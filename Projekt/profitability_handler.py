# profitability_handler.py
from logger import logger
import db_connector
from datetime import datetime
from flask import render_template, make_response

# ==============================================================
# ================  MODUL: Z I S K O V O S Ť  ==================
# ==============================================================

# ---------- Pomocné "adaptívne" mapovanie produktov ----------
def _table_exists(tbl: str) -> bool:
    row = db_connector.execute_query(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s LIMIT 1",
        (tbl,), fetch='one'
    )
    return bool(row)

def _cols_of(tbl: str):
    rows = db_connector.execute_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
        (tbl,)
    ) or []
    return {r['COLUMN_NAME'].lower(): r['COLUMN_NAME'] for r in rows}

def _pick(cols_map: dict, *candidates):
    for cand in candidates:
        if cand and cand.lower() in cols_map:
            return cols_map[cand.lower()]
    return None

def _choose_products_mapping():
    """
    Nájde tabuľku produktov a priradí názvy stĺpcov podľa toho, čo v DB existuje.
    Vracia dict s kľúčmi: tbl, ean_col, name_col, mj_col, weight_col, type_col, is_manufactured_col
    """
    for tbl in ('produkty', 'products', 'katalog_produktov'):
        if _table_exists(tbl):
            cols = _cols_of(tbl)
            return {
                'tbl': tbl,
                'ean_col': _pick(cols, 'ean', 'barcode', 'kod', 'code'),
                'name_col': _pick(cols, 'nazov_vyrobku', 'nazov', 'name', 'produkt', 'product_name'),
                'mj_col': _pick(cols, 'mj', 'jednotka', 'unit', 'measurement_unit'),
                'weight_col': _pick(cols, 'vaha_balenia_g', 'piece_weight_g', 'hmotnost_kusu_g', 'gramaz', 'weight_g'),
                'type_col': _pick(cols, 'typ_polozky', 'typ', 'type', 'product_type'),
                'is_manufactured_col': _pick(cols, 'je_vyroba', 'vyrobok', 'is_manufactured')
            }
    return {
        'tbl': None, 'ean_col': None, 'name_col': None, 'mj_col': None,
        'weight_col': None, 'type_col': None, 'is_manufactured_col': None
    }

def _join_on_ean(lhs_expr: str, rhs_expr: str) -> str:
    """JOIN na EAN odolný voči mixu kolácií (pretypuje na CHAR(191) s jednotnou koláciou)."""
    return (f"CAST({lhs_expr} AS CHAR(191)) COLLATE utf8mb4_unicode_ci = "
            f"CAST({rhs_expr} AS CHAR(191)) COLLATE utf8mb4_unicode_ci")

# --------------------------------------------------------------
#                   HLAVNÝ PREGLED DÁT
# --------------------------------------------------------------
def get_profitability_data(year, month, **kwargs):
    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        return {"error": "Neplatný formát roku alebo mesiaca."}

    dept = db_connector.execute_query(
        "SELECT * FROM profit_department_monthly WHERE report_year=%s AND report_month=%s",
        (year, month), fetch='one'
    ) or {}

    production_view = get_production_profit_view(year, month)
    sales_channels  = get_sales_channels_view(year, month)
    calculations    = get_calculations_view(year, month)

    # agregované výpočty expedície
    exp_stock_prev      = float(dept.get('exp_stock_prev', 0) or 0)
    exp_from_butchering = float(dept.get('exp_from_butchering', 0) or 0)
    exp_from_prod       = float(dept.get('exp_from_prod', 0) or 0)
    exp_external        = float(dept.get('exp_external', 0) or 0)
    exp_returns         = float(dept.get('exp_returns', 0) or 0)
    exp_stock_current   = float(dept.get('exp_stock_current', 0) or 0)
    exp_revenue         = float(dept.get('exp_revenue', 0) or 0)

    cogs = (exp_stock_prev + exp_from_butchering + exp_from_prod + exp_external) - exp_returns - exp_stock_current
    exp_profit = exp_revenue - cogs

    butcher_profit      = float(dept.get('butcher_meat_value', 0) or 0) - float(dept.get('butcher_paid_goods', 0) or 0)
    butcher_revaluation = float(dept.get('butcher_process_value', 0) or 0) + float(dept.get('butcher_returns_value', 0) or 0)

    total_profit = (
        butcher_profit
        + exp_profit
        + float(production_view['summary'].get('total_profit', 0) or 0)
        - float(dept.get('general_costs', 0) or 0)
    )

    return {
        "year": year, "month": month,
        "department_data": dept,
        "production_view": production_view,
        "sales_channels_view": sales_channels,
        "calculations_view": calculations,
        "calculations": {
            "expedition_profit": exp_profit,
            "butchering_profit": butcher_profit,
            "butchering_revaluation": butcher_revaluation,
            "production_profit": production_view['summary'].get('total_profit', 0),
            "total_profit": total_profit
        }
    }

# --------------------------------------------------------------
#                 PREDAJNÉ KANÁLY (view + save)
# --------------------------------------------------------------
def get_sales_channels_view(year, month):
    pm = _choose_products_mapping()

    # default bez joinu
    base_q = (
        "SELECT sc.*, NULL AS product_name "
        "FROM profit_sales_monthly sc "
        "WHERE sc.report_year=%s AND sc.report_month=%s "
        "ORDER BY sc.sales_channel, 1"
    )
    rows = []
    if pm['tbl'] and pm['name_col'] and pm['ean_col']:
        join_on = _join_on_ean(f"p.{pm['ean_col']}", "sc.product_ean")
        q = (
            "SELECT sc.*, "
            f"p.{pm['name_col']} AS product_name "
            "FROM profit_sales_monthly sc "
            f"LEFT JOIN {pm['tbl']} p ON {join_on} "
            "WHERE sc.report_year=%s AND sc.report_month=%s "
            "ORDER BY sc.sales_channel, product_name"
        )
        rows = db_connector.execute_query(q, (year, month)) or []
    else:
        rows = db_connector.execute_query(base_q, (year, month)) or []

    # zoskupenie + súčty
    by_channel = {}
    for r in rows:
        ch = r.get('sales_channel') or ''
        if ch not in by_channel:
            by_channel[ch] = {'items': [], 'summary': {'total_kg': 0.0, 'total_purchase': 0.0, 'total_sell': 0.0, 'total_profit': 0.0}}
        kg = float(r.get('sales_kg') or 0)
        buy = float(r.get('purchase_price_net') or 0)
        sell= float(r.get('sell_price_net') or 0)

        r['sales_kg'] = kg
        r['purchase_price_net'] = buy
        r['sell_price_net'] = sell
        r['total_profit_eur'] = (sell - buy) * kg
        r['profit_per_kg'] = (sell - buy) if (sell > 0 and buy > 0) else 0.0

        s = by_channel[ch]['summary']
        s['total_kg'] += kg
        s['total_purchase'] += buy * kg
        s['total_sell'] += sell * kg
        s['total_profit'] += r['total_profit_eur']

        by_channel[ch]['items'].append(r)

    return by_channel

def setup_new_sales_channel(data):
    year, month, channel_name = data.get('year'), data.get('month'), (data.get('channel_name') or '').strip()
    if not all([year, month, channel_name]):
        return {"error": "Chýbajú dáta (rok/mesiac/názov kanála)."}

    pm = _choose_products_mapping()
    if not (pm['tbl'] and pm['ean_col'] and pm['name_col']):
        return {"error": "Nenašla sa tabuľka produktov v DB."}

    prod_q = f"SELECT p.{pm['ean_col']} AS ean, p.{pm['name_col']} AS nazov_vyrobku FROM {pm['tbl']} p"
    all_products = db_connector.execute_query(prod_q) or []
    if not all_products:
        return {"message": "V katalógu nie sú žiadne produkty na pridanie."}

    # seed s purchase_price_net = 0 (môžeš doplniť logiku podľa kalkulácií)
    records = [(year, month, channel_name, p['ean'], 0.0) for p in all_products]
    ins_q = (
        "INSERT IGNORE INTO profit_sales_monthly "
        "(report_year, report_month, sales_channel, product_ean, purchase_price_net) "
        "VALUES (%s,%s,%s,%s,%s)"
    )
    db_connector.execute_query(ins_q, records, fetch='rowcount', multi=True)
    return {"message": f"Kanál '{channel_name}' pripravený."}

def save_sales_channel_data(data):
    """
    UPSERT pre riadky kanála – funguje aj bez pre-seedu.
    Očakáva: {year, month, channel, rows:[{ean, sales_kg, purchase_price_net, purchase_price_vat, sell_price_net, sell_price_vat}, ...]}
    """
    year   = data.get('year')
    month  = data.get('month')
    channel= (data.get('channel') or '').strip()
    rows   = data.get('rows') or []

    if not all([year, month, channel]) or not isinstance(rows, list):
        return {"error": "Chýbajú dáta (rok/mesiac/kanál) alebo neplatné 'rows'."}

    upserts = []
    for r in rows:
        ean = (r.get('ean') or '').strip()
        if not ean: continue
        upserts.append((
            year, month, channel, ean,
            float(r.get('sales_kg') or 0),
            float(r.get('purchase_price_net') or 0),
            float(r.get('purchase_price_vat') or 0),
            float(r.get('sell_price_net') or 0),
            float(r.get('sell_price_vat') or 0),
        ))

    if not upserts:
        return {"error": "Nie je čo uložiť."}

    q = (
        "INSERT INTO profit_sales_monthly "
        "(report_year, report_month, sales_channel, product_ean, sales_kg, purchase_price_net, purchase_price_vat, sell_price_net, sell_price_vat) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE "
        " sales_kg=VALUES(sales_kg), purchase_price_net=VALUES(purchase_price_net), purchase_price_vat=VALUES(purchase_price_vat), "
        " sell_price_net=VALUES(sell_price_net), sell_price_vat=VALUES(sell_price_vat)"
    )
    db_connector.execute_query(q, upserts, fetch='none', multi=True)
    return {"message": f"Dáta pre kanál '{channel}' boli uložené."}

# --------------------------------------------------------------
#                   KALKULÁCIE (view + save)
# --------------------------------------------------------------
def get_calculations_view(year, month, **kwargs):
    # 1) hlavičky
    calcs = db_connector.execute_query(
        "SELECT id, name, report_year, report_month, vehicle_id, distance_km, transport_cost "
        "FROM profit_calculations WHERE report_year=%s AND report_month=%s "
        "ORDER BY created_at DESC, id DESC",
        (year, month)
    ) or []
    calc_by_id = {c['id']: {**c, 'items': []} for c in calcs}

    # 2) položky
    items = []
    if calc_by_id:
        placeholders = ", ".join(["%s"] * len(calc_by_id))
        items = db_connector.execute_query(
            f"SELECT * FROM profit_calculation_items WHERE calculation_id IN ({placeholders}) ORDER BY id",
            tuple(calc_by_id.keys())
        ) or []

    # 3) produktová mapa (bez JOIN-u, aby sme nenarazili na kolácie)
    pmap = {}
    pm = _choose_products_mapping()
    if pm['tbl'] and pm['ean_col'] and pm['name_col']:
        prows = db_connector.execute_query(
            f"SELECT p.{pm['ean_col']} AS ean, p.{pm['name_col']} AS name FROM {pm['tbl']} p"
        ) or []
        for r in prows:
            key = str(r.get('ean') or '').strip()
            if key: pmap[key] = r.get('name')

    for it in items:
        ean = str(it.get('product_ean') or '').strip()
        it['product_name'] = pmap.get(ean) or ean or ''
        cid = it.get('calculation_id')
        if cid in calc_by_id:
            calc_by_id[cid]['items'].append(it)

    # 4) available_products (pre editor)
    available_products = []
    if pm['tbl'] and pm['ean_col'] and pm['name_col']:
        rows = db_connector.execute_query(
            f"SELECT p.{pm['ean_col']} AS ean, p.{pm['name_col']} AS nazov_vyrobku FROM {pm['tbl']} p ORDER BY 2,1"
        ) or []
        available_products = [{**r, 'avg_cost': None} for r in rows]

    # 5) vozidlá (ak existuje tabuľka s inými názvami stĺpcov, vrátime prázdne)
    try:
        # POZN.: ak niektoré stĺpce neexistujú, vyhodí to výnimku a spadneme do except → []
        vehicles = db_connector.execute_query(
            "SELECT id, license_plate, name FROM fleet_vehicles WHERE IFNULL(is_active,1)=1 ORDER BY name"
        ) or []
    except Exception:
        vehicles = []

    return {
        "calculations": list(calc_by_id.values()),
        "available_products": available_products,
        "available_vehicles": vehicles
    }

def save_calculation(data):
    calc_id = data.get('id') or None
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor()
        params = (
            data['name'],
            data['year'],
            data['month'],
            (data.get('vehicle_id') or None),
            float(data.get('distance_km') or 0),
            float(data.get('transport_cost') or 0)
        )
        if calc_id:
            cursor.execute(
                "UPDATE profit_calculations "
                "SET name=%s, report_year=%s, report_month=%s, vehicle_id=%s, distance_km=%s, transport_cost=%s "
                "WHERE id=%s",
                params + (calc_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO profit_calculations (name, report_year, report_month, vehicle_id, distance_km, transport_cost) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                params
            )
            calc_id = cursor.lastrowid

        cursor.execute("DELETE FROM profit_calculation_items WHERE calculation_id=%s", (calc_id,))
        items = data.get('items', []) or []
        if items:
            to_ins = [
                (calc_id,
                 it.get('product_ean'),
                 float(it.get('estimated_kg') or 0),
                 float(it.get('purchase_price_net') or 0),
                 float(it.get('sell_price_net') or 0))
                for it in items
            ]
            cursor.executemany(
                "INSERT INTO profit_calculation_items (calculation_id, product_ean, estimated_kg, purchase_price_net, sell_price_net) "
                "VALUES (%s,%s,%s,%s,%s)",
                to_ins
            )
        conn.commit()
        return {"message": f"Kalkulácia '{data['name']}' bola úspešne uložená."}
    except Exception as e:
        if conn: conn.rollback()
        raise e
    finally:
        if conn and conn.is_connected(): conn.close()

def delete_calculation(data):
    db_connector.execute_query("DELETE FROM profit_calculations WHERE id=%s", (data.get('id'),), fetch='none')
    return {"message": "Kalkulácia bola vymazaná."}

# --------------------------------------------------------------
#                   VÝROBA (view + save)
# --------------------------------------------------------------
def get_production_profit_view(year, month):
    pm = _choose_products_mapping()
    if not (pm['tbl'] and pm['ean_col'] and pm['name_col']):
        return {"rows": [], "summary": {'total_profit': 0.0, 'total_kg': 0.0, 'total_kg_no_pkg': 0.0, 'jars_200': 0.0, 'jars_500': 0.0, 'lids': 0.0}}

    tbl, ean, namec = pm['tbl'], pm['ean_col'], pm['name_col']
    mj    = pm['mj_col'] or 'NULL'
    wt    = pm['weight_col'] or 'NULL'
    typ   = pm['type_col']
    manuf = pm['is_manufactured_col']

    where = []
    if manuf:
        where.append(f"p.{manuf}=1")
    elif typ:
        where.append(f"(UPPER(p.{typ}) LIKE 'VYROB%' OR UPPER(p.{typ}) LIKE 'VÝROB%')")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    products_q = (
        f"SELECT p.{ean} AS ean, "
        f"       p.{namec} AS name, "
        f"       {mj} AS mj, "
        f"       {wt} AS vaha_balenia_g, "
        f"       " + (f"p.{typ}" if typ else "NULL") + " AS typ_polozky "
        f"FROM {tbl} p "
        f"{where_sql} "
        "ORDER BY 1"
    )
    products = db_connector.execute_query(products_q) or []

    manual_q = (
        "SELECT product_ean, expedition_sales_kg, transfer_price_per_unit "
        "FROM profit_production_monthly WHERE report_year=%s AND report_month=%s"
    )
    manual_map = { r['product_ean']: r for r in (db_connector.execute_query(manual_q, (year, month)) or []) }

    rows = []
    summary = {'total_profit': 0.0, 'total_kg': 0.0, 'total_kg_no_pkg': 0.0, 'jars_200': 0.0, 'jars_500': 0.0, 'lids': 0.0}

    for p in products:
        ean_val  = p.get('ean')
        name_val = (p.get('name') or '').strip()
        typ_raw  = p.get('typ_polozky')
        typ_val  = (typ_raw if isinstance(typ_raw, str) else str(typ_raw or '')).upper()
        weight_g = float(p.get('vaha_balenia_g') or 0)

        m = manual_map.get(ean_val, {}) if ean_val else {}
        prod_cost = 0.0  # (priestor na budúce prepojenie s kalkuláciami)
        transfer_price = float(m.get('transfer_price_per_unit') or (prod_cost * 1.1 if prod_cost > 0 else 0))
        sales_kg = float(m.get('expedition_sales_kg') or 0)
        profit = (transfer_price - prod_cost) * sales_kg if (sales_kg > 0 and prod_cost >= 0) else 0.0

        summary['total_profit'] += profit
        summary['total_kg']     += sales_kg

        # odhad nerozbalené/nekrajané
        is_packaged_or_sliced = False
        if typ_val:
            t = (typ_val
                 .replace('Á', 'A').replace('Ý', 'Y')
                 .replace('Š', 'S').replace('Č', 'C').replace('Ž', 'Z'))
            if 'KUS' in t or 'KRAJ' in t:
                is_packaged_or_sliced = True
        if not is_packaged_or_sliced:
            summary['total_kg_no_pkg'] += sales_kg

        # poháre / viečka pri paštétach
        nm_low = name_val.lower()
        if weight_g > 0 and sales_kg > 0 and any(k in nm_low for k in ('pašt', 'pastet', 'pečeňov', 'pecenov')):
            num_pcs = (sales_kg * 1000.0) / weight_g
            if abs(weight_g - 200.0) < 0.001: summary['jars_200'] += num_pcs
            if abs(weight_g - 500.0) < 0.001: summary['jars_500'] += num_pcs
            summary['lids'] += num_pcs

        rows.append({
            "ean": ean_val,
            "name": name_val,
            "exp_stock_kg": 0,
            "exp_sales_kg": sales_kg,
            "production_cost": prod_cost,
            "transfer_price": transfer_price,
            "profit": profit
        })

    return {"rows": rows, "summary": summary}

def save_production_profit_data(data):
    year, month, rows = data.get('year'), data.get('month'), data.get('rows', [])
    if not all([year, month]) or not rows:
        return {"error": "Chýbajú dáta pre uloženie výroby."}

    to_upd = [
        (year, month, r['ean'],
         float(r.get('expedition_sales_kg') or 0),
         float(r.get('transfer_price') or 0))
        for r in rows
    ]
    q = (
        "INSERT INTO profit_production_monthly "
        "(report_year, report_month, product_ean, expedition_sales_kg, transfer_price_per_unit) "
        "VALUES (%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE expedition_sales_kg=VALUES(expedition_sales_kg), transfer_price_per_unit=VALUES(transfer_price_per_unit)"
    )
    db_connector.execute_query(q, to_upd, fetch='none', multi=True)
    return {"message": "Dáta pre ziskovosť výroby boli uložené."}

# --------------------------------------------------------------
#                   ODDELENIA (save)
# --------------------------------------------------------------
def save_department_data(data):
    year, month = data.get('year'), data.get('month')
    if not year or not month:
        return {"error": "Chýba rok alebo mesiac."}

    fields = [
        'exp_stock_prev', 'exp_from_butchering', 'exp_from_prod', 'exp_external',
        'exp_returns', 'exp_stock_current', 'exp_revenue',
        'butcher_meat_value', 'butcher_paid_goods', 'butcher_process_value', 'butcher_returns_value',
        'general_costs'
    ]
    params = {f: float(data.get(f) or 0.0) for f in fields}
    params['report_year'] = year
    params['report_month'] = month

    up_q = (
        "INSERT INTO profit_department_monthly "
        "(report_year, report_month, exp_stock_prev, exp_from_butchering, exp_from_prod, exp_external, exp_returns, "
        " exp_stock_current, exp_revenue, butcher_meat_value, butcher_paid_goods, butcher_process_value, butcher_returns_value, general_costs) "
        "VALUES (%(report_year)s, %(report_month)s, %(exp_stock_prev)s, %(exp_from_butchering)s, %(exp_from_prod)s, %(exp_external)s, "
        "        %(exp_returns)s, %(exp_stock_current)s, %(exp_revenue)s, %(butcher_meat_value)s, %(butcher_paid_goods)s, "
        "        %(butcher_process_value)s, %(butcher_returns_value)s, %(general_costs)s) "
        "ON DUPLICATE KEY UPDATE "
        " exp_stock_prev=VALUES(exp_stock_prev), exp_from_butchering=VALUES(exp_from_butchering), exp_from_prod=VALUES(exp_from_prod), "
        " exp_external=VALUES(exp_external), exp_returns=VALUES(exp_returns), exp_stock_current=VALUES(exp_stock_current), "
        " exp_revenue=VALUES(exp_revenue), butcher_meat_value=VALUES(butcher_meat_value), "
        " butcher_paid_goods=VALUES(butcher_paid_goods), butcher_process_value=VALUES(butcher_process_value), "
        " butcher_returns_value=VALUES(butcher_returns_value), general_costs=VALUES(general_costs)"
    )
    db_connector.execute_query(up_q, params, fetch='none')
    return {"message": "Dáta oddelení boli uložené."}
# --------------------------------------------------------------
#                 DASHBOARD (JSON for MoM charts)
# --------------------------------------------------------------
def get_profitability_dashboard(year, month, months_back=12, **kwargs):
    try:
        year = int(year)
        month = int(month)
        months_back = int(months_back or 12)
    except (ValueError, TypeError):
        return {"error": "Neplatný formát roku/mesiaca."}

    # helper: kontinuita mesiacov – N mesiacov končiac na (year, month)
    def month_sequence(y, m, n):
        start_index = (y * 12 + (m - 1)) - (n - 1)   # index prvého mesiaca (inkluzívne)
        seq = []
        for k in range(n):
            idx = start_index + k
            yy = idx // 12
            mm = (idx % 12) + 1
            seq.append((yy, mm))
        return seq

    series = []
    for (yy, mm) in month_sequence(year, month, months_back):
        one = get_profitability_data(yy, mm)
        if isinstance(one, dict) and one.get('error'):
            continue

        dept  = (one or {}).get('department_data', {}) or {}
        calcs = (one or {}).get('calculations', {}) or {}

        # zisky z už existujúcich výpočtov
        exp_profit      = float(calcs.get('expedition_profit', 0) or 0)
        butcher_profit  = float(calcs.get('butchering_profit', 0) or 0)
        prod_profit     = float(calcs.get('production_profit', 0) or 0)
        net_profit      = float(calcs.get('total_profit', 0) or 0)

        # potrebujeme aj COGS – dopočítame
        exp_stock_prev      = float(dept.get('exp_stock_prev', 0) or 0)
        exp_from_butchering = float(dept.get('exp_from_butchering', 0) or 0)
        exp_from_prod       = float(dept.get('exp_from_prod', 0) or 0)
        exp_external        = float(dept.get('exp_external', 0) or 0)
        exp_returns         = float(dept.get('exp_returns', 0) or 0)
        exp_stock_current   = float(dept.get('exp_stock_current', 0) or 0)
        exp_revenue         = float(dept.get('exp_revenue', 0) or 0)
        general_costs       = float(dept.get('general_costs', 0) or 0)

        cogs = (exp_stock_prev + exp_from_butchering + exp_from_prod + exp_external) - exp_returns - exp_stock_current

        series.append({
            "year": yy, "month": mm, "period": f"{mm:02d}/{yy}",
            "revenue_eur": exp_revenue,
            "cogs_eur": cogs,
            "expedition_profit_eur": exp_profit,
            "butchering_profit_eur": butcher_profit,
            "production_profit_eur": prod_profit,
            "general_costs_eur": general_costs,
            "net_profit_eur": net_profit
        })

    return {"series": series}

# --------------------------------------------------------------
#                       REPORT (HTML)
# --------------------------------------------------------------
def get_profitability_report_html(**kwargs):
    year  = kwargs.get('year')
    month = kwargs.get('month')
    rtype = kwargs.get('type', 'summary')

    full = get_profitability_data(year, month)

    if rtype == 'calculations':
        for calc in full.get('calculations_view', {}).get('calculations', []):
            calc['distance_km']    = float(calc.get('distance_km') or 0)
            calc['transport_cost'] = float(calc.get('transport_cost') or 0)
            for item in calc.get('items', []):
                item['purchase_price_net'] = float(item.get('purchase_price_net') or 0)
                item['sell_price_net']     = float(item.get('sell_price_net') or 0)
                item['estimated_kg']       = float(item.get('estimated_kg') or 0)

    title_map = {
        'departments':    'Report Výnosov Oddelení',
        'production':     'Report Výnosu Výroby',
        'sales_channels': 'Report Predajných Kanálov',
        'calculations':   'Report Kalkulácií',
        'summary':        'Celkový Prehľad Ziskovosti'
    }
    data = {
        "title": title_map.get(rtype, 'Report Ziskovosti'),
        "report_type": rtype,
        "period": f"{month}/{year}",
        "data": full,
        "today": datetime.now().strftime('%d.%m.%Y')
    }
    return make_response(render_template('profitability_report_template.html', **data))
