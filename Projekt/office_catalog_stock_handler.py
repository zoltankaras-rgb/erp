# ==== SKLAD – ERP_NEW IMPLEMENTÁCIA ====
from datetime import datetime
import db_connector
from validators import safe_get_float, safe_get_int
# --- PDF fonty (diakritika) ---
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_fonts_ready = False
def _ensure_pdf_fonts():
    """Zaregistruje DejaVuSans/DejaVuSans-Bold, ak sú v /fonts; inak ostane default."""
    global _fonts_ready
    if _fonts_ready:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, 'fonts'),
        os.path.join(os.path.dirname(here), 'fonts'),
    ]
    reg_ok = 0
    for base in candidates:
        reg = os.path.join(base, 'DejaVuSans.ttf')
        reg_b = os.path.join(base, 'DejaVuSans-Bold.ttf')
        if os.path.exists(reg) and os.path.exists(reg_b):
            pdfmetrics.registerFont(TTFont('DejaVuSans', reg))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', reg_b))
            _fonts_ready = True
            break

def get_warehouses(**kwargs):
    """Zoznam skladov pre selecty a filter dashboardu."""
    rows = db_connector.execute_query(
        "SELECT id, nazov, typ FROM warehouses ORDER BY id"
    )
    return {"warehouses": rows}

def get_stock_overview(**kwargs):
    """
    Prehľad skladu pre dashboard.
    Voliteľne príde warehouse_id (int). Ak nie, vráti všetko.
    """
    warehouse_id = safe_get_int(kwargs.get("warehouse_id")) if kwargs else None
    base_sql = """
        SELECT 
            sp.sklad_id,
            w.nazov                AS sklad,
            p.id                   AS product_id,
            p.ean,
            p.nazov                AS product,
            COALESCE(pc.name,'')   AS category,
            sp.mnozstvo            AS qty,
            sp.priemerna_cena      AS avg_cost,
            ROUND(sp.mnozstvo * sp.priemerna_cena, 2) AS stock_value
        FROM sklad_polozky sp
        JOIN warehouses w      ON w.id = sp.sklad_id
        JOIN products   p      ON p.id = sp.produkt_id
        LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
    """
    if warehouse_id:
        sql = base_sql + " WHERE sp.sklad_id=%s ORDER BY w.nazov, p.nazov"
        rows = db_connector.execute_query(sql, (warehouse_id,))
    else:
        sql = base_sql + " ORDER BY w.nazov, p.nazov"
        rows = db_connector.execute_query(sql)
    # agregácia pre hlavičku (voliteľné)
    total_value = sum((r.get("stock_value") or 0) for r in rows)
    return {"items": rows, "total_value": float(f"{total_value:.2f}")}

# ==== SUROVINY (ERP_NEW) – Kancelária / Sklad ====
from datetime import datetime
import db_connector
from validators import safe_get_float, safe_get_int

# konštanty pre typ a jednotku – uprav, ak používaš inú mapu
TYP_SUROVINA = 0   # raw material
JEDNOTKA_KG  = 0   # kg

def _get_product_id_by_any(identifier):
    """id/ean/nazov -> product_id (alebo None)"""
    if identifier is None:
        return None
    ident = str(identifier).strip()
    # id?
    try:
        pid = int(ident)
        row = db_connector.execute_query("SELECT id FROM products WHERE id=%s", (pid,), fetch='one')
        if row: return row['id']
    except Exception:
        pass
    # ean
    row = db_connector.execute_query("SELECT id FROM products WHERE ean=%s", (ident,), fetch='one')
    if row: return row['id']
    # nazov
    row = db_connector.execute_query("SELECT id FROM products WHERE nazov=%s", (ident,), fetch='one')
    if row: return row['id']
    return None

def raw_get_categories(**kwargs):
    """Zoznam kategórií surovín (pre select v UI)."""
    rows = db_connector.execute_query("SELECT id, name AS nazov FROM product_categories ORDER BY name")
    return {"categories": rows}

def raw_list_by_category(**kwargs):
    """
    Prehľad surovín VO VÝROBNOM SKLADE (sklad_id = 1).
    Voliteľne filter podľa predajnej/produktovej kategórie (category_id).
    Vracia len položky, ktoré v sklade 1 skutočne existujú (INNER JOIN na sklad_polozky).
    """
    warehouse_id = 1  # fix na výrobný sklad
    category_id  = (kwargs or {}).get("category_id")

    sql = """
        SELECT
            sp.sklad_id,
            w.nazov                     AS sklad,
            p.id                        AS product_id,
            p.ean,
            p.nazov                     AS product,
            COALESCE(pc.name,'')        AS category,
            sp.mnozstvo                 AS qty,
            sp.priemerna_cena           AS avg_cost,
            ROUND(sp.mnozstvo * sp.priemerna_cena, 2) AS stock_value
        FROM sklad_polozky sp
        JOIN warehouses w         ON w.id = sp.sklad_id
        JOIN products   p         ON p.id = sp.produkt_id
        LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
        WHERE sp.sklad_id = %s
          AND p.typ = %s          -- len suroviny (raw)
    """
    params = [warehouse_id, TYP_SUROVINA]

    if category_id:
        sql += " AND p.kategoria_id = %s"
        params.append(safe_get_int(category_id))

    sql += " ORDER BY pc.name, p.nazov"
    rows = db_connector.execute_query(sql, tuple(params))
    total = sum((r.get("stock_value") or 0) for r in rows)
    return {"items": rows, "total_value": float(f"{total:.2f}")} 

def raw_add_material_product(**kwargs):
    """
    Založenie suroviny (produkt) – očakáva:
    {
      "name": "Bravčové plece",
      "ean": "optional",
      "category_id": 123,     # product_categories.id
      "min_stock": "5.0",
      "dph": "20.00"          # ak riešiš
    }
    """
    if not kwargs:
        return {"error": "Chýba JSON payload."}
    name = (kwargs.get("name") or "").strip()
    if not name:
        return {"error": "Zadaj názov suroviny."}

    ean         = (kwargs.get("ean") or None)
    category_id = safe_get_int(kwargs.get("category_id") or 0) or None
    min_stock   = safe_get_float(kwargs.get("min_stock") or 0.0)
    dph         = safe_get_float(kwargs.get("dph") or 20.0)

    # existuje už?
    row = db_connector.execute_query("SELECT id FROM products WHERE nazov=%s", (name,), fetch='one')
    if row:
        return {"error": "Surovina s týmto názvom už existuje."}

    db_connector.execute_query("""
        INSERT INTO products (ean, nazov, typ, jednotka, kategoria_id, min_zasoba, dph, je_vyroba)
        VALUES (%s,%s,%s,%s,%s,%s,%s,0)
    """, (ean, name, TYP_SUROVINA, JEDNOTKA_KG, category_id, min_stock, dph), fetch=None)
    new_row = db_connector.execute_query("SELECT id, ean, nazov FROM products WHERE nazov=%s", (name,), fetch='one')
    return {"ok": True, "product": new_row}

def raw_receive_material(**kwargs):
    """
    Príjem suroviny do skladu (jedna položka). Očakáva:
    {
      "warehouse_id": 1,
      "product": "1111111111111",  # id/ean/nazov
      "qty": "12.5",
      "unit_cost": "4.20",
      "supplier": "Dodavatel a.s."
    }
    """
    if not kwargs:
        return {"error": "Chýba JSON payload."}
    warehouse_id = safe_get_int(kwargs.get("warehouse_id") or 1)
    ident        = (kwargs.get("product") or "").strip()
    qty          = safe_get_float(kwargs.get("qty") or 0)
    unit_cost    = safe_get_float(kwargs.get("unit_cost") or 0)
    supplier     = (kwargs.get("supplier") or None)
    if not ident or qty <= 0 or unit_cost < 0:
        return {"error": "Zadaj produkt, kladné množstvo a cenu."}

    product_id = _get_product_id_by_any(ident)
    if not product_id:
        return {"error": "Produkt neexistuje."}

    conn = db_connector.get_connection()
    cur = conn.cursor()
    try:
        rec = db_connector.execute_query(
            "SELECT id, mnozstvo, priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
            (warehouse_id, product_id), fetch='one'
        )
        if rec:
            old_q = float(rec["mnozstvo"]); old_c = float(rec["priemerna_cena"])
            new_q = old_q + qty
            new_avg = (old_q*old_c + qty*unit_cost) / new_q if new_q > 0 else unit_cost
            cur.execute("UPDATE sklad_polozky SET mnozstvo=%s, priemerna_cena=%s WHERE id=%s", (new_q, new_avg, rec["id"]))
        else:
            cur.execute("INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena) VALUES (%s,%s,%s,%s)",
                        (warehouse_id, product_id, qty, unit_cost))
        # doklad príjmu + ledger
        cur.execute("INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, cena, dodavatel) VALUES (%s,%s,%s,%s,%s,%s)",
                    (warehouse_id, product_id, datetime.now(), qty, unit_cost, supplier))
        cur.execute("INSERT INTO inventory_movements (sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (warehouse_id, product_id, qty, unit_cost, 1, 'zaznamy_prijem', supplier))
        conn.commit()
        return {"ok": True, "received": {"product_id": product_id, "qty": qty, "unit_cost": unit_cost}}
    except Exception:
        conn.rollback()
        raise
    finally:
        try: cur.close(); conn.close()
        except Exception: pass

def raw_writeoff_material(**kwargs):
    """
    Odpis suroviny (jedna položka). Očakáva:
    {
      "warehouse_id": 1,
      "product": "1111111111111",  # id/ean/nazov
      "qty": "1.25",
      "reason_code": 1,
      "reason_text": "poškodené",
      "actor_user_id": 1
    }
    """
    if not kwargs:
        return {"error": "Chýba JSON payload."}
    warehouse_id = safe_get_int(kwargs.get("warehouse_id") or 1)
    ident        = (kwargs.get("product") or "").strip()
    qty          = safe_get_float(kwargs.get("qty") or 0)
    reason_code  = safe_get_int(kwargs.get("reason_code") or 3)
    reason_text  = (kwargs.get("reason_text") or None)
    actor_user_id= safe_get_int(kwargs.get("actor_user_id") or 0)

    if not ident or qty <= 0:
        return {"error": "Zadaj produkt a kladné množstvo."}

    product_id = _get_product_id_by_any(ident)
    if not product_id:
        return {"error": "Produkt neexistuje."}

    conn = db_connector.get_connection()
    cur = conn.cursor()
    try:
        rec = db_connector.execute_query(
            "SELECT id, mnozstvo, priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
            (warehouse_id, product_id), fetch='one'
        )
        if not rec or float(rec["mnozstvo"]) < qty:
            return {"error": "Nedostatočné množstvo na sklade."}

        new_q = float(rec["mnozstvo"]) - qty
        cur.execute("UPDATE sklad_polozky SET mnozstvo=%s WHERE id=%s", (new_q, rec["id"]))
        cur.execute("INSERT INTO writeoff_logs (sklad_id, produkt_id, qty, reason_code, reason_text, actor_user_id) VALUES (%s,%s,%s,%s,%s,%s)",
                    (warehouse_id, product_id, qty, reason_code, reason_text, actor_user_id))
        cur.execute("INSERT INTO inventory_movements (sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (warehouse_id, product_id, -qty, float(rec["priemerna_cena"]), 3, 'writeoff_logs', reason_text))
        conn.commit()
        return {"ok": True, "written_off": {"product_id": product_id, "qty": qty}}
    except Exception:
        conn.rollback()
        raise
    finally:
        try: cur.close(); conn.close()
        except Exception: pass
# ==== SKLAD / SUROVINY – ERP_NEW IMPLEMENTÁCIA (PATCH) ====
from datetime import datetime
import db_connector
from validators import safe_get_float, safe_get_int

TYP_SUROVINA = 0   # raw material
JEDNOTKA_KG  = 0   # kg

def get_warehouses(**kwargs):
    """Zoznam skladov (napr. Výroba=1)."""
    rows = db_connector.execute_query(
        "SELECT id, nazov, typ FROM warehouses ORDER BY id"
    )
    return {"warehouses": rows}

def raw_get_categories(**kwargs):
    """Zoznam kategórií surovín (Mäso, Koreniny, Obaly, Pomocný materiál...)."""
    rows = db_connector.execute_query(
        "SELECT id, name AS nazov FROM product_categories ORDER BY name"
    )
    return {"categories": rows}

def raw_list_by_category(**kwargs):
    """
    Prehľad surovín v sklade (filtre: warehouse_id, category_id).
    Vracia qty, priemerna_cena, stock_value, product_id atď.
    """
    warehouse_id = safe_get_int((kwargs or {}).get("warehouse_id") or 1)
    category_id  = (kwargs or {}).get("category_id")
    sql = """
        SELECT
            sp.sklad_id,
            w.nazov                     AS sklad,
            p.id                        AS product_id,
            p.ean,
            p.nazov                     AS product,
            COALESCE(pc.name,'')        AS category,
            COALESCE(sp.mnozstvo,0.0)   AS qty,
            COALESCE(sp.priemerna_cena,0.0) AS avg_cost,
            ROUND(COALESCE(sp.mnozstvo,0.0) * COALESCE(sp.priemerna_cena,0.0), 2) AS stock_value
        FROM products p
        LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
        LEFT JOIN sklad_polozky sp ON sp.produkt_id = p.id AND sp.sklad_id = %s
        LEFT JOIN warehouses w ON w.id = %s
        WHERE p.typ = %s
    """
    params = [warehouse_id, warehouse_id, TYP_SUROVINA]
    if category_id:
        sql += " AND p.kategoria_id = %s"
        params.append(safe_get_int(category_id))
    sql += " ORDER BY pc.name, p.nazov"
    rows = db_connector.execute_query(sql, tuple(params))
    total = sum((r.get("stock_value") or 0) for r in rows)
    return {"items": rows, "total_value": float(f"{total:.2f}")}

def _get_product_id_by_any(identifier):
    """Pomôcka: ID / EAN / presný NÁZOV -> product_id alebo None."""
    if identifier is None:
        return None
    ident = str(identifier).strip()
    # ID?
    try:
        pid = int(ident)
        row = db_connector.execute_query("SELECT id FROM products WHERE id=%s", (pid,), fetch='one')
        if row: return row['id']
    except Exception:
        pass
    # EAN
    row = db_connector.execute_query("SELECT id FROM products WHERE ean=%s", (ident,), fetch='one')
    if row: return row['id']
    # NÁZOV (presne)
    row = db_connector.execute_query("SELECT id FROM products WHERE nazov=%s", (ident,), fetch='one')
    if row: return row['id']
    return None

def receive_multiple_stock_items(**kwargs):
    """
    VIACRIADKOVÝ PRÍJEM do skladu.
    Očakáva JSON:
    {
      "warehouse_id": 1,
      "items": [
        {"product": "123" | "1111111111111" | "Bravčové plece", "qty": "5.5", "unit_cost": "4.20", "supplier": "Rozrábka|Expedícia|Externý dodávateľ|Iné|..."},
        ...
      ]
    }
    """
    if not kwargs:
        return {"error": "Chýba JSON payload."}
    warehouse_id = safe_get_int(kwargs.get("warehouse_id") or 1)
    items = kwargs.get("items") or []
    if not items:
        return {"error": "Zadajte aspoň jednu položku."}

    conn = db_connector.get_connection()
    cur = conn.cursor()
    try:
        done = []
        for it in items:
            ident = (it.get("product") or "").strip()
            qty = safe_get_float(it.get("qty") or 0)
            unit_cost = safe_get_float(it.get("unit_cost") or 0)
            supplier = (it.get("supplier") or None)

            if not ident or qty <= 0 or unit_cost < 0:
                continue

            product_id = _get_product_id_by_any(ident)
            if not product_id:
                continue

            # existujúci záznam v sklade?
            rec = db_connector.execute_query(
                "SELECT id, mnozstvo, priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
                (warehouse_id, product_id), fetch='one'
            )
            if rec:
                old_q = float(rec["mnozstvo"])
                old_c = float(rec["priemerna_cena"])
                new_q = old_q + qty
                new_avg = (old_q*old_c + qty*unit_cost) / new_q if new_q > 0 else unit_cost
                cur.execute(
                    "UPDATE sklad_polozky SET mnozstvo=%s, priemerna_cena=%s WHERE id=%s",
                    (new_q, new_avg, rec["id"])
                )
            else:
                cur.execute(
                    "INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena) VALUES (%s,%s,%s,%s)",
                    (warehouse_id, product_id, qty, unit_cost)
                )

            # doklad príjmu + ledger
            cur.execute(
                "INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, cena, dodavatel) VALUES (%s,%s,%s,%s,%s,%s)",
                (warehouse_id, product_id, datetime.now(), qty, unit_cost, supplier)
            )
            cur.execute(
                "INSERT INTO inventory_movements (sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (warehouse_id, product_id, qty, unit_cost, 1, 'zaznamy_prijem', supplier)
            )
            done.append({"product_id": product_id, "qty": qty})

        conn.commit()
        return {"ok": True, "count": len(done), "received": done}
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

def raw_receive_material(**kwargs):
    """Jednoriadkový PRÍJEM – volá multi s jedným itemom."""
    if not kwargs:
        return {"error": "Chýba JSON payload."}
    warehouse_id = safe_get_int(kwargs.get("warehouse_id") or 1)
    item = {
        "product": (kwargs.get("product") or "").strip(),
        "qty": kwargs.get("qty"),
        "unit_cost": kwargs.get("unit_cost"),
        "supplier": kwargs.get("supplier")
    }
    return receive_multiple_stock_items({"warehouse_id": warehouse_id, "items": [item]})

def raw_writeoff_material(**kwargs):
    """
    ODPIS zo skladu (jedna položka):
    { "warehouse_id":1, "product":"<id|ean|nazov>", "qty":"1.25", "reason_code":1, "reason_text":"poškodené", "actor_user_id": 1 }
    """
    if not kwargs:
        return {"error":"Chýba JSON payload."}
    warehouse_id = safe_get_int(kwargs.get("warehouse_id") or 1)
    ident        = (kwargs.get("product") or "").strip()
    qty          = safe_get_float(kwargs.get("qty") or 0)
    reason_code  = safe_get_int(kwargs.get("reason_code") or 3)
    reason_text  = (kwargs.get("reason_text") or None)
    actor_user_id= safe_get_int(kwargs.get("actor_user_id") or 0)

    if not ident or qty <= 0:
        return {"error":"Zadajte produkt a kladné množstvo."}

    product_id = _get_product_id_by_any(ident)
    if not product_id:
        return {"error":"Produkt neexistuje."}

    conn = db_connector.get_connection()
    cur = conn.cursor()
    try:
        rec = db_connector.execute_query(
            "SELECT id, mnozstvo, priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
            (warehouse_id, product_id), fetch='one'
        )
        if not rec or float(rec["mnozstvo"]) < qty:
            return {"error":"Nedostatočné množstvo na sklade."}

        new_q = float(rec["mnozstvo"]) - qty
        cur.execute("UPDATE sklad_polozky SET mnozstvo=%s WHERE id=%s", (new_q, rec["id"]))
        cur.execute(
            "INSERT INTO writeoff_logs (sklad_id, produkt_id, qty, reason_code, reason_text, actor_user_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (warehouse_id, product_id, qty, reason_code, reason_text, actor_user_id)
        )
        cur.execute(
            "INSERT INTO inventory_movements (sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (warehouse_id, product_id, -qty, float(rec["priemerna_cena"]), 3, 'writeoff_logs', reason_text)
        )
        conn.commit()
        return {"ok": True, "written_off": {"product_id": product_id, "qty": qty}}
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass
# ==== ERP ADMIN – CENTRÁLNY KATALÓG (ERP_NEW) ====
import db_connector
from validators import safe_get_float, safe_get_int

VAT_ALLOWED = {5.0, 10.0, 19.0, 20.0, 23.0}

def erp_get_sales_categories(**kwargs):
    rows = db_connector.execute_query("SELECT id, name FROM sales_categories ORDER BY name")
    return {"categories": rows}

def erp_add_sales_category(**kwargs):
    name = (kwargs or {}).get("name")
    if not name or not str(name).strip():
        return {"error": "Zadaj názov kategórie."}
    name = str(name).strip()
    exists = db_connector.execute_query("SELECT id FROM sales_categories WHERE name=%s", (name,), fetch='one')
    if exists:
        return {"error": "Kategória už existuje."}
    db_connector.execute_query("INSERT INTO sales_categories (name) VALUES (%s)", (name,), fetch=None)
    row = db_connector.execute_query("SELECT id, name FROM sales_categories WHERE name=%s", (name,), fetch='one')
    return {"ok": True, "category": row}

def erp_add_catalog_product(**kwargs):
    """
    Očakáva JSON:
    {
      "ean": "123...", "name": "Názov", "vat": 20.0,
      "sales_category_id": 3, "unit": "kg" | "ks", "is_produced": true/false
    }
    """
    if not kwargs: return {"error": "Chýba payload."}
    ean   = (kwargs.get("ean") or None)
    name  = (kwargs.get("name") or "").strip()
    vat   = safe_get_float(kwargs.get("vat") or 20.0)
    sc_id = safe_get_int(kwargs.get("sales_category_id") or 0)
    unit  = (kwargs.get("unit") or "kg").strip().lower()
    is_prod = True if kwargs.get("is_produced") in (True, "true", 1, "1", "on") else False

    if not name:
        return {"error": "Zadaj názov produktu."}
    if vat not in VAT_ALLOWED:
        return {"error": f"DPH {vat}% nie je povolené. Povolené: {sorted(VAT_ALLOWED)}"}
    if unit not in ("kg", "ks"):
        return {"error": "Jednotka musí byť 'kg' alebo 'ks'."}

    # jednotka: 0 = kg, 1 = ks
    jednotka = 0 if unit == "kg" else 1
    # typ: ponecháme 1 = predajný produkt (konzistentne s tvojimi seedmi)
    typ = 1
    # min_zasoba default 0
    # kategoria_id (technická kategória) necháme NULL – predajnú dávame do sales_categories
    # je_vyroba podľa checkboxu
    # unikátnejšie: EAN môže byť NULL ale ak je, musí byť unikátny
    if ean:
        dup = db_connector.execute_query("SELECT id FROM products WHERE ean=%s", (ean,), fetch='one')
        if dup:
            return {"error": "EAN už existuje."}

    db_connector.execute_query("""
        INSERT INTO products (ean, nazov, typ, jednotka, kategoria_id, min_zasoba, dph, je_vyroba)
        VALUES (%s, %s, %s, %s, NULL, 0.000, %s, %s)
    """, (ean, name, typ, jednotka, vat, 1 if is_prod else 0), fetch=None)

    prod = db_connector.execute_query("SELECT id, ean, nazov, dph, jednotka, je_vyroba FROM products WHERE nazov=%s ORDER BY id DESC", (name,), fetch='one')
    if sc_id:
        # priraď predajnú kategóriu (m:n)
        db_connector.execute_query("""
            INSERT IGNORE INTO product_sales_categories (product_id, sales_category_id)
            VALUES (%s, %s)
        """, (prod["id"], sc_id), fetch=None)

    return {"ok": True, "product": prod}

def erp_catalog_overview(**kwargs):
    """
    Prehľad centrálneho katalógu: len produkty z katalógu (typ = 1),
    nie suroviny výroby (typ = 0).
    """
    sql = """
      SELECT
        p.id,
        ANY_VALUE(p.ean)       AS ean,
        ANY_VALUE(p.nazov)     AS nazov,
        ANY_VALUE(p.dph)       AS dph,
        ANY_VALUE(p.jednotka)  AS jednotka,
        ANY_VALUE(p.je_vyroba) AS je_vyroba,
        GROUP_CONCAT(DISTINCT sc.name ORDER BY sc.name SEPARATOR ', ') AS sales_categories
      FROM products p
      LEFT JOIN product_sales_categories psc ON psc.product_id = p.id
      LEFT JOIN sales_categories sc ON sc.id = psc.sales_category_id
      WHERE p.typ = 1
      GROUP BY p.id
      ORDER BY nazov
    """
    rows = db_connector.execute_query(sql)
    for r in rows:
        r["unit_label"] = "kg" if (r.get("jednotka") == 0) else "ks"
        r["is_produced"] = bool(r.get("je_vyroba"))
    return {"items": rows}
# ==== Sklad – špecializované príjmy & Dodávatelia (ERP_NEW) ====
from datetime import datetime
import db_connector
from validators import safe_get_float, safe_get_int

TYP_SUROVINA = 0   # raw material
WAREHOUSE_VYROBA = 1  # výrobny sklad

# --- Dodávatelia (register) ---
def erp_list_suppliers(**kwargs):
    rows = db_connector.execute_query("""
        SELECT id, name, ico, dic, ic_dph, email, phone, address, note
        FROM suppliers
        ORDER BY name
    """)
    return {"suppliers": rows}

def erp_add_supplier(**kwargs):
    if not kwargs:
        return {"error": "Chýba JSON payload."}
    name     = (kwargs.get("name") or "").strip()
    ico      = (kwargs.get("ico") or None)
    dic      = (kwargs.get("dic") or None)
    ic_dph   = (kwargs.get("ic_dph") or None)
    email    = (kwargs.get("email") or None)
    phone    = (kwargs.get("phone") or None)
    address  = (kwargs.get("address") or None)
    note     = (kwargs.get("note") or None)
    if not name:
        return {"error": "Zadaj názov dodávateľa."}
    db_connector.execute_query("""
      INSERT INTO suppliers (name, ico, dic, ic_dph, email, phone, address, note)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (name, ico, dic, ic_dph, email, phone, address, note), fetch=None)
    row = db_connector.execute_query("SELECT * FROM suppliers WHERE name=%s ORDER BY id DESC", (name,), fetch='one')
    return {"ok": True, "supplier": row}

# --- Produkty (len suroviny), rozdelené podľa kategórií ---
def raw_list_products_meat(**kwargs):
    """Vráti zoznam SUROVÍN v kategórii 'Mäso' (id + názov) – na výber do príjmu Mäso."""
    rows = db_connector.execute_query("""
      SELECT p.id, p.nazov
      FROM products p
      LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
      WHERE p.typ = %s AND pc.name = 'Mäso'
      ORDER BY p.nazov
    """, (TYP_SUROVINA,))
    return {"items": rows}

def raw_list_products_other(**kwargs):
    """Vráti zoznam SUROVÍN v kategóriách 'Koreniny','Obaly','Pomocný materiál' – pre druhý príjem."""
    rows = db_connector.execute_query("""
      SELECT p.id, p.nazov
      FROM products p
      LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
      WHERE p.typ = %s AND pc.name IN ('Koreniny','Obaly','Pomocný materiál')
      ORDER BY p.nazov
    """, (TYP_SUROVINA,))
    return {"items": rows}

# --- Príjem Mäso (multi-riadky) ---
def receive_meat_items(**kwargs):
    """
    JSON:
    {
      "items": [ {"product_id": 123, "qty": "5.5", "unit_cost": "4.20", "supplier_text": "Rozrábka|Expedícia|Externý dodávateľ|Iné ..."} ]
    }
    Zapisuje do: sklad_polozky (WH=1), zaznamy_prijem, inventory_movements
    """
    if not kwargs: return {"error": "Chýba JSON payload."}
    items = kwargs.get("items") or []
    if not items: return {"error": "Zadaj aspoň jednu položku."}

    conn = db_connector.get_connection(); cur = conn.cursor()
    try:
        done = []
        for it in items:
            product_id  = safe_get_int(it.get("product_id"))
            qty         = safe_get_float(it.get("qty") or 0)
            unit_cost   = safe_get_float(it.get("unit_cost") or 0)
            supplier_tx = (it.get("supplier_text") or None)
            if not product_id or qty <= 0 or unit_cost < 0:
                continue

            rec = db_connector.execute_query(
                "SELECT id, mnozstvo, priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
                (WAREHOUSE_VYROBA, product_id), fetch='one'
            )
            if rec:
                old_q = float(rec["mnozstvo"]); old_c = float(rec["priemerna_cena"])
                new_q = old_q + qty
                new_avg = (old_q*old_c + qty*unit_cost) / new_q if new_q>0 else unit_cost
                cur.execute("UPDATE sklad_polozky SET mnozstvo=%s, priemerna_cena=%s WHERE id=%s",
                            (new_q, new_avg, rec["id"]))
            else:
                cur.execute("INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena) VALUES (%s,%s,%s,%s)",
                            (WAREHOUSE_VYROBA, product_id, qty, unit_cost))

            cur.execute("INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, cena, dodavatel) VALUES (%s,%s,%s,%s,%s,%s)",
                        (WAREHOUSE_VYROBA, product_id, datetime.now(), qty, unit_cost, supplier_tx))
            cur.execute("INSERT INTO inventory_movements (sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (WAREHOUSE_VYROBA, product_id, qty, unit_cost, 1, 'zaznamy_prijem', supplier_tx))
            done.append({"product_id": product_id, "qty": qty})
        conn.commit()
        return {"ok": True, "count": len(done), "received": done}
    except Exception:
        conn.rollback(); raise
    finally:
        try: cur.close(); conn.close()
        except: pass

# --- Príjem Koreniny/Obaly/Pomocný materiál (multi-riadky so supplier_id) ---
def receive_other_items(**kwargs):
    """
    JSON:
    {
      "supplier_id": 7,        # povinné (vyberieš z registru dodávateľov)
      "items": [ {"product_id": 321, "qty": "2", "unit_cost": "1.15"}, ... ]
    }
    Dodávateľa uložíme do zaznamy_prijem.dodavatel ako názov (text).
    """
    if not kwargs: return {"error": "Chýba JSON payload."}
    supplier_id = safe_get_int(kwargs.get("supplier_id") or 0)
    items = kwargs.get("items") or []
    if not supplier_id: return {"error": "Vyber dodávateľa."}
    if not items: return {"error": "Zadaj aspoň jednu položku."}

    sup = db_connector.execute_query("SELECT name FROM suppliers WHERE id=%s", (supplier_id,), fetch='one')
    if not sup: return {"error": "Dodávateľ neexistuje."}
    supplier_name = sup["name"]

    conn = db_connector.get_connection(); cur = conn.cursor()
    try:
        done = []
        for it in items:
            product_id = safe_get_int(it.get("product_id"))
            qty        = safe_get_float(it.get("qty") or 0)
            unit_cost  = safe_get_float(it.get("unit_cost") or 0)
            if not product_id or qty <= 0 or unit_cost < 0:
                continue

            rec = db_connector.execute_query(
                "SELECT id, mnozstvo, priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
                (WAREHOUSE_VYROBA, product_id), fetch='one'
            )
            if rec:
                old_q = float(rec["mnozstvo"]); old_c = float(rec["priemerna_cena"])
                new_q = old_q + qty
                new_avg = (old_q*old_c + qty*unit_cost) / new_q if new_q>0 else unit_cost
                cur.execute("UPDATE sklad_polozky SET mnozstvo=%s, priemerna_cena=%s WHERE id=%s",
                            (new_q, new_avg, rec["id"]))
            else:
                cur.execute("INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena) VALUES (%s,%s,%s,%s)",
                            (WAREHOUSE_VYROBA, product_id, qty, unit_cost))

            cur.execute("INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, cena, dodavatel) VALUES (%s,%s,%s,%s,%s,%s)",
                        (WAREHOUSE_VYROBA, product_id, datetime.now(), qty, unit_cost, supplier_name))
            cur.execute("INSERT INTO inventory_movements (sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (WAREHOUSE_VYROBA, product_id, qty, unit_cost, 1, 'zaznamy_prijem', supplier_name))
            done.append({"product_id": product_id, "qty": qty, "supplier": supplier_name})
        conn.commit()
        return {"ok": True, "count": len(done), "received": done, "supplier": supplier_name}
    except Exception:
        conn.rollback(); raise
    finally:
        try: cur.close(); conn.close()
        except: pass
# ==== REPORTY PRÍJMU – Výrobný sklad (ID=1) ====
from datetime import datetime, timedelta
from io import BytesIO
from flask import send_file, make_response
import db_connector
from validators import safe_get_float, safe_get_int

WAREHOUSE_VYROBA = 1

# helper na obdobie
def _resolve_period(kwargs):
    """
    Vstup (JSON):
      period: 'week' | 'month' | 'range'
      date_from: 'YYYY-MM-DD' (len pre 'range')
      date_to:   'YYYY-MM-DD' (len pre 'range')
    Výstup: (dt_from, dt_to_exclusive)
    """
    now = datetime.now()
    period = (kwargs or {}).get('period') or 'week'
    if period == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # ďalší mesiac
        if start.month == 12:
            end = start.replace(year=start.year+1, month=1)
        else:
            end = start.replace(month=start.month+1)
        return start, end
    elif period == 'range':
        ds = (kwargs or {}).get('date_from')
        de = (kwargs or {}).get('date_to')
        if not ds or not de:
            # fallback na posledných 7 dní
            end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            start = end - timedelta(days=7)
            return start, end
        try:
            start = datetime.strptime(ds, "%Y-%m-%d")
            end   = datetime.strptime(de, "%Y-%m-%d") + timedelta(days=1)  # exclusive
            return start, end
        except Exception:
            end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            start = end - timedelta(days=7)
            return start, end
    else:  # 'week'
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        start = end - timedelta(days=7)
        return start, end

def _category_where(category_scope):
    """
    'meat' -> pc.name='Mäso'
    'other'-> pc.name IN ('Koreniny','Obaly','Pomocný materiál')
    'all'  -> bez filtra
    """
    if category_scope == 'meat':
        return " AND pc.name = 'Mäso' "
    elif category_scope == 'other':
        return " AND pc.name IN ('Koreniny','Obaly','Pomocný materiál') "
    return ""  # all
def report_receipts_summary(**kwargs):
    """
    JSON report pre tabuľku v UI.
    Vstup JSON:
      { "period":"week|month|range", "date_from":"YYYY-MM-DD", "date_to":"YYYY-MM-DD",
        "category_scope": "meat|other|all" }
    """
    category_scope = (kwargs or {}).get('category_scope') or 'all'
    dt_from, dt_to = _resolve_period(kwargs)

    sql = f"""
      SELECT
        pc.name                           AS category,
        COALESCE(zp.dodavatel, '—')       AS supplier,
        p.nazov                           AS product,
        SUM(zp.mnozstvo)                  AS qty,
        AVG(zp.cena)                      AS avg_price,
        SUM(zp.mnozstvo * zp.cena)        AS total_cost
      FROM zaznamy_prijem zp
      JOIN products p            ON p.id = zp.produkt_id
      LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
      WHERE zp.sklad_id = %s
        AND zp.datum >= %s AND zp.datum < %s
        { _category_where(category_scope) }
      GROUP BY pc.name, supplier, p.nazov
      ORDER BY pc.name, supplier, p.nazov
    """
    rows = db_connector.execute_query(sql, (WAREHOUSE_VYROBA, dt_from, dt_to))

    # sumáre podľa kategórie a podľa dodávateľa
    cat_totals = {}
    sup_totals = {}
    grand_total = 0.0
    for r in rows:
        total = float(r.get("total_cost") or 0.0)
        grand_total += total
        cat = r.get("category") or "Nezaradené"
        sup = r.get("supplier") or "—"
        cat_totals[cat] = cat_totals.get(cat, 0.0) + total
        sup_totals[sup] = sup_totals.get(sup, 0.0) + total

    return {
        "period": {"from": dt_from.strftime("%Y-%m-%d"), "to": (dt_to - timedelta(days=1)).strftime("%Y-%m-%d")},
        "category_scope": category_scope,
        "items": rows,  # obsahuje aj 'supplier'
        "totals_by_category": [{"category": k, "total_cost": round(v, 2)} for k, v in cat_totals.items()],
        "totals_by_supplier": [{"supplier": k, "total_cost": round(v, 2)} for k, v in sup_totals.items()],
        "grand_total": round(grand_total, 2),
    }

def report_receipts_pdf(**kwargs):
    """
    Vygeneruje PDF report – s diakritikou (DejaVuSans) a so stĺpcom 'Dodávateľ'.
    """
    _ensure_pdf_fonts()  # zaregistruje DejaVuSans, ak sme ju našli
    data = report_receipts_summary(**kwargs)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)

    styles = getSampleStyleSheet()
    # ak máme font, prepíš názvy
    if _fonts_ready:
        for k in styles.byName:
            styles[k].fontName = 'DejaVuSans'
        styles['Title'].fontName = 'DejaVuSans-Bold'
        styles['Heading3'].fontName = 'DejaVuSans-Bold'

    story = []
    title = f"Report príjmu – Výrobný sklad (ID=1)"
    period_txt = f"Obdobie: {data['period']['from']} – {data['period']['to']}; Kategórie: {data['category_scope']}"
    story.append(Paragraph(title, styles['Title']))
    story.append(Paragraph(period_txt, styles['Normal']))
    story.append(Spacer(1, 12))

    # tabuľka (vrátane dodávateľa)
    table_data = [["Kategória", "Dodávateľ", "Produkt", "Množstvo", "Priem. cena", "Hodnota (€)"]]
    for r in data["items"]:
        table_data.append([
            r.get("category") or "Nezaradené",
            r.get("supplier") or "—",
            r.get("product") or "",
            f"{float(r.get('qty') or 0):.3f}",
            f"{float(r.get('avg_price') or 0):.4f}",
            f"{float(r.get('total_cost') or 0):.2f}",
        ])

    col_widths = [100, 110, 160, 60, 70, 80]
    table = Table(table_data, colWidths=col_widths)
    tbl_style = [
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor("#e5e7eb")),
        ('ALIGN', (3,1), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f3f4f6")),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
    ]
    if _fonts_ready:
        tbl_style += [
            ('FONTNAME', (0,0), (-1,0), 'DejaVuSans-Bold'),
            ('FONTNAME', (0,1), (-1,-1), 'DejaVuSans'),
        ]
    table.setStyle(TableStyle(tbl_style))
    story.append(table)
    story.append(Spacer(1, 12))

    # sumáre
    story.append(Paragraph("<b>Súčty podľa kategórie</b>", styles['Heading3']))
    sums_data = [["Kategória", "Hodnota (€)"]]
    for row in data["totals_by_category"]:
        sums_data.append([row["category"], f"{float(row['total_cost']):.2f}"])
    sums_data.append(["<b>Celkom</b>", f"<b>{float(data['grand_total']):.2f}</b>"])
    sums_table = Table(sums_data, colWidths=[240, 120])
    sums_style = [
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor("#e5e7eb")),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f3f4f6")),
        ('ALIGN', (1,1), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
    ]
    if _fonts_ready:
        sums_style[-1] = ('FONTNAME', (0,-1), (-1,-1), 'DejaVuSans-Bold')
        sums_style.insert(0, ('FONTNAME', (0,0), (-1,0), 'DejaVuSans-Bold'))
        sums_style.append(('FONTNAME', (0,1), (-1,-1), 'DejaVuSans'))
    sums_table.setStyle(TableStyle(sums_style))
    story.append(sums_table)

    doc.build(story)
    pdf_bytes = buf.getvalue(); buf.close()

    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = 'attachment; filename=report_prijmu.pdf'
    return resp
# ==== ERP ADMIN – Výrobné kategórie + parametre výroby ====
import db_connector
from validators import safe_get_float, safe_get_int

def erp_prodcat_list(**kwargs):
    rows = db_connector.execute_query(
        "SELECT id, name FROM production_categories ORDER BY name"
    )
    return {"production_categories": rows}

def erp_prodcat_add(**kwargs):
    name = (kwargs or {}).get("name")
    if not name or not str(name).strip():
        return {"error": "Zadaj názov výrobnej kategórie."}
    name = str(name).strip()
    ex = db_connector.execute_query("SELECT id FROM production_categories WHERE name=%s", (name,), fetch='one')
    if ex: return {"error": "Kategória už existuje."}
    db_connector.execute_query("INSERT INTO production_categories(name) VALUES(%s)", (name,), fetch=None)
    row = db_connector.execute_query("SELECT id, name FROM production_categories WHERE name=%s", (name,), fetch='one')
    return {"ok": True, "category": row}

def erp_product_prodmeta_get(**kwargs):
    pid = safe_get_int((kwargs or {}).get("product_id") or 0)
    if not pid: return {"error":"Chýba product_id"}
    row = db_connector.execute_query("""
        SELECT id, nazov, je_vyroba, production_category_id, production_unit, piece_weight_g
        FROM products WHERE id=%s
    """, (pid,), fetch='one')
    if not row: return {"error":"Produkt neexistuje."}
    return {"product": row}

def erp_product_prodmeta_save(**kwargs):
    """
    { "product_id":123, "is_produced":true/false, "production_category_id":3,
      "production_unit":"kg"|"ks", "piece_weight_g":200 (ak ks) }
    """
    if not kwargs: return {"error":"Chýba payload"}
    pid = safe_get_int(kwargs.get("product_id") or 0)
    is_prod = True if kwargs.get("is_produced") in (True,"true",1,"1","on") else False
    prodcat_id = safe_get_int(kwargs.get("production_category_id") or 0) or None
    unit_str = (kwargs.get("production_unit") or "kg").strip().lower()
    if unit_str not in ("kg","ks"): return {"error":"production_unit musí byť 'kg' alebo 'ks'."}
    production_unit = 0 if unit_str == "kg" else 1
    piece_weight_g = None
    if production_unit == 1:
        pw = kwargs.get("piece_weight_g")
        try:
            piece_weight_g = int(pw)
            if piece_weight_g <= 0: return {"error":"piece_weight_g musí byť kladné celé číslo (gramy)."}
        except Exception:
            return {"error":"piece_weight_g musí byť celé číslo v gramoch."}

    # update
    db_connector.execute_query("""
      UPDATE products
         SET je_vyroba=%s,
             production_category_id=%s,
             production_unit=%s,
             piece_weight_g=%s
       WHERE id=%s
    """, (1 if is_prod else 0, prodcat_id, production_unit, piece_weight_g, pid), fetch=None)

    row = db_connector.execute_query("""
        SELECT id, nazov, je_vyroba, production_category_id, production_unit, piece_weight_g
        FROM products WHERE id=%s
    """, (pid,), fetch='one')
    return {"ok": True, "product": row}
# ==== ERP ADMIN – Recepty (per 100 kg báza) ====
import db_connector
from validators import safe_get_float, safe_get_int

TYP_SUROVINA = 0  # surovina

def erp_recipes_products(**kwargs):
    rows = db_connector.execute_query("""
        SELECT id, nazov FROM products
        WHERE je_vyroba = 1
        ORDER BY nazov
    """)
    return {"products": rows}

def erp_recipes_materials(**kwargs):
    rows = db_connector.execute_query("""
        SELECT id, nazov FROM products
        WHERE typ = %s
        ORDER BY nazov
    """, (TYP_SUROVINA,))
    return {"materials": rows}

def _get_or_create_recipe_for_product(prod_id:int):
    r = db_connector.execute_query("SELECT id FROM recepty WHERE vyrobok_id=%s", (prod_id,), fetch='one')
    if r: return r['id']
    p = db_connector.execute_query("SELECT nazov FROM products WHERE id=%s", (prod_id,), fetch='one')
    name = p['nazov'] if p else f"Recept {prod_id}"
    db_connector.execute_query("INSERT INTO recepty (vyrobok_id, nazov) VALUES (%s,%s)", (prod_id, name), fetch=None)
    r = db_connector.execute_query("SELECT id FROM recepty WHERE vyrobok_id=%s", (prod_id,), fetch='one')
    return r['id']

def erp_recipe_get(**kwargs):
    pid = safe_get_int((kwargs or {}).get('product_id') or 0)
    if not pid: return {"error":"Chýba product_id"}
    rec = db_connector.execute_query("SELECT id, nazov FROM recepty WHERE vyrobok_id=%s", (pid,), fetch='one')
    if not rec:
        return {"recipe": {"product_id": pid, "items": []}}
    items = db_connector.execute_query("""
        SELECT rp.surovina_id AS material_id, p.nazov AS material_name, rp.mnozstvo_na_davku AS qty_per_100kg
        FROM recepty_polozky rp
        JOIN products p ON p.id = rp.surovina_id
        WHERE rp.recept_id=%s
        ORDER BY material_name
    """, (rec['id'],))
    return {"recipe": {"product_id": pid, "name": rec['nazov'], "items": items}}

def erp_recipe_save(**kwargs):
    if not kwargs: return {"error":"Chýba payload"}
    pid   = safe_get_int(kwargs.get('product_id') or 0)
    items = kwargs.get('items') or []
    if not pid: return {"error":"Chýba product_id"}

    cleaned, seen = [], set()
    for it in items:
        mid = safe_get_int(it.get('material_id') or 0)
        q   = safe_get_float(it.get('qty_per_100kg') or 0)
        if not mid or q <= 0: continue
        if mid in seen: return {"error":"Duplicitná surovina v recepte."}
        seen.add(mid)
        cleaned.append((mid, q))

    rec_id = _get_or_create_recipe_for_product(pid)
    db_connector.execute_query("DELETE FROM recepty_polozky WHERE recept_id=%s", (rec_id,), fetch=None)
    if cleaned:
        db_connector.execute_query(
            "INSERT INTO recepty_polozky (recept_id, surovina_id, mnozstvo_na_davku) VALUES (%s,%s,%s)",
            [(rec_id, mid, q) for (mid,q) in cleaned], fetch='none', multi=True
        )
    return {"ok": True, "recipe_id": rec_id, "items_count": len(cleaned)}
# === PRÍJEM DO VÝROBNÉHO SKLADU (WAREHOUSE_PROD=1) ==========================
from decimal import Decimal
def _d(x): 
    try: return Decimal(str(x))
    except: return Decimal('0')

WAREHOUSE_PROD = 1  # ak máš iné ID výrobného skladu, tu zmeň

def prod_receive_get_suppliers(payload=None):
    """Zoznam dodávateľov pre select."""
    conn = db_connector.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name FROM suppliers ORDER BY name")
        rows = cur.fetchall() or []
        return {"suppliers": [{"id": r["id"], "name": r["name"]} for r in rows]}
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

def prod_receive_get_template(payload):
    """
    Načíta šablónu pre dodávateľa: produkty + posledná cena (last_price).
    payload: { supplier_id:int }
    """
    supplier_id = int((payload or {}).get("supplier_id") or 0)
    if supplier_id <= 0:
        return {"error": "Chýba supplier_id."}

    conn = db_connector.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        # berieme všetky produkty, ktoré má tento dodávateľ v product_suppliers
        cur.execute("""
            SELECT p.id AS product_id, p.nazov AS name,
                   COALESCE(ps.last_price, 0) AS price
            FROM product_suppliers ps
            JOIN products p ON p.id = ps.product_id
            WHERE ps.supplier_id = %s
            ORDER BY p.nazov
        """, (supplier_id,))
        items = cur.fetchall() or []
        # FE môže rovno vykresliť grid a doplniť množstvá
        return {"items": [
            {"product_id": r["product_id"], "name": r["name"], "price": float(r["price"]), "qty": 0.0}
            for r in items
        ]}
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

def prod_receive_save_batch(payload):
    """
    Uloží jeden doklad príjmu pre jedného dodávateľa do výrobného skladu.
    payload:
      supplier_id:int
      doc_date?: 'YYYY-MM-DD'
      note?: str
      items: [ { product_id:int, qty:float, price:float } ]
    Efekt:
      - pre každú položku: INSERT do zaznamy_prijem (sklad_id=WAREHOUSE_PROD),
        prepočet WMA do sklad_polozky, movement v inventory_movements (movement_type=1)
      - aktualizuje product_suppliers.last_price pre daného dodávateľa
      - vráti doc_no
    """
    supplier_id = int(payload.get("supplier_id") or 0)
    items = payload.get("items") or []
    doc_date = payload.get("doc_date") or datetime.now().strftime("%Y-%m-%d")
    note = (payload.get("note") or "").strip()
    worker = (payload.get("workerName") or "").strip()  # voliteľné

    if supplier_id <= 0:
        return {"error": "Chýba dodávateľ."}
    # vyfiltruj prázdne riadky
    clean = []
    for it in items:
        pid = int(it.get("product_id") or 0)
        qty = _d(it.get("qty") or 0)
        price = _d(it.get("price") or 0)
        if pid > 0 and qty > 0:
            clean.append({"product_id": pid, "qty": qty, "price": price})
    if not clean:
        return {"error": "Žiadne položky na príjem."}

    # dokladové číslo – jednoduché generovanie
    doc_no = f"PR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    conn = db_connector.get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        for it in clean:
            pid   = it["product_id"]
            qty   = it["qty"]
            price = it["price"]

            # 1) vlož riadok do zaznamy_prijem
            cur.execute("""
                INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, nakupna_cena_eur_kg, poznamka, dodavatel)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (WAREHOUSE_PROD, pid, doc_date, str(qty), str(price), f"{note} #{doc_no}", str(supplier_id)))

            # 2) prepočet WMA do sklad_polozky
            cur.execute("""
                SELECT id, mnozstvo, priemerna_cena
                FROM sklad_polozky
                WHERE sklad_id=%s AND produkt_id=%s
                FOR UPDATE
            """, (WAREHOUSE_PROD, pid))
            rec = cur.fetchone()
            old_qty = _d(rec["mnozstvo"]) if rec else Decimal('0')
            old_avg = _d(rec["priemerna_cena"]) if rec else Decimal('0')
            new_qty = old_qty + qty
            new_avg = old_avg
            if new_qty > 0:
                new_avg = (old_qty * old_avg + qty * price) / new_qty

            if rec:
                cur.execute("UPDATE sklad_polozky SET mnozstvo=%s, priemerna_cena=%s WHERE id=%s",
                            (str(new_qty.quantize(Decimal('0.001'))),
                             str(new_avg.quantize(Decimal('0.01'))),
                             rec["id"]))
            else:
                cur.execute("""
                    INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena)
                    VALUES (%s, %s, %s, %s)
                """, (WAREHOUSE_PROD, pid,
                      str(qty.quantize(Decimal('0.001'))),
                      str(price.quantize(Decimal('0.01')))))

            # 3) movement – príjem
            cur.execute("""
                INSERT INTO inventory_movements
                  (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
                VALUES (NOW(6), %s, %s, %s, %s, %s, %s, %s, %s)
            """, (WAREHOUSE_PROD, pid,
                  str(qty.quantize(Decimal('0.001'))),
                  str(price.quantize(Decimal('0.01'))),
                  1,  # MOVEMENT_IN
                  'zaznamy_prijem', 0,  # nemáme header_id, použijeme 0
                  f"dod:{supplier_id} {doc_no} {note}".strip()))

            # 4) zapíš last_price pre supplier/product
            cur.execute("""
                UPDATE product_suppliers
                   SET last_price=%s
                 WHERE supplier_id=%s AND product_id=%s
            """, (str(price.quantize(Decimal('0.0001'))), supplier_id, pid))

        conn.commit()
        return {"message": f"Príjem uložený. Doklad: {doc_no}", "doc_no": doc_no, "count": len(clean)}
    except Exception as ex:
        if conn: conn.rollback()
        return {"error": f"Uloženie príjmu zlyhalo: {ex}"}
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()
