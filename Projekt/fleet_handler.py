from validators import validate_required_fields, safe_get_float, safe_get_int
from logger import logger
import db_connector
from datetime import datetime
from calendar import monthrange
from flask import render_template, make_response
import traceback

# ================================
# === FLEET / KNIHA JÁZD API  ====
# ================================

def _fv_cols():
    rows = db_connector.execute_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'fleet_vehicles'"
    )
    return {r['COLUMN_NAME'] for r in rows}

def _vehicle_select_sql_and_flags():
    cols = _fv_cols()
    parts = ["id"]

    # license_plate alias (spz/vin fallback)
    if 'license_plate' in cols:
        parts.append("license_plate")
    elif 'spz' in cols:
        parts.append("spz AS license_plate")
    elif 'vin' in cols:
        parts.append("vin AS license_plate")
    else:
        parts.append("NULL AS license_plate")

    # name alias (znacka/model fallback)
    if 'name' in cols:
        parts.append("name")
    elif ('znacka' in cols) or ('model' in cols):
        joiners = []
        if 'znacka' in cols: joiners.append("COALESCE(znacka,'')")
        if 'model'  in cols: joiners.append("COALESCE(model,'')")
        expr = "CONCAT_WS(' ', " + ", ".join(joiners) + ")" if joiners else "''"
        parts.append(f"{expr} AS name")
    else:
        parts.append("'' AS name")

    parts.append("type" if 'type' in cols else "NULL AS type")
    parts.append("default_driver" if 'default_driver' in cols else "NULL AS default_driver")

    if 'initial_odometer' in cols:
        parts.append("initial_odometer")
    elif 'stav_km' in cols:
        parts.append("stav_km AS initial_odometer")
    else:
        parts.append("0 AS initial_odometer")

    has_is_active = 'is_active' in cols
    parts.append("IFNULL(is_active,1) AS is_active" if has_is_active else "1 AS is_active")

    select_sql = "SELECT " + ", ".join(parts) + " FROM fleet_vehicles"
    return select_sql, has_is_active

def _tbl_cols(table):
    rows = db_connector.execute_query(
        "SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, DATA_TYPE, EXTRA "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,)
    ) or []
    meta = {r['COLUMN_NAME']: r for r in rows}
    def has(c): return c in meta
    def notnull_nodflt(c):
        m = meta.get(c) or {}
        return (m.get('IS_NULLABLE') == 'NO') and (m.get('COLUMN_DEFAULT') is None) and ('auto_increment' not in (m.get('EXTRA') or ''))
    def is_num(c):
        t = (meta.get(c, {}).get('DATA_TYPE') or '').lower()
        return t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint')
    def is_date(c):
        t = (meta.get(c, {}).get('DATA_TYPE') or '').lower()
        return t in ('date','datetime','timestamp','time')
    return meta, has, notnull_nodflt, is_num, is_date


def get_fleet_data(vehicle_id=None, year=None, month=None, **kwargs):
    """
    Zoznam vozidiel, denné logy, tankovania a posledný známy stav tachometra pred mesiacom.
    (kompatibilné s SPZ/vin a znacka/model)
    """
    select_sql, has_is_active = _vehicle_select_sql_and_flags()
    where = " WHERE IFNULL(is_active,1)=1" if has_is_active else ""
    vehicles = db_connector.execute_query(f"{select_sql}{where} ORDER BY name")

    if not vehicle_id and vehicles:
        vehicle_id = vehicles[0]['id']

    today = datetime.now()
    year = safe_get_int(year) if year else today.year
    month = safe_get_int(month) if month else today.month

    logs, refuelings, last_odometer = [], [], 0
    if vehicle_id:
        logs = db_connector.execute_query(
            "SELECT id, vehicle_id, log_date, driver, start_odometer, end_odometer, km_driven, "
            "goods_out_kg, goods_in_kg, delivery_notes_count "
            "FROM fleet_logs WHERE vehicle_id=%s AND YEAR(log_date)=%s AND MONTH(log_date)=%s "
            "ORDER BY log_date ASC",
            (vehicle_id, year, month)
        )
        refuelings = db_connector.execute_query(
            "SELECT id, vehicle_id, refueling_date, driver, liters, price_per_liter, total_price "
            "FROM fleet_refuelings WHERE vehicle_id=%s AND YEAR(refueling_date)=%s AND MONTH(refueling_date)=%s "
            "ORDER BY refueling_date ASC",
            (vehicle_id, year, month)
        )

        first_day = f"{year:04d}-{month:02d}-01"
        last_odo = db_connector.execute_query(
            "SELECT end_odometer FROM fleet_logs WHERE vehicle_id=%s AND log_date < %s "
            "AND end_odometer IS NOT NULL ORDER BY log_date DESC LIMIT 1",
            (vehicle_id, first_day), fetch='one'
        )
        if last_odo and last_odo.get('end_odometer') is not None:
            last_odometer = safe_get_int(last_odo['end_odometer'])
        else:
            cols = _fv_cols()
            q = None
            if 'initial_odometer' in cols: q = "SELECT initial_odometer AS io FROM fleet_vehicles WHERE id=%s"
            elif 'stav_km' in cols:        q = "SELECT stav_km AS io FROM fleet_vehicles WHERE id=%s"
            if q:
                initial = db_connector.execute_query(q, (vehicle_id,), fetch='one')
                last_odometer = safe_get_int((initial or {}).get('io') or 0)
            else:
                last_odometer = 0

    return {
        "vehicles": vehicles,
        "selected_vehicle_id": safe_get_int(vehicle_id) if vehicle_id else None,
        "selected_year": year,
        "selected_month": month,
        "logs": logs,
        "refuelings": refuelings,
        "last_odometer": last_odometer or 0
    }


def save_daily_log(data, **kwargs):
    """
    Uloží/aktualizuje viaceré dni do fleet_logs.
    Prispôsobí názvy stĺpcov schéme a doplní NOT NULL bez defaultu.
    Nikdy nevyhodí výnimku (žiadne 500).
    """
    try:
        logs = (data or {}).get('logs') or kwargs.get('logs')
        if not logs:
            return {"error": "Chýbajú dáta záznamov (logs)."}

        meta, has, notnull_nodflt, is_num, is_date = _tbl_cols('fleet_logs')

        date_col  = next((c for c in ('log_date','date','datum') if has(c)), None)
        veh_col   = 'vehicle_id' if has('vehicle_id') else None
        driver_c  = next((c for c in ('driver','vodic') if has(c)), None)
        sodo_c    = next((c for c in ('start_odometer','odometer_start','zac_km','zaciatok_km') if has(c)), None)
        eodo_c    = next((c for c in ('end_odometer','odometer_end','kon_km','koniec_km') if has(c)), None)
        km_c      = next((c for c in ('km_driven','najazdene_km') if has(c)), None)
        gout_c    = next((c for c in ('goods_out_kg','vyvoz_kg') if has(c)), None)
        gin_c     = next((c for c in ('goods_in_kg','dovoz_kg') if has(c)), None)
        dl_c      = next((c for c in ('delivery_notes_count','dl_count') if has(c)), None)
        id_c      = 'id' if has('id') else None

        if not (veh_col and date_col):
            return {"error": "Schéma fleet_logs neobsahuje vehicle_id alebo dátumový stĺpec."}

        from datetime import datetime, date
        def norm_date(s):
            if not s: return None
            try: return datetime.strptime(str(s)[:10], "%Y-%m-%d").date().isoformat()
            except Exception:
                try: return datetime.fromisoformat(str(s)).date().isoformat()
                except Exception: return str(s)

        conn = db_connector.get_connection(); cur = conn.cursor()

        for row in logs:
            vid = safe_get_int(row.get('vehicle_id'))
            d   = norm_date(row.get('log_date') or row.get('date') or row.get('datum'))
            if not (vid and d):
                continue

            fields = { veh_col: vid, date_col: d }
            if driver_c: fields[driver_c] = (row.get('driver') or None)
            if sodo_c:   fields[sodo_c]   = safe_get_int(row.get('start_odometer') or row.get('odometer_start'))
            if eodo_c:   fields[eodo_c]   = safe_get_int(row.get('end_odometer') or row.get('odometer_end'))
            if km_c:     fields[km_c]     = safe_get_int(row.get('km_driven'))
            if gout_c:   fields[gout_c]   = safe_get_float(row.get('goods_out_kg'))
            if gin_c:    fields[gin_c]    = safe_get_float(row.get('goods_in_kg'))
            if dl_c:     fields[dl_c]     = safe_get_int(row.get('delivery_notes_count'))

            # doplň NOT NULL bez defaultu
            for c in meta.keys():
                if c in ('id','created_at','updated_at'): continue
                if c in fields:
                    if fields[c] is None and notnull_nodflt(c):
                        fields[c] = 0 if is_num(c) else (date.today().isoformat() if is_date(c) else '')
                else:
                    if notnull_nodflt(c):
                        fields[c] = 0 if is_num(c) else (date.today().isoformat() if is_date(c) else '')

            if id_c:
                # upsert podľa (vehicle_id, date)
                cur.execute(f"SELECT {id_c} FROM fleet_logs WHERE {veh_col}=%s AND {date_col}=%s LIMIT 1", (vid, d))
                ex = cur.fetchone()
                if ex:
                    row_id = ex[0]
                    set_clause = ", ".join(f"{c}=%s" for c in fields.keys() if c != id_c)
                    params = [fields[c] for c in fields.keys() if c != id_c] + [row_id]
                    cur.execute(f"UPDATE fleet_logs SET {set_clause} WHERE {id_c}=%s", params)
                else:
                    cols_sql = ", ".join(fields.keys())
                    ph = ", ".join(["%s"]*len(fields))
                    cur.execute(f"INSERT INTO fleet_logs ({cols_sql}) VALUES ({ph})", list(fields.values()))
            else:
                # tabuľka nemá primárny kľúč 'id' – vlož vždy nový riadok
                cols_sql = ", ".join(fields.keys())
                ph = ", ".join(["%s"]*len(fields))
                cur.execute(f"INSERT INTO fleet_logs ({cols_sql}) VALUES ({ph})", list(fields.values()))

        conn.commit(); cur.close(); conn.close()
        return {"message": "Kniha jázd uložená."}
    except Exception as e:
        logger.error(f"[fleet.save_daily_log] {e}")
        logger.error(traceback.format_exc())
        return {"error": f"DB chyba pri ukladaní knihy jázd: {e}"}


def save_vehicle(data=None, **kwargs):
    """
    Vloží/aktualizuje vozidlo na ľubovoľnej schéme fleet_vehicles (license_plate|spz|vin; name|znacka/model; initial_odometer|stav_km).
    Doplňuje NOT NULL bez defaultu. Nevyhadzuje výnimky.
    """
    try:
        if data is None or not isinstance(data, dict):
            data = kwargs or {}

        # meta stĺpcov
        colrows = db_connector.execute_query(
            "SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, DATA_TYPE, EXTRA "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'fleet_vehicles'"
        ) or []
        meta = {r['COLUMN_NAME']: r for r in colrows}
        cols = set(meta.keys())

        def has(c): return c in cols
        def notnull_nodflt(c):
            m = meta.get(c) or {}
            return (m.get('IS_NULLABLE') == 'NO') and (m.get('COLUMN_DEFAULT') is None) and ('auto_increment' not in (m.get('EXTRA') or ''))
        def is_num(c):
            t = (meta.get(c, {}).get('DATA_TYPE') or '').lower()
            return t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint')
        def is_date(c):
            t = (meta.get(c, {}).get('DATA_TYPE') or '').lower()
            return t in ('date','datetime','timestamp','time')

        # vstup
        lp  = (data.get('license_plate') or '').strip().upper()
        nm  = (data.get('name') or '').strip()
        typ = (data.get('type') or '').strip() or None
        drv = (data.get('default_driver') or '').strip() or None
        init_odo = safe_get_int(data.get('initial_odometer') or 0)
        vehicle_id = data.get('id')

        if not lp and not nm:
            return {"error": "Zadajte aspoň ŠPZ alebo Názov vozidla."}

        fields = {}

        ident = 'license_plate' if has('license_plate') else ('spz' if has('spz') else ('vin' if has('vin') else None))
        if ident: fields[ident] = lp or None

        if has('name'):
            fields['name'] = (nm or lp or None)
        else:
            if has('znacka'): fields['znacka'] = (nm or lp or None)
            if has('model'):  fields['model']  = None  # doplníme nižšie

        if has('type'):           fields['type'] = typ
        if has('default_driver'): fields['default_driver'] = drv

        if has('initial_odometer'):
            fields['initial_odometer'] = init_odo
        elif has('stav_km'):
            fields['stav_km'] = init_odo

        if 'is_active' in cols and not vehicle_id:
            fields['is_active'] = 1

        # doplň NOT NULL bez defaultu
        from datetime import datetime as dt, date
        if has('model') and (('model' not in fields) or fields['model'] is None) and notnull_nodflt('model'):
            fields['model'] = ''
        for c, m in meta.items():
            if c in ('id','created_at','updated_at'): continue
            if c in fields:
                if fields[c] is None and notnull_nodflt(c):
                    t = (m.get('DATA_TYPE') or '').lower()
                    fields[c] = 0 if t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint') else (date.today().isoformat() if t in ('date','datetime','timestamp','time') else '')
            else:
                if notnull_nodflt(c):
                    t = (m.get('DATA_TYPE') or '').lower()
                    if t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint'): fields[c] = 0
                    elif t == 'date': fields[c] = date.today().isoformat()
                    elif t in ('datetime','timestamp'): fields[c] = dt.now().strftime("%Y-%m-%d %H:%M:%S")
                    elif t == 'time': fields[c] = '00:00:00'
                    else: fields[c] = ''

        if not fields:
            return {"error": "Schéma fleet_vehicles neobsahuje použiteľné stĺpce."}

        if vehicle_id:
            set_clause = ", ".join(f"{c}=%s" for c in fields.keys())
            params = list(fields.values()) + [vehicle_id]
            db_connector.execute_query(f"UPDATE fleet_vehicles SET {set_clause} WHERE id=%s", tuple(params), fetch='none')
            return {"message": "Údaje o vozidle boli aktualizované."}
        else:
            cols_sql = ", ".join(fields.keys())
            placeholders = ", ".join(["%s"] * len(fields))
            db_connector.execute_query(f"INSERT INTO fleet_vehicles ({cols_sql}) VALUES ({placeholders})", tuple(fields.values()), fetch='none')
            return {"message": "Nové vozidlo bolo pridané."}

    except Exception as e:
        msg = str(e)
        if '1062' in msg or 'Duplicate' in msg:
            return {"error": "Vozidlo s touto ŠPZ/identifikátorom už existuje."}
        if "doesn't have a default value" in msg or 'cannot be null' in msg.lower():
            return {"error": "Schéma vyžaduje ďalšie povinné polia. Doplňte prosím údaje (napr. Názov, Model…)."}
        logger.error(f"[fleet.save_vehicle] DB error: {msg}")
        logger.error(traceback.format_exc())
        return {"error": f"DB chyba: {msg}"}

def save_vehicle_safe(*args, **kwargs):
    try:
        data = args[0] if (args and isinstance(args[0], dict)) else kwargs
        resp = save_vehicle(data=data)
        return resp
    except Exception as e:
        logger.error(f"[fleet.save_vehicle_safe] {e}")
        logger.error(traceback.format_exc())
        return {"error": f"Neočekávaná chyba: {e}"}


def save_refueling(data=None, **kwargs):
    """
    Vloží záznam o tankovaní do fleet_refuelings.
    Prispôsobí názvy stĺpcov a doplní NOT NULL bez defaultu. Nevyhadzuje výnimky.
    """
    try:
        payload = data or kwargs or {}
        meta, has, notnull_nodflt, is_num, is_date = _tbl_cols('fleet_refuelings')

        vcol      = 'vehicle_id' if has('vehicle_id') else None
        date_col  = next((c for c in ('refueling_date','date','datum') if has(c)), None)
        liters_c  = next((c for c in ('liters','litre','liters_l') if has(c)), None)
        ppl_c     = next((c for c in ('price_per_liter','price_l','cena_za_l','cena_l') if has(c)), None)
        total_c   = next((c for c in ('total_price','total','sum','cena_spolu') if has(c)), None)
        driver_c  = next((c for c in ('driver','vodic') if has(c)), None)

        if not (vcol and date_col and liters_c):
            return {"error":"Schéma fleet_refuelings neobsahuje povinné stĺpce (vehicle_id, dátum, litres)."}

        from datetime import datetime as dt, date
        def norm_date(s):
            if not s: return None
            try: return dt.strptime(str(s)[:10], "%Y-%m-%d").date().isoformat()
            except Exception:
                try: return dt.fromisoformat(str(s)).date().isoformat()
                except Exception: return str(s)

        vid   = safe_get_int(payload.get('vehicle_id') or payload.get('vehicle'))
        d_iso = norm_date(payload.get('refueling_date') or payload.get('date') or payload.get('datum'))
        lits  = safe_get_float(payload.get('liters') or payload.get('litre'))
        if not vid or not d_iso or lits is None:
            return {"error":"Vyplňte vozidlo, dátum a litre."}

        fields = { vcol: vid, date_col: d_iso, liters_c: lits }
        if driver_c: fields[driver_c] = (payload.get('driver') or '').strip() or None

        ppl   = safe_get_float(payload.get('price_per_liter'))
        total = safe_get_float(payload.get('total_price'))
        if ppl_c and ppl is not None:
            fields[ppl_c] = ppl
        if total_c:
            if total is None and (ppl is not None):
                total = round(lits * ppl, 2)
            fields[total_c] = total

        for c, m in meta.items():
            if c in ('id','created_at','updated_at'):  # preskoč auto/id
                continue
            if c in fields:
                if fields[c] is None and notnull_nodflt(c):
                    t = (m.get('DATA_TYPE') or '').lower()
                    fields[c] = 0 if t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint') else (date.today().isoformat() if t in ('date','datetime','timestamp','time') else '')
            else:
                if notnull_nodflt(c):
                    t = (m.get('DATA_TYPE') or '').lower()
                    if t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint'): fields[c] = 0
                    elif t == 'date': fields[c] = date.today().isoformat()
                    elif t in ('datetime','timestamp'): fields[c] = dt.now().strftime("%Y-%m-%d %H:%M:%S")
                    elif t == 'time': fields[c] = '00:00:00'
                    else: fields[c] = ''

        cols_sql = ", ".join(fields.keys())
        ph = ", ".join(["%s"]*len(fields))
        db_connector.execute_query(f"INSERT INTO fleet_refuelings ({cols_sql}) VALUES ({ph})", tuple(fields.values()), fetch='none')
        return {"message":"Záznam o tankovaní bol pridaný."}

    except Exception as e:
        logger.error(f"[fleet.save_refueling] {e}")
        logger.error(traceback.format_exc())
        return {"error": f"DB chyba pri ukladaní tankovania: {e}"}


def delete_refueling(data, **kwargs):
    rid = data.get('id')
    if not rid: return {"error": "Chýba ID záznamu."}
    db_connector.execute_query("DELETE FROM fleet_refuelings WHERE id=%s", (rid,), fetch='none')
    return {"message": "Záznam o tankovaní bol vymazaný."}


def get_fleet_analysis(vehicle_id=None, year=None, month=None, **kwargs):
    if not all([vehicle_id, year, month]): return {"error": "Chýbajú parametre."}
    year, month = safe_get_int(year), safe_get_int(month)

    log_sum = db_connector.execute_query(
        "SELECT SUM(km_driven) AS total_km, SUM(goods_out_kg) AS total_goods_out "
        "FROM fleet_logs WHERE vehicle_id=%s AND YEAR(log_date)=%s AND MONTH(log_date)=%s",
        (vehicle_id, year, month), fetch='one'
    ) or {}
    ref_sum = db_connector.execute_query(
        "SELECT SUM(liters) AS total_liters, SUM(total_price) AS total_fuel_cost "
        "FROM fleet_refuelings WHERE vehicle_id=%s AND YEAR(refueling_date)=%s AND MONTH(refueling_date)=%s",
        (vehicle_id, year, month), fetch='one'
    ) or {}

    start = datetime(year, month, 1)
    end = start.replace(day=monthrange(year, month)[1])

    other = db_connector.execute_query(
        "SELECT SUM(monthly_cost) AS total_other_costs FROM fleet_costs "
        "WHERE (vehicle_id=%s OR vehicle_id IS NULL) AND valid_from<=%s AND (valid_to IS NULL OR valid_to>=%s)",
        (vehicle_id, end.date(), start.date()), fetch='one'
    ) or {}

    total_km = safe_get_float(log_sum.get('total_km') or 0)
    total_goods_out = safe_get_float(log_sum.get('total_goods_out') or 0)
    total_fuel_cost = safe_get_float(ref_sum.get('total_fuel_cost') or 0)
    total_liters = safe_get_float(ref_sum.get('total_liters') or 0)
    total_other_costs = safe_get_float(other.get('total_other_costs') or 0)

    total_costs = total_fuel_cost + total_other_costs
    cost_per_km = total_costs / total_km if total_km > 0 else 0
    cost_per_kg_goods = (total_costs * 1.1) / total_goods_out if total_goods_out > 0 else 0
    avg_consumption = (total_liters / total_km) * 100 if total_km > 0 else 0

    return {
        "total_costs": total_costs,
        "total_km": total_km,
        "cost_per_km": cost_per_km,
        "total_goods_out_kg": total_goods_out,
        "cost_per_kg_goods": cost_per_kg_goods,
        "avg_consumption": avg_consumption
    }

def get_fleet_costs(vehicle_id=None, **kwargs):
    return db_connector.execute_query(
        "SELECT id, cost_name, cost_type, monthly_cost, valid_from, valid_to, vehicle_id "
        "FROM fleet_costs WHERE (vehicle_id=%s OR vehicle_id IS NULL) ORDER BY valid_from DESC",
        (vehicle_id,)
    )

def save_fleet_cost(data, **kwargs):
    """
    Vloží/aktualizuje náklad do fleet_costs.
    Prispôsobí sa schéme a doplní NOT NULL bez defaultu. Nevyhadzuje výnimky.
    """
    try:
        payload = data or kwargs or {}
        meta, has, notnull_nodflt, is_num, is_date = _tbl_cols('fleet_costs')

        fields = {}
        if has('cost_name'):     fields['cost_name']     = (payload.get('cost_name') or '').strip() or None
        if has('cost_type'):     fields['cost_type']     = (payload.get('cost_type') or '').strip() or None
        if has('monthly_cost'):  fields['monthly_cost']  = safe_get_float(payload.get('monthly_cost'))
        if has('valid_from'):    fields['valid_from']    = payload.get('valid_from') or None
        if has('valid_to'):      fields['valid_to']      = payload.get('valid_to') or None
        if has('vehicle_id'):    fields['vehicle_id']    = safe_get_int(payload.get('vehicle_id')) if payload.get('vehicle_id') not in (None,'') else None

        from datetime import date, datetime as dt
        for c, m in meta.items():
            if c in ('id','created_at','updated_at'): continue
            if c in fields:
                if fields[c] is None and notnull_nodflt(c):
                    t = (m.get('DATA_TYPE') or '').lower()
                    fields[c] = 0 if t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint') else (date.today().isoformat() if t in ('date','datetime','timestamp','time') else '')
            else:
                if notnull_nodflt(c):
                    t = (m.get('DATA_TYPE') or '').lower()
                    if t in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint'): fields[c] = 0
                    elif t == 'date': fields[c] = date.today().isoformat()
                    elif t in ('datetime','timestamp'): fields[c] = dt.now().strftime("%Y-%m-%d %H:%M:%S")
                    elif t == 'time': fields[c] = '00:00:00'
                    else: fields[c] = ''

        cid = payload.get('id')
        if cid:
            set_clause = ", ".join(f"{c}=%s" for c in fields.keys())
            params = list(fields.values()) + [cid]
            db_connector.execute_query(f"UPDATE fleet_costs SET {set_clause} WHERE id=%s", tuple(params), fetch='none')
            return {"message": "Náklad bol aktualizovaný."}
        else:
            cols_sql = ", ".join(fields.keys())
            placeholders = ", ".join(["%s"]*len(fields))
            db_connector.execute_query(f"INSERT INTO fleet_costs ({cols_sql}) VALUES ({placeholders})", tuple(fields.values()), fetch='none')
            return {"message": "Nový náklad bol pridaný."}

    except Exception as e:
        logger.error(f"[fleet.save_fleet_cost] {e}")
        logger.error(traceback.format_exc())
        return {"error": f"DB chyba pri ukladaní nákladu: {e}"}


def delete_fleet_cost(data, **kwargs):
    cid = data.get('id')
    if not cid: return {"error": "Chýba ID nákladu."}
    db_connector.execute_query("DELETE FROM fleet_costs WHERE id=%s", (cid,), fetch='none')
    return {"message": "Náklad bol vymazaný."}


def get_report_html_content(**kwargs):
    vehicle_id = kwargs.get('vehicle_id'); year = kwargs.get('year'); month = kwargs.get('month')
    if not all([vehicle_id, year, month]):
        return make_response("<h1>Chýbajú parametre reportu.</h1>", 400)

    year, month = safe_get_int(year), safe_get_int(month)
    data = get_fleet_data(vehicle_id, year, month)
    analysis = get_fleet_analysis(vehicle_id, year, month)

    start = datetime(year, month, 1)
    end = start.replace(day=monthrange(year, month)[1])
    costs = db_connector.execute_query(
        "SELECT * FROM fleet_costs WHERE (vehicle_id=%s OR vehicle_id IS NULL) "
        "AND valid_from<=%s AND (valid_to IS NULL OR valid_to>=%s)",
        (vehicle_id, end.date(), start.date())
    )

    fixed = [c for c in costs if c['cost_type'] in ('MZDA','POISTENIE','DIALNICNA','INE')]
    variable = [c for c in costs if c['cost_type'] in ('SERVIS','PNEUMATIKY','SKODA')]

    ctx = {
        "vehicle": next((v for v in data['vehicles'] if v['id']==safe_get_int(vehicle_id)), {}),
        "period": f"{month:02d}/{year}",
        "logs": data['logs'],
        "refuelings": data['refuelings'],
        "analysis": analysis,
        "fixed_costs": fixed,
        "variable_costs": variable
    }
    return make_response(render_template('fleet_report_template.html', **ctx))
