from stock_utils import update_stock
from validators import validate_required_fields, safe_get_float, safe_get_int
from logger import logger
import db_connector
from datetime import datetime, timedelta
import math
import re
import json
from flask import request, render_template, make_response
import production_handler
import notification_handler
import b2b_handler
# === mentor patch: helpers for DB compatibility ===
from typing import Optional

import db_connector  # uprav podľa svojho projektu, ak treba
# === helpers (vloz nad funkcie) ===
import db_connector
from typing import Optional

def _has_table(table: str) -> bool:
    rows = db_connector.execute_query(
        "SELECT COUNT(*) AS n FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name=%s", (table,)
    ) or []
    return bool(rows and (rows[0].get('n') or rows[0].get('N') or rows[0].get('COUNT(*)')))

def _has_column(table: str, column: str) -> bool:
    rows = db_connector.execute_query(
        "SELECT COUNT(*) AS n FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name=%s AND column_name=%s",
        (table, column)
    ) or []
    return bool(rows and (rows[0].get('n') or rows[0].get('N') or rows[0].get('COUNT(*)')))

def _pick_col(table: str, candidates: list[str], default: Optional[str] = None) -> Optional[str]:
    for c in candidates:
        if _has_column(table, c):
            return c
    return default
# === /helpers ===

def _has_column(table: str, column: str) -> bool:
    sql = (
        "SELECT COUNT(*) AS n FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name=%s AND column_name=%s"
    )
    row = db_connector.execute_query(sql, (table, column), 'one')
    return bool(row and row.get('n'))

def _detect_price_col_in(table: str) -> Optional[str]:
    # Skúsime najbežnejšie názvy; vrátime prvý, čo existuje
    for col in ('priemerna_cena', 'nakupna_cena', 'cena', 'unit_price'):
        if _has_column(table, col):
            return col
    return None
# === /mentor patch ===
# === mentor patch: helpers ===
def _pick_col(table: str, candidates: list[str], default: str | None = None) -> str | None:
    for c in candidates:
        if _has_column(table, c):
            return c
    return default
# === /mentor patch ===

# -------------------------------------------------------------------
# Pomocné utilitky pre robustnosť voči rozdielnym schémam/tabuľkám
# -------------------------------------------------------------------

def _has_table(table_name: str) -> bool:
    row = db_connector.execute_query(
        """
        SELECT 1
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s
        LIMIT 1
        """,
        (table_name,), 'one'
    )
    return bool(row)

def _has_column(table_name: str, col_name: str) -> bool:
    row = db_connector.execute_query(
        """
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
        LIMIT 1
        """,
        (table_name, col_name), 'one'
    )
    return bool(row)

def _detect_receive_price_column() -> str | None:
    """
    Vráti názov stĺpca s cenou v 'zaznamy_prijem' podľa toho, čo v DB existuje.
    Preferencia zodpovedá tvojej schéme (nakupna_cena_eur_kg == primárne).
    """
    for c in ('nakupna_cena_eur_kg', 'nakupna_cena', 'cena', 'price'):
        if _has_column('zaznamy_prijem', c):
            return c
    return None


# =================================================================
# === DASHBOARD / KANCELÁRIA ===
# =================================================================


def get_kancelaria_dashboard_data():
    """
    Kompletné dáta pre Dashboard (Kancelária):
    - nízke zásoby: suroviny (výrobný), hotové/tovar (centrálny)
    - posledné príjmy, posledné výrobné dávky (robustné na názvy stĺpcov)
    - B2B/B2C posledné objednávky + nové registrácie
    - KPI počty (B2B,B2C v aktuálnom mesiaci, produkty bez receptu, počet kategórií receptov)
    - TOP 5 výrobkov (30 dní), časová séria výroby (30 dní)
    """
    # ------------------------ LOW STOCKS ------------------------
    sql_low_raw = """
        SELECT p.id, p.nazov, p.kategoria, p.jednotka,
               COALESCE(p.min_zasoba,0)     AS min_zasoba,
               COALESCE(SUM(sp.mnozstvo),0) AS qty
        FROM sklad_polozky sp
        JOIN sklady_ext   s ON s.id = sp.sklad_id
        JOIN produkty_ext p ON p.id = sp.produkt_id
        WHERE s.typ = 'vyrobny' AND p.typ = 'surovina'
        GROUP BY p.id, p.nazov, p.kategoria, p.jednotka, p.min_zasoba
        HAVING qty < p.min_zasoba
        ORDER BY p.kategoria, p.nazov
        LIMIT 100
    """
    low_raw_rows = db_connector.execute_query(sql_low_raw) or []

    sql_low_final = """
        SELECT p.id, p.nazov, p.kategoria, p.jednotka, p.typ,
               COALESCE(p.min_zasoba,0)     AS min_zasoba,
               COALESCE(SUM(sp.mnozstvo),0) AS qty
        FROM sklad_polozky sp
        JOIN sklady_ext   s ON s.id = sp.sklad_id
        JOIN produkty_ext p ON p.id = sp.produkt_id
        WHERE s.typ = 'centralny' AND p.typ <> 'surovina'
        GROUP BY p.id, p.nazov, p.kategoria, p.jednotka, p.typ, p.min_zasoba
        HAVING qty < p.min_zasoba
        ORDER BY p.kategoria, p.nazov
        LIMIT 200
    """
    low_final_rows = db_connector.execute_query(sql_low_final) or []

    low_goods_grouped = {}
    for r in low_final_rows:
        cat = (r.get('kategoria') or 'Nezaradené')
        low_goods_grouped.setdefault(cat, []).append({
            "produkt_id": r["id"],
            "name":       r["nazov"],
            "category":   cat,
            "quantity":   float(r.get("qty") or 0),
            "minStock":   float(r.get("min_zasoba") or 0),
            "unit":       r.get("jednotka") or ""
        })

    # ------------------------ RECEIVES (optional) ------------------------
    recent_receives = []
    try:
        price_col = _detect_price_col_in('zaznamy_prijem') if 'zaznamy_prijem' else None
        price_expr = f"zp.{price_col}" if price_col else "NULL"
        sql_receives = f"""
            SELECT zp.id, zp.datum, p.nazov, zp.mnozstvo, {price_expr} AS cena,
                   zp.dodavatel, s.nazov AS sklad
            FROM zaznamy_prijem zp
            JOIN produkty_ext p ON p.id = zp.produkt_id
            LEFT JOIN sklady_ext s ON s.id = zp.sklad_id
            ORDER BY zp.datum DESC
            LIMIT 10
        """
        recent_receives = db_connector.execute_query(sql_receives) or []
    except Exception:
        recent_receives = []

    # ------------------------ BATCHES (robustné) ------------------------
    recent_batches = []
    try:
        real_col = _pick_col('zaznamy_vyroba', ['skutocne_vyrobene','realne_mnozstvo','vyrobene_mnozstvo','mnozstvo_skutocne','mnozstvo'])
        plan_col = 'planovane_mnozstvo' if _has_column('zaznamy_vyroba','planovane_mnozstvo') else None
        qty_expr = f"COALESCE(zv.{real_col}, zv.{plan_col})" if (real_col and plan_col) else (f"zv.{real_col}" if real_col else (f"zv.{plan_col}" if plan_col else "NULL"))
        date_col = _pick_col('zaznamy_vyroba', ['datum_vyroby','datum_ukoncenia','datum','created_at','updated_at'])
        join_col = _pick_col('zaznamy_vyroba', ['vyrobok_id','produkt_id','product_id'])
        date_expr = f"zv.{date_col} AS datum_vyroby" if date_col else "NULL AS datum_vyroby"
        stav_expr = "zv.stav" if _has_column('zaznamy_vyroba','stav') else "NULL"
        join_expr = f"JOIN produkty_ext p ON p.id = zv.{join_col}" if join_col else "LEFT JOIN produkty_ext p ON 1=0"
        sql_recent_batches = f"""
            SELECT zv.id, {date_expr}, p.nazov, {('zv.'+plan_col) if plan_col else 'NULL'} AS planovane_mnozstvo,
                   {qty_expr} AS realne_mnozstvo, {stav_expr} AS stav
            FROM zaznamy_vyroba zv
            {join_expr}
            ORDER BY datum_vyroby DESC
            LIMIT 10
        """
        recent_batches = db_connector.execute_query(sql_recent_batches) or []
    except Exception:
        recent_batches = []

    # ------------------------ ORDERS & REGISTRATIONS ------------------------
    b2b_orders = []
    if _has_table('b2b_objednavky'):
        b2b_orders = db_connector.execute_query("""
            SELECT o.id, o.cislo_objednavky, o.datum_objednavky, o.pozadovany_datum_dodania,
                   o.celkova_suma, o.status, z.nazov_firmy
            FROM b2b_objednavky o
            LEFT JOIN b2b_zakaznici z ON z.id = o.zakaznik_id
            ORDER BY o.datum_objednavky DESC
            LIMIT 20
        """) or []

    b2c_orders = []
    if _has_table('b2c_objednavky'):
        b2c_orders = db_connector.execute_query("""
            SELECT id, datum, celkom_s_dph, body
            FROM b2c_objednavky
            ORDER BY datum DESC
            LIMIT 20
        """) or []

    new_b2b_regs = []
    if _has_table('b2b_zakaznici'):
        new_b2b_regs = db_connector.execute_query("""
            SELECT id, nazov_firmy, email, telefon, datum_registracie
            FROM b2b_zakaznici
            WHERE COALESCE(je_schvaleny,0)=0
            ORDER BY datum_registracie DESC
            LIMIT 20
        """) or []

    new_b2c_regs = []
    for cand in ('b2c_zakaznici','b2c_users','b2c_customers'):
        if _has_table(cand):
            appr  = _pick_col(cand, ['je_schvaleny','is_approved','approved'])
            namec = _pick_col(cand, ['meno','full_name','name','nazov_firmy'])
            email = _pick_col(cand, ['email','mail'])
            phone = _pick_col(cand, ['telefon','phone'])
            cdate = _pick_col(cand, ['datum_registracie','created_at','created','ts','registered_at'])
            if appr and cdate:
                sql = f"""
                    SELECT id,
                           {namec if namec else 'NULL'} AS name,
                           {email if email else 'NULL'} AS email,
                           {phone if phone else 'NULL'} AS phone,
                           {cdate} AS created_at
                    FROM {cand}
                    WHERE COALESCE({appr},0)=0
                    ORDER BY {cdate} DESC
                    LIMIT 20
                """
                new_b2c_regs = db_connector.execute_query(sql) or []
            break

    # ------------------------ KPI COUNTS ------------------------
    b2bOrdersCount = 0
    if _has_table('b2b_objednavky'):
        b2b_dt = _pick_col('b2b_objednavky', ['datum_objednavky','created_at','datum'])
        if b2b_dt:
            row = db_connector.execute_query(
                f"SELECT COUNT(*) AS c FROM b2b_objednavky WHERE YEAR({b2b_dt})=YEAR(CURDATE()) AND MONTH({b2b_dt})=MONTH(CURDATE())",
                fetch='one'
            )
            b2bOrdersCount = int(row['c']) if row else 0

    b2cOrdersCount = 0
    if _has_table('b2c_objednavky'):
        b2c_dt = _pick_col('b2c_objednavky', ['datum','datum_objednavky','created_at'])
        if b2c_dt:
            row = db_connector.execute_query(
                f"SELECT COUNT(*) AS c FROM b2c_objednavky WHERE YEAR({b2c_dt})=YEAR(CURDATE()) AND MONTH({b2c_dt})=MONTH(CURDATE())",
                fetch='one'
            )
            b2cOrdersCount = int(row['c']) if row else 0

    productsWithoutRecipeCount = 0
    recipeCategoriesCount = 0
    if _has_table('recepty'):
        row = db_connector.execute_query("""
            SELECT COUNT(*) AS c
            FROM produkty_ext p
            WHERE p.typ='vyrobok'
              AND NOT EXISTS (SELECT 1 FROM recepty r WHERE r.vyrobok_id = p.id)
        """, fetch='one')
        productsWithoutRecipeCount = int(row['c']) if row else 0

        row = db_connector.execute_query("""
            SELECT COUNT(DISTINCT p.kategoria) AS c
            FROM produkty_ext p
            WHERE p.typ='vyrobok'
              AND p.kategoria IS NOT NULL AND p.kategoria <> ''
              AND EXISTS (SELECT 1 FROM recepty r WHERE r.vyrobok_id = p.id)
        """, fetch='one')
        recipeCategoriesCount = int(row['c']) if row else 0

    # ------------------------ TOP 5 + TIMESERIES (30 dní) -------------------
    topProducts = []
    timeSeriesData = []
    try:
        since = (datetime.now().date() - timedelta(days=30))
        zv_date = _pick_col('zaznamy_vyroba', ['datum_vyroby','datum_ukoncenia','datum','created_at','updated_at'])
        zv_join = _pick_col('zaznamy_vyroba', ['vyrobok_id','produkt_id','product_id'])
        zv_real = _pick_col('zaznamy_vyroba', ['skutocne_vyrobene','realne_mnozstvo','vyrobene_mnozstvo','mnozstvo_skutocne','mnozstvo'])
        zv_plan = 'planovane_mnozstvo' if _has_column('zaznamy_vyroba','planovane_mnozstvo') else None
        qty_expr = f"COALESCE(zv.{zv_real}, zv.{zv_plan})" if (zv_real and zv_plan) else (f"zv.{zv_real}" if zv_real else (f"zv.{zv_plan}" if zv_plan else "NULL"))

        if zv_date and qty_expr:
            # timeseries bez joinu
            ts_sql = f"""
                SELECT DATE({zv_date}) AS production_date, SUM({qty_expr}) AS total_kg
                FROM zaznamy_vyroba zv
                WHERE DATE({zv_date}) >= %s
                GROUP BY DATE({zv_date})
                ORDER BY production_date
            "
            """
            # fix multiline quoting
            ts_sql = ts_sql.replace('"', '').replace("'", '"')  # neutralize quotes inside f-string assembly
            ts_sql = f"""
                SELECT DATE({zv_date}) AS production_date, SUM({qty_expr}) AS total_kg
                FROM zaznamy_vyroba zv
                WHERE DATE({zv_date}) >= %s
                GROUP BY DATE({zv_date})
                ORDER BY production_date
            """
            timeSeriesData = db_connector.execute_query(ts_sql, (since,)) or []

        if zv_date and zv_join and qty_expr:
            top_sql = f"""
                SELECT p.nazov AS name, SUM({qty_expr}) AS total
                FROM zaznamy_vyroba zv
                JOIN produkty_ext p ON p.id = zv.{zv_join}
                WHERE DATE({zv_date}) >= %s
                GROUP BY p.nazov
                ORDER BY total DESC
                LIMIT 5
            """
            topProducts = db_connector.execute_query(top_sql, (since,)) or []
    except Exception:
        pass

    # ------------------------ RETURN ------------------------
    return {
        # nízke zásoby
        "lowStockRaw": [{
            "produkt_id": r["id"],
            "name":       r["nazov"],
            "category":   r.get("kategoria") or "Nezaradené",
            "quantity":   float(r.get("qty") or 0),
            "minStock":   float(r.get("min_zasoba") or 0),
            "unit":       r.get("jednotka") or ""
        } for r in low_raw_rows],
        "lowStockGoods": low_goods_grouped,

        # posledné udalosti
        "recent_receives": recent_receives,
        "recent_batches":  recent_batches,

        # objednávky + registrácie (tabuľky)
        "b2b_orders": b2b_orders,
        "b2c_orders": b2c_orders,
        "new_b2b_regs": new_b2b_regs,
        "new_b2c_regs": new_b2c_regs,

        # KPI
        "b2bOrdersCount": b2bOrdersCount,
        "b2cOrdersCount": b2cOrdersCount,
        "productsWithoutRecipeCount": productsWithoutRecipeCount,
        "recipeCategoriesCount": recipeCategoriesCount,

        # prehľady
        "topProducts": topProducts,
        "timeSeriesData": timeSeriesData
    }

def get_kancelaria_base_data():
    """
    Základné dáta pre kanceláriu.
    - Zoznam výrobkov bez receptu (produkty.typ = 'vyrobok' a nemajú záznam v recepty)
    - Zoznam kategórií priamo z produkty.kategoria
    """
    products_without_recipe_q = """
        SELECT p.nazov
        FROM produkty p
        WHERE p.typ = 'vyrobok'
          AND p.id NOT IN (SELECT DISTINCT vyrobok_id FROM recepty)
        ORDER BY p.nazov
    """
    products_list = db_connector.execute_query(products_without_recipe_q) or []

    categories_q = """
        SELECT DISTINCT kategoria
        FROM produkty
        WHERE kategoria IS NOT NULL AND kategoria <> ''
        ORDER BY kategoria
    """
    categories_list = db_connector.execute_query(categories_q) or []

    return {
        'warehouse': production_handler.get_warehouse_state(),
        'itemTypes': ['Mäso', 'Koreniny', 'Obaly - Črevá', 'Pomocný material'],
        'productsWithoutRecipe': [p['nazov'] for p in products_list],
        'recipeCategories': [c['kategoria'] for c in categories_list]
    }


# =================================================================
# === FORECAST / PLÁNOVANIE / AKCIE ===
# =================================================================

def get_7_day_order_forecast():
    """7-dňový prehľad objednávok podľa produktov (B2B)."""
    start_date = datetime.now().date()
    dates = [start_date + timedelta(days=i) for i in range(7)]
    date_str_list = [d.strftime('%Y-%m-%d') for d in dates]
    end_date = dates[-1]

    orders_query = """
        SELECT
            p.id AS produkt_id,
            p.nazov,
            p.jednotka,
            p.kategoria,
            obj.pozadovany_datum_dodania,
            pol.mnozstvo
        FROM b2b_objednavky_polozky pol
        JOIN b2b_objednavky obj ON pol.objednavka_id = obj.id
        JOIN produkty p        ON pol.produkt_id = p.id
        WHERE DATE(obj.pozadovany_datum_dodania) BETWEEN %s AND %s
    """
    all_orders = db_connector.execute_query(orders_query, (start_date, end_date)) or []

    stock_query = """
        SELECT produkt_id, COALESCE(SUM(mnozstvo),0) AS stock
        FROM sklad_polozky
        GROUP BY produkt_id
    """
    stock_rows = db_connector.execute_query(stock_query) or []
    stock_map = {row["produkt_id"]: safe_get_float(row["stock"]) for row in stock_rows}

    forecast = {}
    for o in all_orders:
        pid = o["produkt_id"]
        dstr = o["pozadovany_datum_dodania"].strftime('%Y-%m-%d')
        if pid not in forecast:
            forecast[pid] = {
                "produkt_id": pid,
                "nazov": o["nazov"],
                "jednotka": o["jednotka"],
                "kategoria": o["kategoria"],
                "stock": stock_map.get(pid, 0.0),
                "forecast": {d: 0.0 for d in date_str_list}
            }
        forecast[pid]["forecast"][dstr] += safe_get_float(o.get("mnozstvo") or 0.0)

    return forecast


def get_goods_purchase_suggestion():
    """
    Návrh nákupu pre externý tovar (produkty.typ='externy') s ohľadom na blízke objednávky.
    """
    start = datetime.now().date()
    end   = start + timedelta(days=7)

    reserved_q = """
        SELECT p.id AS produkt_id, SUM(pol.mnozstvo) AS reserved_qty
        FROM b2b_objednavky_polozky pol
        JOIN b2b_objednavky obj ON pol.objednavka_id = obj.id
        JOIN produkty p        ON pol.produkt_id     = p.id
        WHERE DATE(obj.pozadovany_datum_dodania) BETWEEN %s AND %s
          AND p.typ = 'externy'
        GROUP BY p.id
    """
    reserved_rows = db_connector.execute_query(reserved_q, (start, end)) or []
    reserved_map = {r['produkt_id']: safe_get_float(r['reserved_qty']) for r in reserved_rows}

    goods_q = """
        SELECT p.id AS produkt_id, p.nazov, p.min_zasoba, p.jednotka,
               COALESCE(SUM(sp.mnozstvo), 0) AS aktualny_stav
        FROM produkty p
        LEFT JOIN sklad_polozky sp ON sp.produkt_id = p.id
        WHERE p.typ = 'externy'
        GROUP BY p.id, p.nazov, p.min_zasoba, p.jednotka
        ORDER BY p.nazov
    """
    all_goods = db_connector.execute_query(goods_q) or []

    out = []
    for g in all_goods:
        pid = g["produkt_id"]
        stock    = safe_get_float(g.get("aktualny_stav") or 0.0)
        min_st   = safe_get_float(g.get("min_zasoba") or 0.0)
        reserved = reserved_map.get(pid, 0.0)
        if stock - reserved < min_st:
            out.append({
                "produkt_id": pid,
                "nazov": g["nazov"],
                "jednotka": g["jednotka"],
                "stock": stock,
                "reserved": reserved,
                "min_stock": min_st,
                "suggested_qty": max(min_st - (stock - reserved), 0)
            })
    return out


def get_promotions_data():
    """Dáta pre promo kampane (retail chains + externé produkty + promo záznamy)."""
    chains = db_connector.execute_query("SELECT * FROM b2b_retail_chains ORDER BY name") or []
    products = db_connector.execute_query("""
        SELECT id AS produkt_id, ean, nazov AS name
        FROM produkty
        WHERE typ = 'externy'
        ORDER BY name
    """) or []
    promos = db_connector.execute_query("""
        SELECT pr.id, pr.chain_id, pr.produkt_id, pr.start_date, pr.end_date, pr.special_price,
               p.nazov AS produkt_nazov, c.name AS chain_name
        FROM b2b_promotions pr
        JOIN produkty p ON pr.produkt_id = p.id
        JOIN b2b_retail_chains c ON pr.chain_id = c.id
        ORDER BY pr.start_date DESC
    """) or []
    return {"chains": chains, "products": products, "promotions": promos}


def manage_promotion_chain(**data):
    """
    Správa obchodných reťazcov (add|update|delete).
    Očakáva: name, contact_person, email, phone (pri update aj id).
    """
    action = data.get("action")
    if action == "add":
        if not data.get("name"):
            return {"error": "Názov reťazca je povinný."}
        new_id = db_connector.execute_query(
            """
            INSERT INTO b2b_retail_chains (name, contact_person, email, phone)
            VALUES (%s, %s, %s, %s)
            """,
            (data.get("name"), data.get("contact_person"), data.get("email"), data.get("phone")),
            fetch="lastrowid"
        )
        return {"message": "Reťazec bol pridaný.", "id": new_id}

    elif action == "update":
        chain_id = data.get("id")
        if not chain_id:
            return {"error": "Chýba ID reťazca."}
        db_connector.execute_query(
            """
            UPDATE b2b_retail_chains
               SET name=%s, contact_person=%s, email=%s, phone=%s
             WHERE id=%s
            """,
            (data.get("name"), data.get("contact_person"), data.get("email"), data.get("phone"), chain_id),
            fetch="none"
        )
        return {"message": "Reťazec bol aktualizovaný."}

    elif action == "delete":
        chain_id = data.get("id")
        if not chain_id:
            return {"error": "Chýba ID reťazca."}
        db_connector.execute_query("DELETE FROM b2b_retail_chains WHERE id=%s", (chain_id,), fetch="none")
        return {"message": "Reťazec bol vymazaný."}

    return {"error": "Neplatná akcia."}


def save_promotion():
    """
    Ukladá promo akciu.
    Očakáva JSON: chain_id, produkt_id, start_date, end_date, sale_price_net
    """
    data = request.get_json(force=True)
    req = ['chain_id', 'produkt_id', 'start_date', 'end_date', 'sale_price_net']
    if not all(data.get(k) for k in req):
        return {"error": "Chýbajú povinné údaje."}

    db_connector.execute_query(
        """
        INSERT INTO b2b_promotions (chain_id, produkt_id, start_date, end_date, special_price, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """,
        (data['chain_id'], data['produkt_id'], data['start_date'], data['end_date'],
         safe_get_float(data['sale_price_net'])),
        fetch="none"
    )
    return {"message": "Akcia bola úspešne uložená."}


def delete_promotion():
    data = request.get_json(force=True)
    promo_id = data.get('id')
    if not promo_id:
        return {"error": "Chýba ID akcie."}
    db_connector.execute_query("DELETE FROM b2b_promotions WHERE id=%s", (promo_id,), fetch='none')
    return {"message": "Akcia bola vymazaná."}


# =================================================================
# === SKLAD / PRÍJEM / PREHĽAD ===
# =================================================================

def receive_multiple_stock_items(items):
    """Hromadný príjem surovín do výrobného skladu (sklad_id=1)."""
    if not items:
        return {"error": "Neboli poskytnuté žiadne položky na príjem."}

    sklad_id = 1
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        for item in items:
            name = item.get('name')
            qty  = safe_get_float(item.get('quantity') or 0)
            price = safe_get_float(item.get('price') or 0)
            date = item.get('date') or datetime.now()
            note = item.get('note') or ''

            if not name or qty <= 0:
                continue

            produkt = db_connector.execute_query(
                "SELECT id FROM produkty WHERE nazov=%s AND typ='surovina'",
                (name,), 'one'
            )
            if not produkt:
                continue
            produkt_id = produkt['id']

            # Zápis príjmu
            cursor.execute("""
                INSERT INTO zaznamy_prijem
                    (sklad_id, produkt_id, datum, mnozstvo, nakupna_cena_eur_kg, poznamka, dodavatel)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (sklad_id, produkt_id, date, qty, price, note, note))

            # Update/Average sklad_polozky
            cursor.execute(
                "SELECT id, mnozstvo, nakupna_cena FROM sklad_polozky WHERE sklad_id=%s AND produkt_id=%s",
                (sklad_id, produkt_id)
            )
            sklad_item = cursor.fetchone()
            if sklad_item:
                old_qty   = safe_get_float(sklad_item['mnozstvo'] or 0)
                old_price = safe_get_float(sklad_item['nakupna_cena'] or 0)
                new_qty   = old_qty + qty
                new_avg   = (old_qty * old_price + qty * price) / new_qty if new_qty > 0 else price
                cursor.execute(
                    "UPDATE sklad_polozky SET mnozstvo=%s, nakupna_cena=%s WHERE id=%s",
                    (new_qty, new_avg, sklad_item['id'])
                )
            else:
                cursor.execute(
                    "INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, nakupna_cena) VALUES (%s, %s, %s, %s)",
                    (sklad_id, produkt_id, qty, price)
                )

        conn.commit()
        return {"message": f"Úspešne prijatých {len(items)} položiek na sklad."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


# === mentor patch: comprehensive stock view (optional) ===
def get_comprehensive_stock_view():
    price_col = _detect_price_col_in('sklad_polozky')  # typicky 'priemerna_cena'
    price_expr = f"sp.{price_col}" if price_col else "NULL"

    sql = f"""
        SELECT s.nazov AS sklad,
               p.id   AS produkt_id,
               p.nazov AS produkt,
               p.typ,
               p.kategoria,
               p.jednotka,
               sp.mnozstvo,
               {price_expr} AS cena
        FROM sklad_polozky sp
        JOIN produkty_ext p ON p.id = sp.produkt_id
        JOIN sklady_ext   s ON s.id = sp.sklad_id
        ORDER BY s.nazov, p.kategoria, p.nazov
    """
    rows = db_connector.execute_query(sql) or []

    groups = {}
    for r in rows:
        key = f"{r['sklad']} - {r.get('kategoria') or 'Nezaradené'}"
        groups.setdefault(key, []).append({
            "produkt_id": r["produkt_id"],
            "name":       r["produkt"],
            "category":   r.get("kategoria") or "Nezaradené",
            "quantity":   float(r.get("mnozstvo") or 0),
            "unit":       r.get("jednotka") or "",
            "price":      float(r.get("cena") or 0)
        })
    return {"groups": groups}
# === /mentor patch ===


def get_raw_materials_stock():
    """Sumár surovín podľa kategórií."""
    rows = db_connector.execute_query("""
        SELECT p.nazov AS name, p.kategoria,
               COALESCE(SUM(sp.mnozstvo), 0)     AS mnozstvo,
               COALESCE(AVG(sp.nakupna_cena), 0) AS nakupna_cena
        FROM sklad_polozky sp
        JOIN produkty p ON sp.produkt_id = p.id
        WHERE p.typ = 'surovina'
        GROUP BY p.id, p.nazov, p.kategoria
        ORDER BY p.kategoria, p.nazov
    """) or []
    out = {}
    for r in rows:
        cat = r.get("kategoria") or "Nezaradené"
        out.setdefault(cat, []).append({
            "name": r["name"],
            "quantity": float(r.get("mnozstvo") or 0),
            "price": float(r.get("nakupna_cena") or 0)
        })
    return out


# =================================================================
# === VÝROBA / PLÁN ===
# =================================================================

def calculate_production_plan():
    """
    Jednoduchý plán výroby: dopyt z B2B najbližších 7 dní + minimálna zásoba – aktuálny sklad.
    Výstup zoskupený podľa kategórií.
    """
    end_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

    ordered_rows = db_connector.execute_query("""
        SELECT pol.produkt_id, SUM(pol.mnozstvo) AS total_ordered_qty
        FROM b2b_objednavky obj
        JOIN b2b_objednavky_polozky pol ON obj.id = pol.objednavka_id
        WHERE DATE(obj.pozadovany_datum_dodania) BETWEEN CURDATE() AND %s
        GROUP BY pol.produkt_id
    """, (end_date,)) or []
    ordered_map = {r['produkt_id']: safe_get_float(r['total_ordered_qty']) for r in ordered_rows}

    products_to_plan = db_connector.execute_query("""
        SELECT p.id AS produkt_id, p.nazov, p.kategoria, COALESCE(p.min_zasoba,0) AS min_zasoba
        FROM produkty p
        WHERE p.typ = 'vyrobok'
        ORDER BY p.kategoria, p.nazov
    """) or []

    sklad_rows = db_connector.execute_query("""
        SELECT produkt_id, SUM(mnozstvo) AS aktualny_stav
        FROM sklad_polozky
        GROUP BY produkt_id
    """) or []
    sklad_map = {r['produkt_id']: safe_get_float(r['aktualny_stav'] or 0.0) for r in sklad_rows}

    plan = []
    for p in products_to_plan:
        pid   = p['produkt_id']
        sklad = sklad_map.get(pid, 0.0)
        minz  = safe_get_float(p.get('min_zasoba') or 0.0)
        dopyt = ordered_map.get(pid, 0.0)
        need  = (dopyt + minz) - sklad
        if need > 0:
            dávka = 50.0
            navrh = math.ceil(need / dávka) * dávka
            plan.append({
                "produkt_id": pid,
                "nazov": p['nazov'],
                "kategoria": p.get('kategoria') or 'Nezaradené',
                "aktualny_sklad": sklad,
                "celkova_potreba": dopyt + minz,
                "navrhovana_vyroba": navrh,
                "datum_vyroby": datetime.now().strftime('%Y-%m-%d')
            })

    plan_grouped = {}
    for it in plan:
        plan_grouped.setdefault(it['kategoria'], []).append(it)
    return plan_grouped


def create_production_tasks_from_plan(plan):
    """
    Vytvorí výrobné úlohy v 'zaznamy_vyroba'.
    Očakáva list dictov s kľúčmi:
      - produkt_id (alebo nazov/nazov_vyrobku -> dohľadá sa ID),
      - navrhovana_vyroba,
      - datum_vyroby (YYYY-MM-DD)
    """
    if not plan:
        return {"message": "Plán je prázdny."}

    conn = db_connector.get_connection()
    created = 0
    try:
        cur = conn.cursor()
        for it in plan:
            pid = it.get('produkt_id')
            if not pid:
                # fallback dohľadanie podľa názvu
                pname = it.get('nazov') or it.get('nazov_vyrobku')
                if not pname:
                    continue
                row = db_connector.execute_query("SELECT id FROM produkty WHERE nazov=%s", (pname,), 'one')
                if not row:
                    continue
                pid = row['id']

            qty = safe_get_float(it.get('navrhovana_vyroba') or it.get('planovane_mnozstvo') or 0.0)
            if qty <= 0:
                continue
            d = it.get('datum_vyroby') or datetime.now().strftime('%Y-%m-%d')

            cur.execute("""
                INSERT INTO zaznamy_vyroba
                    (vyrobok_id, datum_vyroby, planovane_mnozstvo, stav)
                VALUES (%s, %s, %s, 'Prijate')
            """, (pid, d, qty))
            created += 1

        conn.commit()
        return {"message": f"Vytvorených {created} výrobných úloh."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_purchase_suggestions():
    """Suroviny pod minimom (produkty.typ='surovina')."""
    return db_connector.execute_query("""
        SELECT 
            p.id        AS produkt_id,
            p.nazov,
            p.kategoria,
            p.jednotka,
            COALESCE(p.min_zasoba,0)                     AS min_zasoba,
            COALESCE(SUM(sp.mnozstvo), 0)                AS current_qty,
            (COALESCE(p.min_zasoba,0) - COALESCE(SUM(sp.mnozstvo),0)) AS needed
        FROM produkty p
        LEFT JOIN sklad_polozky sp ON sp.produkt_id = p.id
        WHERE p.typ = 'surovina'
        GROUP BY p.id, p.nazov, p.kategoria, p.jednotka, p.min_zasoba
        HAVING COALESCE(SUM(sp.mnozstvo),0) < COALESCE(p.min_zasoba,0)
        ORDER BY needed DESC
        LIMIT 20
    """) or []


# =================================================================
# === KATALÓG PRODUKTOV ===
# =================================================================

def add_new_raw_material(**data):
    """Pridá novú surovinu do 'produkty'."""
    name = data.get('nazov')
    kategoria = data.get('kategoria')
    jednotka = data.get('jednotka')
    if not name or not kategoria or not jednotka:
        return {"error": "Názov, kategória a jednotka sú povinné."}

    exists = db_connector.execute_query(
        "SELECT id FROM produkty WHERE nazov=%s AND typ='surovina'", (name,), 'one'
    )
    if exists:
        return {"error": f"Surovina '{name}' už existuje."}

    new_id = db_connector.execute_query("""
        INSERT INTO produkty (ean, nazov, typ, jednotka, kategoria, je_vyroba, min_zasoba, dph)
        VALUES (%s, %s, 'surovina', %s, %s, 0, %s, 0.00)
    """, (data.get('ean'), name, jednotka, kategoria, safe_get_float(data.get('min_zasoba', 0))), 'lastrowid')
    return {"message": f"Surovina '{name}' bola pridaná.", "produkt_id": new_id}


def get_catalog_management_data(**kwargs):
    """Dáta pre správu katalógu."""
    products = db_connector.execute_query("""
        SELECT id, ean, nazov, typ, kategoria, jednotka, min_zasoba, dph, je_vyroba, parent_id
        FROM produkty
        ORDER BY typ, nazov
    """) or []
    item_types = ['surovina', 'vyrobok', 'krajaný', 'externy']
    dph_rates = [0.00, 5.00, 10.00, 20.00]
    categories = ['mäso', 'koreniny', 'obaly', 'pomocný', 'ostatné']
    return {"products": products, "item_types": item_types, "dph_rates": dph_rates, "categories": categories}


def add_catalog_item(**data):
    """Pridá novú položku do 'produkty'."""
    ean      = data.get('ean')
    nazov    = data.get('nazov')
    item_typ = data.get('typ')
    jednotka = data.get('jednotka')
    kategoria = data.get('kategoria')
    dph      = safe_get_float(data.get('dph', 0.0))
    min_zasoba = safe_get_float(data.get('min_zasoba', 0))

    if not all([nazov, item_typ, jednotka, kategoria]):
        return {"error": "Názov, typ, jednotka a kategória sú povinné."}

    if ean and db_connector.execute_query("SELECT id FROM produkty WHERE ean=%s", (ean,), 'one'):
        return {"error": f"EAN '{ean}' už existuje."}
    if db_connector.execute_query("SELECT id FROM produkty WHERE nazov=%s", (nazov,), 'one'):
        return {"error": f"Názov '{nazov}' už existuje."}

    new_id = db_connector.execute_query("""
        INSERT INTO produkty (ean, nazov, typ, jednotka, kategoria, je_vyroba, min_zasoba, dph)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (ean, nazov, item_typ, jednotka, kategoria, 1 if item_typ == 'vyrobok' else 0, min_zasoba, dph),
       'lastrowid')
    return {"message": f"Položka '{nazov}' bola pridaná.", "produkt_id": new_id}


def update_catalog_item(**data):
    """Aktualizuje položku v 'produkty' podľa id."""
    produkt_id = data.get('id')
    if not produkt_id:
        return {"error": "Chýba ID produktu."}
    db_connector.execute_query("""
        UPDATE produkty
           SET ean=%s, nazov=%s, typ=%s, jednotka=%s,
               kategoria=%s, min_zasoba=%s, dph=%s, je_vyroba=%s
         WHERE id=%s
    """, (data.get('ean'), data.get('nazov'), data.get('typ'), data.get('jednotka'),
          data.get('kategoria'), safe_get_float(data.get('min_zasoba', 0)),
          safe_get_float(data.get('dph', 0.0)),
          1 if data.get('typ') == 'vyrobok' else 0, produkt_id),
       'none')
    return {"message": f"Položka {produkt_id} aktualizovaná."}


def delete_catalog_item(**data):
    """Vymaže produkt z 'produkty', ak nie je v recepte a nie je parent pre krájané."""
    produkt_id = data.get('id')
    if not produkt_id:
        return {"error": "Chýba ID produktu."}

    if db_connector.execute_query("SELECT id FROM recepty WHERE vyrobok_id=%s LIMIT 1", (produkt_id,), 'one'):
        return {"error": "Nemožno vymazať – produkt je použitý v recepte."}
    if db_connector.execute_query("SELECT id FROM produkty WHERE parent_id=%s LIMIT 1", (produkt_id,), 'one'):
        return {"error": "Nemožno vymazať – produkt je zdrojom pre krájaný produkt."}

    db_connector.execute_query("DELETE FROM produkty WHERE id=%s", (produkt_id,), 'none')
    return {"message": f"Položka {produkt_id} bola vymazaná."}


# =================================================================
# === RECEPTY ===
# =================================================================

def add_new_recipe(recipe_data):
    vyrobok_id = recipe_data.get('vyrobok_id')
    ingredients = recipe_data.get('ingredients')
    if not vyrobok_id or not ingredients:
        return {"error": "Chýba výrobok alebo suroviny."}

    if db_connector.execute_query("SELECT id FROM recepty WHERE vyrobok_id=%s LIMIT 1", (vyrobok_id,), 'one'):
        return {"error": "Recept pre tento výrobok už existuje."}

    rows = [(vyrobok_id, ing['surovina_id'], safe_get_float(ing['quantity']))
            for ing in ingredients
            if ing.get('surovina_id') and safe_get_float(ing.get('quantity', 0)) > 0]

    if not rows:
        return {"error": "Recept neobsahuje platné suroviny."}

    conn = db_connector.get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO recepty (vyrobok_id, surovina_id, mnozstvo_na_davku) VALUES (%s, %s, %s)",
            rows
        )
        conn.commit()
        return {"message": "Recept bol vytvorený."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_recipes_for_editing():
    return db_connector.execute_query("""
        SELECT r.vyrobok_id, p.nazov AS vyrobok, COUNT(r.id) AS ingredient_count
        FROM recepty r
        JOIN produkty p ON p.id = r.vyrobok_id
        GROUP BY r.vyrobok_id, p.nazov
        ORDER BY p.nazov
    """) or []


def get_recipe_details(vyrobok_id):
    if not vyrobok_id:
        return {"error": "Chýba ID výrobku."}
    ingredients = db_connector.execute_query("""
        SELECT r.id, s.id AS surovina_id, s.nazov AS surovina, r.mnozstvo_na_davku
        FROM recepty r
        JOIN produkty s ON s.id = r.surovina_id
        WHERE r.vyrobok_id = %s
    """, (vyrobok_id,)) or []
    if not ingredients:
        return {"error": "Recept nebol nájdený."}
    return {"vyrobok_id": vyrobok_id, "ingredients": ingredients}


def update_recipe(recipe_data):
    vyrobok_id = recipe_data.get('vyrobok_id')
    ingredients = recipe_data.get('ingredients', [])
    if not vyrobok_id:
        return {"error": "Chýba ID výrobku."}

    conn = db_connector.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM recepty WHERE vyrobok_id=%s", (vyrobok_id,))
        rows = [(vyrobok_id, ing['surovina_id'], safe_get_float(ing['quantity']))
                for ing in ingredients
                if ing.get('surovina_id') and safe_get_float(ing.get('quantity', 0)) > 0]
        if rows:
            cur.executemany(
                "INSERT INTO recepty (vyrobok_id, surovina_id, mnozstvo_na_davku) VALUES (%s, %s, %s)",
                rows
            )
        conn.commit()
        return {"message": "Recept bol aktualizovaný."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def delete_recipe(vyrobok_id):
    if not vyrobok_id:
        return {"error": "Chýba ID výrobku."}
    db_connector.execute_query("DELETE FROM recepty WHERE vyrobok_id=%s", (vyrobok_id,), 'none')
    return {"message": f"Recept pre produkt {vyrobok_id} bol vymazaný."}


# =================================================================
# === KRÁJANÉ PRODUKTY (väzba parent -> krajaný) ===
# =================================================================

def get_slicing_management_data():
    """
    Zdrojové produkty: produkty.typ='vyrobok'
    Neprepojené krájané: produkty.typ='krajaný' a parent_id IS NULL
    """
    sources = db_connector.execute_query("""
        SELECT id, ean, nazov AS name
        FROM produkty
        WHERE typ='vyrobok'
        ORDER BY nazov
    """) or []
    unlinked = db_connector.execute_query("""
        SELECT id, ean, nazov AS name
        FROM produkty
        WHERE typ='krajaný' AND (parent_id IS NULL OR parent_id=0)
        ORDER BY nazov
    """) or []
    return {"sourceProducts": sources, "unlinkedSlicedProducts": unlinked}


def link_sliced_product(data):
    """
    Prepojí krájaný produkt na zdroj:
      - buď cez ID (source_id/target_id),
      - alebo cez EAN (sourceEan/targetEan).
    """
    source_id = data.get('source_id')
    target_id = data.get('target_id')

    if not source_id or not target_id:
        # skús EAN
        src_ean = data.get('sourceEan')
        tgt_ean = data.get('targetEan')
        if not src_ean or not tgt_ean:
            return {"error": "Chýba identifikácia produktov."}
        src = db_connector.execute_query("SELECT id FROM produkty WHERE ean=%s", (src_ean,), 'one')
        tgt = db_connector.execute_query("SELECT id FROM produkty WHERE ean=%s", (tgt_ean,), 'one')
        if not src or not tgt:
            return {"error": "Produkty podľa EAN neboli nájdené."}
        source_id, target_id = src['id'], tgt['id']

    db_connector.execute_query("UPDATE produkty SET parent_id=%s WHERE id=%s", (source_id, target_id), 'none')
    return {"message": "Produkty prepojené."}


def create_and_link_sliced_product(data):
    """
    Vytvorí nový krájaný produkt (typ='krajaný') a nastaví parent_id na zdroj (vyrobok).
    Očakáva: source_id alebo sourceEan, nazov, ean, jednotka (default 'ks'), kategoria (nepovinné)
    """
    source_id = data.get('source_id')
    if not source_id:
        src_ean = data.get('sourceEan')
        if not src_ean:
            return {"error": "Chýba zdrojový produkt (source_id alebo sourceEan)."}
        src = db_connector.execute_query("SELECT id FROM produkty WHERE ean=%s", (src_ean,), 'one')
        if not src:
            return {"error": "Zdrojový produkt nebol nájdený."}
        source_id = src['id']

    new_name = data.get('name')
    new_ean  = data.get('ean')
    if not all([new_name, new_ean]):
        return {"error": "Chýba nazov alebo ean."}

    if db_connector.execute_query("SELECT id FROM produkty WHERE ean=%s", (new_ean,), 'one'):
        return {"error": f"EAN '{new_ean}' už existuje."}

    # prevziať kategóriu/dph zo zdroja (ak existuje)
    src = db_connector.execute_query("SELECT kategoria, dph FROM produkty WHERE id=%s", (source_id,), 'one') or {}
    kategoria = data.get('kategoria') or src.get('kategoria')
    dph       = safe_get_float(src.get('dph') or 0.0)
    jednotka  = data.get('jednotka') or 'ks'

    new_id = db_connector.execute_query("""
        INSERT INTO produkty (ean, nazov, typ, jednotka, kategoria, je_vyroba, parent_id, dph)
        VALUES (%s, %s, 'krajaný', %s, %s, 0, %s, %s)
    """, (new_ean, new_name, jednotka, kategoria, source_id, dph), 'lastrowid')
    return {"message": f"Produkt '{new_name}' vytvorený a prepojený.", "produkt_id": new_id}


def get_products_for_min_stock():
    """Finálne produkty pre nastavenie min. zásob."""
    return db_connector.execute_query("""
        SELECT id AS produkt_id, ean, nazov AS name, jednotka, min_zasoba
        FROM produkty
        WHERE typ IN ('vyrobok','krajaný','externy')
        ORDER BY name
    """) or []


def update_min_stock_levels(products_data):
    if not products_data:
        return {"error": "Neboli poskytnuté žiadne dáta na aktualizáciu."}

    conn = db_connector.get_connection()
    updated = 0
    try:
        cur = conn.cursor()
        for p in products_data:
            pid = p.get("produkt_id")
            minz = p.get("min_zasoba")
            if pid is None or minz in (None, ""):
                continue
            cur.execute("UPDATE produkty SET min_zasoba=%s WHERE id=%s", (safe_get_float(minz), safe_get_int(pid)))
            updated += 1
        conn.commit()
        return {"message": f"Minimálne zásoby aktualizované pre {updated} produktov."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


# =================================================================
# === REPORTY / ŠTATISTIKY ===
# =================================================================

def get_production_stats(period="week", category=None):
    """Štatistiky výroby pre stav 'Ukoncene'."""
    today = datetime.now()
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    else:
        start_date = datetime(1970, 1, 1)

    q = """
        SELECT 
            zv.id,
            zv.datum_ukoncenia,
            p.nazov AS vyrobok,
            zv.planovane_mnozstvo,
            zv.realne_mnozstvo,
            zv.celkova_cena_surovin,
            p.kategoria,
            p.jednotka
        FROM zaznamy_vyroba zv
        JOIN produkty p ON p.id = zv.vyrobok_id
        WHERE zv.stav = 'Ukoncene' AND zv.datum_ukoncenia >= %s
    """
    params = [start_date]
    if category and category != 'Všetky':
        q += " AND p.kategoria = %s"
        params.append(category)
    q += " ORDER BY zv.datum_ukoncenia DESC"

    rec = db_connector.execute_query(q, tuple(params)) or []
    return {'period': period, 'category': category, 'data': rec}


def get_receipt_report_html(period, category):
    """HTML report príjmov surovín (filter podľa s.nazov)."""
    today = datetime.now()
    if period == 'day':
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = datetime(1970, 1, 1)

    price_col = _detect_receive_price_column()
    price_expr = f"zp.{price_col}" if price_col else "NULL"

    q = f"""
        SELECT
            zp.datum,
            p.nazov                AS nazov_suroviny,
            s.nazov                AS sklad,
            zp.mnozstvo            AS mnozstvo_kg,
            {price_expr}           AS nakupna_cena_eur_kg,
            zp.poznamka            AS poznamka_dodavatel
        FROM zaznamy_prijem zp
        JOIN produkty p ON p.id = zp.produkt_id
        LEFT JOIN sklady s ON s.id = zp.sklad_id
        WHERE zp.datum >= %s
    """
    params = [start_date]
    if category and category != 'Všetky':
        q += " AND s.nazov = %s"
        params.append(category)
    q += " ORDER BY zp.datum DESC, p.nazov"

    records = db_connector.execute_query(q, tuple(params)) or []

    total_value = 0.0
    for r in records:
        qty = float(r.get('mnozstvo_kg') or 0)
        price = float(r.get('nakupna_cena_eur_kg') or 0)
        total_value += qty * price

    tpl = {
        "title": "Report Príjmu Surovín",
        "report_info": f"Obdobie: {period}, Sklad: {category}",
        "report_date": today.strftime('%d.%m.%Y'),
        "is_receipt_report": True,
        "data": records,
        "total_value": total_value
    }
    return make_response(render_template('report_template.html', **tpl))


def get_inventory_difference_report_html(date_str):
    """Ukážka – len ak máš tabuľku inventúrnych rozdielov (uprav, ak používaš iné meno)."""
    if not date_str:
        return make_response("<h1>Chyba: Nebol zadaný dátum pre report.</h1>", 400)

    # Ak používaš inú tabuľku/mená, uprav tu:
    if not _has_table('inventurne_rozdiely'):
        return make_response("<h1>Tabuľka inventúrnych rozdielov neexistuje.</h1>", 400)

    rec = db_connector.execute_query("""
        SELECT * FROM inventurne_rozdiely
        WHERE DATE(datum) = %s
        ORDER BY nazov_suroviny
    """, (date_str,)) or []
    total_diff_value = sum(safe_get_float(r.get('hodnota_rozdielu_eur') or 0.0) for r in rec)

    template_data = {
        "title": "Report Inventúrnych Rozdielov",
        "report_date": datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y'),
        "is_inventory_report": True,
        "data": rec,
        "total_diff_value": total_diff_value
    }
    return make_response(render_template('report_template.html', **template_data))


# =================================================================
# === HACCP DOKUMENTY (podľa tvojej schémy: nazov, file_path, created_at) ===
# =================================================================

def get_haccp_docs():
    if not _has_table('haccp_dokumenty'):
        return []
    return db_connector.execute_query("""
        SELECT id, nazov, file_path, created_at
        FROM haccp_dokumenty
        ORDER BY nazov
    """) or []


def get_haccp_doc_content(id=None, **kwargs):
    if not id:
        return {"error": "Chýba ID dokumentu."}
    if not _has_table('haccp_dokumenty'):
        return {"error": "Tabuľka haccp_dokumenty neexistuje."}
    row = db_connector.execute_query("""
        SELECT id, nazov, file_path, created_at
        FROM haccp_dokumenty
        WHERE id=%s
    """, (id,), 'one')
    if not row:
        return {"error": "Dokument nebol nájdený."}
    # Vraciame meta + cestu k súboru (obsah ako taký v DB nemáš).
    return row


def save_haccp_doc(id=None, title=None, file_path=None, **kwargs):
    if not _has_table('haccp_dokumenty'):
        return {"error": "Tabuľka haccp_dokumenty neexistuje."}
    if not title or not file_path:
        return {"error": "Chýba názov alebo cesta k súboru."}
    if id:
        db_connector.execute_query("""
            UPDATE haccp_dokumenty SET nazov=%s, file_path=%s WHERE id=%s
        """, (title, file_path, id), 'none')
        return {"message": "Dokument bol aktualizovaný."}
    new_id = db_connector.execute_query("""
        INSERT INTO haccp_dokumenty (nazov, file_path, created_at)
        VALUES (%s, %s, NOW())
    """, (title, file_path), 'lastrowid')
    return {"message": "Dokument bol vytvorený.", "id": new_id}


# =================================================================
# === B2B ADMINISTRÁCIA ===
# =================================================================

def get_pending_b2b_registrations():
    if not _has_table('b2b_zakaznici'):
        return []
    return db_connector.execute_query("""
        SELECT id, nazov_firmy, adresa, adresa_dorucenia, email, telefon, datum_registracie
        FROM b2b_zakaznici
        WHERE je_schvaleny=0 AND typ='B2B'
        ORDER BY datum_registracie DESC
    """) or []


def approve_b2b_registration(data):
    if not _has_table('b2b_zakaznici'):
        return {"error": "Tabuľka b2b_zakaznici neexistuje."}
    reg_id, customer_id = data.get('id'), data.get('customerId')
    if not reg_id or not customer_id:
        return {"error": "Chýba ID registrácie alebo zákaznícke číslo."}
    if db_connector.execute_query("SELECT id FROM b2b_zakaznici WHERE zakaznik_id=%s", (customer_id,), 'one'):
        return {"error": f"Zákaznícke číslo '{customer_id}' už je pridelené."}
    db_connector.execute_query("""
        UPDATE b2b_zakaznici
           SET je_schvaleny=1, zakaznik_id=%s
         WHERE id=%s
    """, (customer_id, reg_id), 'none')

    cust = db_connector.execute_query("SELECT email, nazov_firmy FROM b2b_zakaznici WHERE id=%s", (reg_id,), 'one')
    if cust:
        try:
            notification_handler.send_approval_email(cust['email'], cust['nazov_firmy'], customer_id)
        except Exception as e:
            logger.debug(f"Odoslanie e-mailu zlyhalo: {e}")
    return {"message": "Registrácia schválená."}


def reject_b2b_registration(data):
    if not _has_table('b2b_zakaznici'):
        return {"error": "Tabuľka b2b_zakaznici neexistuje."}
    rows = db_connector.execute_query(
        "DELETE FROM b2b_zakaznici WHERE id=%s AND je_schvaleny=0", (data.get('id'),), 'none'
    )
    return {"message": "Registrácia bola odmietnutá."} if rows else {"error": "Registráciu sa nepodarilo nájsť."}


def get_customers_and_pricelists():
    """
    Ak existujú tabuľky cenníkov, vráti aj väzby; inak len zákazníkov.
    """
    out = {"customers": [], "pricelists": []}
    if not _has_table('b2b_zakaznici'):
        return out

    customers_q = """
        SELECT z.id, z.zakaznik_id, z.nazov_firmy, z.email, z.telefon, z.adresa, z.adresa_dorucenia
        FROM b2b_zakaznici z
        WHERE z.je_admin=0 AND z.typ='B2B'
        ORDER BY z.nazov_firmy
    """
    out["customers"] = db_connector.execute_query(customers_q) or []

    if _has_table('b2b_cenniky'):
        out["pricelists"] = db_connector.execute_query(
            "SELECT id, nazov_cennika FROM b2b_cenniky ORDER BY nazov_cennika"
        ) or []
    return out


def update_customer_details(data):
    if not _has_table('b2b_zakaznici'):
        return {"error": "Tabuľka b2b_zakaznici neexistuje."}
    customer_id = data.get('id')
    conn = db_connector.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE b2b_zakaznici
               SET nazov_firmy=%s, email=%s, telefon=%s, adresa=%s, adresa_dorucenia=%s
             WHERE id=%s
        """, (data.get('nazov_firmy'), data.get('email'), data.get('telefon'),
              data.get('adresa'), data.get('adresa_dorucenia'), customer_id))
        # voliteľne: väzby na cenníky (len ak existujú obe tabuľky)
        if _has_table('b2b_zakaznik_cennik') and _has_table('b2b_cenniky'):
            cur.execute("DELETE FROM b2b_zakaznik_cennik WHERE zakaznik_id=%s", (customer_id,))
            ids = data.get('pricelist_ids', [])
            if ids:
                rows = [(customer_id, i) for i in ids]
                cur.executemany("INSERT INTO b2b_zakaznik_cennik (zakaznik_id, cennik_id) VALUES (%s, %s)", rows)
        conn.commit()
        return {"message": "Údaje zákazníka boli aktualizované."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_pricelists_and_products():
    out = {"pricelists": [], "productsByCategory": {}}
    # cenníky len ak tabuľka existuje
    if _has_table('b2b_cenniky'):
        out["pricelists"] = db_connector.execute_query(
            "SELECT id, nazov_cennika FROM b2b_cenniky ORDER BY nazov_cennika"
        ) or []
    # produkty
    products = db_connector.execute_query("""
        SELECT id, ean, nazov AS name, kategoria, dph
        FROM produkty
        WHERE typ IN ('vyrobok','krajaný','externy')
        ORDER BY kategoria, name
    """) or []
    by_cat = {}
    for p in products:
        c = p.get('kategoria') or 'Nezaradené'
        by_cat.setdefault(c, []).append(p)
    out["productsByCategory"] = by_cat
    return out


def create_pricelist(data):
    if not _has_table('b2b_cenniky'):
        return {"error": "Tabuľka b2b_cenniky neexistuje."}
    name = data.get('name')
    if not name:
        return {"error": "Názov cenníka je povinný."}
    new_id = db_connector.execute_query(
        "INSERT INTO b2b_cenniky (nazov_cennika) VALUES (%s)", (name,), 'lastrowid'
    )
    return {"message": f"Cenník '{name}' bol vytvorený.", "newPricelist": {"id": new_id, "nazov_cennika": name}}


def get_pricelist_details(data):
    if not _has_table('b2b_cennik_polozky'):
        return {"items": []}
    return {"items": db_connector.execute_query(
        "SELECT ean_produktu, cena FROM b2b_cennik_polozky WHERE cennik_id=%s", (data.get('id'),)
    ) or []}


def update_pricelist(data):
    if not _has_table('b2b_cennik_polozky'):
        return {"error": "Tabuľka b2b_cennik_polozky neexistuje."}
    pricelist_id, items = data.get('id'), data.get('items', [])
    conn = db_connector.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM b2b_cennik_polozky WHERE cennik_id=%s", (pricelist_id,))
        if items:
            rows = [(pricelist_id, i['ean'], safe_get_float(i['price'])) for i in items if i.get('price') is not None]
            if rows:
                cur.executemany(
                    "INSERT INTO b2b_cennik_polozky (cennik_id, ean_produktu, cena) VALUES (%s, %s, %s)", rows
                )
        conn.commit()
        return {"message": "Cenník bol aktualizovaný."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_announcement():
    if not _has_table('b2b_nastavenia'):
        return {"announcement": ""}
    row = db_connector.execute_query(
        "SELECT hodnota FROM b2b_nastavenia WHERE kluc='oznam'", fetch='one'
    )
    return {"announcement": row['hodnota'] if row else ""}


def save_announcement(data):
    if not _has_table('b2b_nastavenia'):
        return {"error": "Tabuľka b2b_nastavenia neexistuje."}
    text = data.get('announcement', '')
    db_connector.execute_query(
        "INSERT INTO b2b_nastavenia (kluc, hodnota) VALUES ('oznam', %s) "
        "ON DUPLICATE KEY UPDATE hodnota = VALUES(hodnota)",
        (text,), 'none'
    )
    return {"message": "Oznam bol aktualizovaný."}


def get_all_b2b_orders(filters):
    if not _has_table('b2b_objednavky'):
        return {"orders": []}
    start_date = filters.get('startDate') or '1970-01-01'
    end_date   = filters.get('endDate')   or '2999-12-31'
    orders = db_connector.execute_query("""
        SELECT o.*, z.nazov_firmy
        FROM b2b_objednavky o
        JOIN b2b_zakaznici z ON z.id = o.zakaznik_id
        WHERE DATE(o.pozadovany_datum_dodania) BETWEEN %s AND %s
        ORDER BY o.pozadovany_datum_dodania DESC, o.datum_objednavky DESC
    """, (start_date, end_date)) or []
    return {"orders": orders}


def get_b2b_order_details(order_id):
    if not _has_table('b2b_objednavky'):
        return {"error": "Tabuľka b2b_objednavky neexistuje."}
    if not order_id:
        return {"error": "Chýba ID objednávky."}

    order = db_connector.execute_query("""
        SELECT o.*, z.nazov_firmy, z.zakaznik_id AS customerLoginId, z.adresa AS customerAddress
        FROM b2b_objednavky o
        JOIN b2b_zakaznici z ON z.id = o.zakaznik_id
        WHERE o.id=%s
    """, (order_id,), 'one')
    if not order:
        return {"error": "Objednávka nebola nájdená."}

    items = db_connector.execute_query("""
        SELECT pol.produkt_id, pol.mnozstvo, pol.cena,
               p.ean, p.nazov, p.jednotka
        FROM b2b_objednavky_polozky pol
        JOIN produkty p ON p.id = pol.produkt_id
        WHERE pol.objednavka_id=%s
    """, (order_id,)) or []

    return {
        'id': order['id'],
        'order_number': order['cislo_objednavky'],
        'deliveryDate': order['pozadovany_datum_dodania'].strftime('%Y-%m-%d') if order.get('pozadovany_datum_dodania') else None,
        'note': order.get('poznamka'),
        'customerName': order['nazov_firmy'],
        'customerLoginId': order['customerLoginId'],
        'customerAddress': order['customerAddress'],
        'order_date': order['datum_objednavky'].strftime('%d.%m.%Y') if order.get('datum_objednavky') else None,
        'totalNet': safe_get_float(order.get('celkova_suma_bez_dph') or 0.0),
        'totalVat': safe_get_float(order.get('celkova_suma_s_dph') or 0.0),
        'items': [{
            'ean': it['ean'],
            'name': it['nazov'],
            'quantity': safe_get_float(it['mnozstvo']),
            'price': safe_get_float(it['cena']),
            'unit': it['jednotka'],
            'item_note': None
        } for it in items]
    }


# =================================================================
# === B2C ADMINISTRÁCIA (opatrné – nie všetky stĺpce môžu existovať) ===
# =================================================================

def get_b2c_orders_for_admin():
    if not _has_table('b2c_objednavky') or not _has_table('b2b_zakaznici'):
        return []
    return db_connector.execute_query("""
        SELECT o.*, z.nazov_firmy AS zakaznik_meno
        FROM b2c_objednavky o
        JOIN b2b_zakaznici z ON z.id = o.zakaznik_id
        ORDER BY 
            CASE o.stav
                WHEN 'Prijatá' THEN 1
                WHEN 'Pripravená' THEN 2
                WHEN 'Hotová' THEN 3
                WHEN 'Zrušená' THEN 4
                ELSE 5
            END,
            o.pozadovany_datum_dodania ASC, 
            o.datum_objednavky ASC
    """) or []


def finalize_b2c_order(data):
    """
    Nastaví finálnu cenu a stav 'Pripravená'.
    Ak neexistujú stĺpce finalna_suma_*, použije sa celkova_suma_*.
    """
    if not _has_table('b2c_objednavky'):
        return {"error": "Tabuľka b2c_objednavky neexistuje."}

    order_id = data.get('order_id')
    final_price_s_dph_str = data.get('final_price')
    if not all([order_id, final_price_s_dph_str]):
        return {"error": "Chýba ID objednávky alebo finálna cena."}

    try:
        final_price_s_dph = safe_get_float(str(final_price_s_dph_str).replace(',', '.'))
        if final_price_s_dph <= 0:
            return {"error": "Finálna cena musí byť kladné číslo."}
    except (ValueError, TypeError):
        return {"error": "Neplatný formát finálnej ceny."}

    has_final_cols = _has_column('b2c_objednavky', 'finalna_suma_s_dph')
    if has_final_cols:
        db_connector.execute_query("""
            UPDATE b2c_objednavky
               SET finalna_suma_s_dph=%s, stav='Pripravená'
             WHERE id=%s
        """, (final_price_s_dph, order_id), 'none')
    else:
        # fallback na existujúce celkova_suma_s_dph
        db_connector.execute_query("""
            UPDATE b2c_objednavky
               SET celkova_suma_s_dph=%s, stav='Pripravená'
             WHERE id=%s
        """, (final_price_s_dph, order_id), 'none')

    # notifikácia (ak máš e-mailové šablóny)
    order = db_connector.execute_query("SELECT zakaznik_id, cislo_objednavky FROM b2c_objednavky WHERE id=%s", (order_id,), 'one')
    if order and _has_table('b2b_zakaznici'):
        customer = db_connector.execute_query("SELECT nazov_firmy, email FROM b2b_zakaznici WHERE id=%s", (order['zakaznik_id'],), 'one')
        if customer:
            try:
                notification_handler.send_order_ready_email(
                    customer_email=customer['email'],
                    customer_name=customer['nazov_firmy'],
                    order_number=order['cislo_objednavky'],
                    final_price=final_price_s_dph
                )
            except Exception as e:
                logger.debug(f"Notifikácia zlyhala: {e}")

    return {"message": "Objednávka bola finalizovaná."}


def credit_b2c_loyalty_points(data):
    """
    Pripísanie bodov – funguje len ak existuje stĺpec vernostne_body v b2b_zakaznici
    a stĺpec datum_pripisania_bodov v b2c_objednavky (inak vráti chybu).
    """
    if not (_has_table('b2c_objednavky') and _has_table('b2b_zakaznici')):
        return {"error": "Potrebné tabuľky neexistujú."}
    if not (_has_column('b2b_zakaznici', 'vernostne_body') and _has_column('b2c_objednavky', 'datum_pripisania_bodov')):
        return {"error": "Vernostný program nie je aktivovaný v DB."}

    order_id = data.get('order_id')
    if not order_id:
        return {"error": "Chýba ID objednávky."}

    order = db_connector.execute_query("SELECT * FROM b2c_objednavky WHERE id=%s", (order_id,), 'one')
    if not order:
        return {"error": "Objednávka nebola nájdená."}
    if order['stav'] != 'Pripravená':
        return {"error": "Body možno pripísať len v stave 'Pripravená'."}
    if order.get('datum_pripisania_bodov') is not None:
        return {"error": "Body už boli pripísané."}

    final_price = safe_get_float(order.get('finalna_suma_s_dph') or order.get('celkova_suma_s_dph') or 0.0)
    if final_price <= 0:
        return {"error": "Objednávka nemá zadanú finálnu cenu."}

    points = math.floor(final_price)
    customer_id = order['zakaznik_id']
    conn = db_connector.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("UPDATE b2b_zakaznici SET vernostne_body = vernostne_body + %s WHERE id=%s", (points, customer_id))
        cur.execute("UPDATE b2c_objednavky SET datum_pripisania_bodov=%s, stav='Hotová' WHERE id=%s", (datetime.now(), order_id))
        cur.execute("SELECT nazov_firmy, email, vernostne_body FROM b2b_zakaznici WHERE id=%s", (customer_id,))
        customer = cur.fetchone()
        conn.commit()

        if customer:
            try:
                notification_handler.send_points_credited_email(
                    customer['email'], customer['nazov_firmy'], points, customer['vernostne_body']
                )
            except Exception as e:
                logger.debug(f"Notifikácia bodov zlyhala: {e}")

        return {"message": f"Pripísaných {points} bodov. Objednávka je hotová."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def cancel_b2c_order(data):
    if not _has_table('b2c_objednavky'):
        return {"error": "Tabuľka b2c_objednavky neexistuje."}
    order_id, reason = data.get('order_id'), data.get('reason')
    if not all([order_id, reason]):
        return {"error": "Chýba ID objednávky alebo dôvod zrušenia."}
    db_connector.execute_query("""
        UPDATE b2c_objednavky
           SET stav='Zrušená', poznamka = CONCAT(IFNULL(poznamka,''), ' | ZRUŠENÉ: ', %s)
         WHERE id=%s
    """, (reason, order_id), 'none')

    if _has_table('b2b_zakaznici'):
        order = db_connector.execute_query("SELECT zakaznik_id, cislo_objednavky FROM b2c_objednavky WHERE id=%s", (order_id,), 'one')
        if order:
            customer = db_connector.execute_query("SELECT nazov_firmy, email FROM b2b_zakaznici WHERE id=%s", (order['zakaznik_id'],), 'one')
            if customer:
                try:
                    notification_handler.send_b2c_order_cancelled_email(
                        customer['email'], customer['nazov_firmy'], order['cislo_objednavky'], reason
                    )
                except Exception as e:
                    logger.debug(f"Notifikácia zrušenia zlyhala: {e}")
    return {"message": "Objednávka bola zrušená."}


def get_b2c_customers_for_admin():
    if not _has_table('b2b_zakaznici'):
        return []
    # podporíme aj B2C, ak by si ich mal v rovnakej tabuľke (typ='B2C')
    return db_connector.execute_query("""
        SELECT zakaznik_id, nazov_firmy, email, telefon, adresa, adresa_dorucenia
        FROM b2b_zakaznici
        WHERE typ='B2C'
        ORDER BY nazov_firmy
    """) or []


def get_b2c_pricelist_for_admin():
    """
    Prehľad B2C cenníka: ak máš tabuľku b2c_cennik_polozky, načítame ju.
    Produkty berieme z 'produkty' (nazov, kategoria, dph).
    """
    all_products = db_connector.execute_query("""
        SELECT ean, nazov, kategoria, dph
        FROM produkty
        WHERE typ IN ('vyrobok','krajaný','externy')
        ORDER BY kategoria, nazov
    """) or []
    pricelist_items = []
    if _has_table('b2c_cennik_polozky'):
        pricelist_items = db_connector.execute_query("""
            SELECT c.ean_produktu, p.nazov, p.dph, c.cena_bez_dph, c.je_v_akcii, c.akciova_cena_bez_dph
            FROM b2c_cennik_polozky c
            JOIN produkty p ON p.ean = c.ean_produktu
        """) or []
    return {"all_products": all_products, "pricelist": pricelist_items}


def update_b2c_pricelist(data):
    if not _has_table('b2c_cennik_polozky'):
        return {"error": "Tabuľka b2c_cennik_polozky neexistuje."}
    items = data.get('items', [])
    conn = db_connector.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE b2c_cennik_polozky")
        if items:
            rows = [(i['ean'], safe_get_float(i.get('price', 0)),
                     bool(i.get('is_akcia', False)),
                     (safe_get_float(i.get('sale_price')) if i.get('is_akcia') and i.get('sale_price') else None))
                    for i in items]
            cur.executemany("""
                INSERT INTO b2c_cennik_polozky (ean_produktu, cena_bez_dph, je_v_akcii, akciova_cena_bez_dph)
                VALUES (%s, %s, %s, %s)
            """, rows)
        conn.commit()
        return {"message": "B2C cenník bol aktualizovaný."}
    except Exception:
        if conn: conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_b2c_rewards_for_admin():
    if not _has_table('b2c_vernostne_odmeny'):
        return []
    return db_connector.execute_query("""
        SELECT id, nazov_odmeny, potrebne_body, je_aktivna
        FROM b2c_vernostne_odmeny
        ORDER BY potrebne_body ASC
    """) or []


def add_b2c_reward(data):
    if not _has_table('b2c_vernostne_odmeny'):
        return {"error": "Tabuľka b2c_vernostne_odmeny neexistuje."}
    name, points = data.get('name'), data.get('points')
    if not all([name, points]):
        return {"error": "Názov a body sú povinné."}
    pts = safe_get_int(points)
    if pts <= 0:
        return {"error": "Body musia byť kladné číslo."}
    db_connector.execute_query("""
        INSERT INTO b2c_vernostne_odmeny (nazov_odmeny, potrebne_body, je_aktivna)
        VALUES (%s, %s, 1)
    """, (name, pts), 'none')
    return {"message": f"Odmena '{name}' pridaná."}


def toggle_b2c_reward_status(data):
    if not _has_table('b2c_vernostne_odmeny'):
        return {"error": "Tabuľka b2c_vernostne_odmeny neexistuje."}
    reward_id, current_status = data.get('id'), data.get('status')
    if not reward_id:
        return {"error": "Chýba ID odmeny."}
    db_connector.execute_query(
        "UPDATE b2c_vernostne_odmeny SET je_aktivna=%s WHERE id=%s",
        (0 if bool(current_status) else 1, reward_id), 'none'
    )
    return {"message": "Stav odmeny zmenený."}
def erp_catalog_overview(payload=None, **kwargs):
    """
    Stub pre ERP katalóg (kancelária dashboard), aby /api/kancelaria/getDashboardData nepadal.
    Neskôr doplníš reálne dáta; teraz stačí vrátiť prázdny prehľad.
    """
    return {
        "ok": True,
        "products_count": 0,
        "categories_count": 0,
        "suppliers_count": 0,
        "updated_at": None,
    }

