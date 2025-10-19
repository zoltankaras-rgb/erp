# -*- coding: utf-8 -*-
from typing import Any, Dict, Optional
from flask import request, session
import db_connector as db

def _get_first_production_warehouse_id() -> int:
    row = db.execute_query("SELECT id FROM warehouses WHERE typ IN (0,'vyrobny') ORDER BY id LIMIT 1", fetch='one')
    if not row:
        raise Exception("V DB chýba výrobný sklad (warehouses.typ=0).")
    return list(row.values())[0]

def _get_first_central_warehouse_id() -> int:
    row = db.execute_query("SELECT id FROM warehouses WHERE typ IN (1,'centralny') ORDER BY id LIMIT 1", fetch='one')
    if not row:
        raise Exception("V DB chýba centrálny sklad (warehouses.typ=1).")
    return list(row.values())[0]

def _get_user_id_for_audit() -> int:
    try:
        user = session.get('user') or {}
        uid = user.get('id')
        return int(uid) if uid else 1
    except Exception:
        return 1

def _find_product_by_ean(ean: str) -> Optional[Dict[str, Any]]:
    return db.execute_query("SELECT id, ean, nazov FROM products WHERE ean=%s", (ean,), fetch='one')

def get_production_stock_overview():
    w_id = _get_first_production_warehouse_id()
    body = request.json or {}
    filter_names = body.get('category_names')

    params = [w_id]
    where_cat = ""
    if filter_names:
        where_cat = "WHERE COALESCE(pc.name,'') IN (" + ",".join(["%s"]*len(filter_names)) + ")"
        params.extend(filter_names)

    q = f"""
    SELECT
      pc.name AS kategoria,
      p.id, p.ean, p.nazov, p.typ, p.jednotka, p.min_zasoba, p.dph, p.je_vyroba,
      COALESCE(sp.mnozstvo,0) AS mnozstvo,
      COALESCE(sp.priemerna_cena,0) AS priemerna_cena
    FROM products p
    LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
    LEFT JOIN sklad_polozky sp ON sp.produkt_id = p.id AND sp.sklad_id = %s
    {where_cat}
    ORDER BY pc.name, p.nazov
    """
    rows = db.execute_query(q, tuple(params), fetch='all') or []
    lows = [r for r in rows if float(r.get('mnozstvo') or 0) < float(r.get('min_zasoba') or 0)]
    return { "warehouse_id": w_id, "items": rows, "lowStock": lows }

def receive_production_items():
    body = request.json or {}
    items = body.get('items') or []
    if not items:
        return {"error": "Chýbajú položky na príjem."}

    w_id = _get_first_production_warehouse_id()
    actor = _get_user_id_for_audit()

    supplier_id = None
    sup = items[0].get('supplier') if items else None
    if sup and sup.get('name'):
        row = db.execute_query("SELECT id FROM suppliers WHERE name=%s", (sup['name'],), fetch='one')
        if row:
            supplier_id = list(row.values())[0]
        else:
            supplier_id = db.execute_query(
                "INSERT INTO suppliers(name,ico,email,phone,address,note) VALUES(%s,%s,%s,%s,%s,%s)",
                (sup.get('name'), sup.get('ico'), sup.get('email'), sup.get('phone'), sup.get('address'), sup.get('note')),
                fetch='lastrowid'
            )

    for it in items:
        ean = it.get('ean')
        qty = float(it.get('qty') or 0)
        unit_cost = float(it.get('unit_cost') or 0)
        if not ean or qty <= 0:
            continue
        prod = _find_product_by_ean(ean)
        if not prod:
            continue
        pid = prod['id']

        try:
            db.execute_query("CALL sp_inventory_receipt(%s,%s,%s,%s,%s,%s)",
                             (actor, w_id, pid, qty, unit_cost, "PRIJEM - kancelaria"), fetch=None)
        except Exception:
            db.execute_query("""
                INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena)
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                   priemerna_cena = CASE
                       WHEN (sklad_polozky.mnozstvo + VALUES(mnozstvo)) <= 0 THEN 0
                       ELSE ROUND(((sklad_polozky.mnozstvo * sklad_polozky.priemerna_cena) + (VALUES(mnozstvo) * VALUES(priemerna_cena))) / (sklad_polozky.mnozstvo + VALUES(mnozstvo)), 4)
                   END,
                   mnozstvo = sklad_polozky.mnozstvo + VALUES(mnozstvo)
            """, (w_id, pid, qty, unit_cost))
            db.execute_query("""
                INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
                VALUES (%s,%s,%s,%s,0,'kancelaria_prijem',NULL,%s)
            """, (w_id, pid, qty, unit_cost, "PRIJEM - kancelaria"))

        if supplier_id:
            db.execute_query("""
                INSERT INTO product_suppliers(product_id, supplier_id, last_price, preferred)
                VALUES(%s,%s,%s,1)
                ON DUPLICATE KEY UPDATE last_price=VALUES(last_price), preferred=1
            """, (pid, supplier_id, unit_cost))

    return {"message": "Príjem bol zaevidovaný.", "warehouse_id": w_id}

def manual_writeoff():
    body = request.json or {}
    ean = body.get('ean')
    qty = float(body.get('qty') or 0)
    reason_code = int(body.get('reason_code') or 4)
    reason_text = body.get('reason_text') or ''
    signature_text = body.get('signature_text') or None

    if not ean or qty <= 0:
        return {"error": "Chýba EAN alebo množstvo."}

    prod = _find_product_by_ean(ean)
    if not prod:
        return {"error": "Produkt s daným EAN neexistuje."}

    actor = _get_user_id_for_audit()
    w_id = _get_first_production_warehouse_id()

    try:
        db.execute_query("CALL sp_manual_writeoff(%s,%s,%s,%s,%s,%s,%s)",
                         (actor, w_id, prod['id'], qty, reason_code, reason_text, signature_text), fetch=None)
    except Exception:
        row = db.execute_query("SELECT priemerna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
                               (w_id, prod['id']), fetch='one')
        avg = float(list(row.values())[0]) if row else 0.0
        db.execute_query("UPDATE sklad_polozky SET mnozstvo = GREATEST(0, mnozstvo - %s) WHERE sklad_id=%s AND produkt_id=%s",
                         (qty, w_id, prod['id']))
        db.execute_query("""
            INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
            VALUES (%s,%s,%s,%s,%s,'manual_writeoff',NULL,%s)
        """, (w_id, prod['id'], -qty, avg, reason_code, reason_text))
        db.execute_query("""
            INSERT INTO writeoff_logs(sklad_id, produkt_id, qty, reason_code, reason_text, actor_user_id, signature_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (w_id, prod['id'], qty, reason_code, reason_text, actor, signature_text))
    return {"message": "Odpis bol zaevidovaný.", "warehouse_id": w_id}

def get_catalog_management_data():
    products = db.execute_query("""
        SELECT
          p.id, p.ean, p.nazov, p.typ,
          COALESCE(pc.name,'') AS kategoria,
          p.kategoria_id, p.jednotka, p.min_zasoba, p.dph, p.je_vyroba, p.parent_id
        FROM products p
        LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
        ORDER BY p.nazov
    """, fetch='all') or []

    categories = db.execute_query("SELECT id, name FROM product_categories ORDER BY name", fetch='all') or []
    sales_cats = db.execute_query("SELECT id, name FROM sales_categories ORDER BY name", fetch='all') or []
    suppliers = db.execute_query("SELECT id, name, ico, email, phone FROM suppliers ORDER BY name", fetch='all') or []

    return { "products": products, "categories": categories, "salesCategories": sales_cats, "suppliers": suppliers }

def save_catalog_product():
    body = request.json or {}
    pid = body.get('id')
    fields = ['ean','nazov','typ','jednotka','kategoria_id','min_zasoba','dph','je_vyroba','parent_id']
    vals = [body.get(k) for k in fields]

    if pid:
        set_clause = ", ".join([f"{k}=%s" for k in fields])
        db.execute_query(f"UPDATE products SET {set_clause} WHERE id=%s", tuple(vals+[pid]))
    else:
        placeholders = ",".join(["%s"]*len(fields))
        new_id = db.execute_query(f"INSERT INTO products({','.join(fields)}) VALUES({placeholders})", tuple(vals), fetch='lastrowid')
        pid = new_id

    sc_ids = body.get('sales_category_ids') or []
    if sc_ids and pid:
        db.execute_query("DELETE FROM product_sales_categories WHERE product_id=%s", (pid,))
        for sid in sc_ids:
            db.execute_query("INSERT INTO product_sales_categories(product_id, sales_category_id) VALUES(%s,%s)", (pid, sid))

    supp = (body.get('supplier') or {}).get('id')
    if supp and pid:
        db.execute_query("""
            INSERT INTO product_suppliers(product_id, supplier_id, preferred)
            VALUES(%s,%s,1)
            ON DUPLICATE KEY UPDATE preferred=1
        """, (pid, supp))

    return {"message": "Produkt uložený.", "id": pid}

def save_catalog_category():
    body = request.json or {}
    cid = db.execute_query("INSERT INTO product_categories(name) VALUES(%s)", (body.get('name'),), fetch='lastrowid')
    return {"message": "Kategória pridaná.", "id": cid}

def save_sales_category():
    body = request.json or {}
    sid = db.execute_query("INSERT INTO sales_categories(name) VALUES(%s)", (body.get('name'),), fetch='lastrowid')
    return {"message": "Predajná kategória pridaná.", "id": sid}

def save_supplier():
    body = request.json or {}
    fields = ['name','ico','dic','ic_dph','email','phone','address','note']
    vals = [body.get(k) for k in fields]
    sid = db.execute_query(f"INSERT INTO suppliers({','.join(fields)}) VALUES({','.join(['%s']*len(fields))})", tuple(vals), fetch='lastrowid')
    return {"message": "Dodávateľ pridaný.", "id": sid}
