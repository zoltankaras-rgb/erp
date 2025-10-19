# costs_handler.py — finálna verzia: rozdelené energie, robustné ukladanie/čítanie
from validators import safe_get_float, safe_get_int
from logger import logger
import db_connector
import profitability_handler
import calendar

# ============= Helpers =============
def _days_in_month(y, m): return calendar.monthrange(int(y), int(m))[1]

def _compute_electricity(year, month, start_kwh, end_kwh, unit_net, vat_rate):
    days = _days_in_month(year, month)
    start = safe_get_float(start_kwh or 0); end = safe_get_float(end_kwh or 0)
    unit  = safe_get_float(unit_net or 0);  vat = safe_get_float(vat_rate or 0)
    cons  = max(0.0, end - start)
    unit_br = unit * (1 + vat/100)
    tot_net = cons * unit; tot_vat = tot_net * (vat/100); tot_br = tot_net + tot_vat
    return {
        "consumption_kwh": cons,
        "unit_price_kwh_gross": unit_br,
        "total_net_eur": tot_net,
        "total_vat_eur": tot_vat,
        "total_gross_eur": tot_br,
        "avg_daily_kwh": cons / days if days else 0.0,
        "avg_daily_cost_gross": tot_br / days if days else 0.0,
        "avg_unit_price_gross": (tot_br/cons) if cons>0 else unit_br
    }

def _compute_gas(year, month, start_m3, end_m3, coeff, unit_kwh_net, vat_rate):
    days = _days_in_month(year, month)
    s = safe_get_float(start_m3 or 0); e = safe_get_float(end_m3 or 0)
    coeff = safe_get_float(coeff or 0); unit = safe_get_float(unit_kwh_net or 0); vat = safe_get_float(vat_rate or 0)
    m3 = max(0.0, e - s); kwh = m3 * coeff
    unit_br = unit * (1 + vat/100); tot_net = kwh * unit; tot_vat = tot_net * (vat/100); tot_br = tot_net + tot_vat
    return {
        "consumption_m3": m3,
        "consumption_kwh": kwh,
        "unit_price_kwh_gross": unit_br,
        "total_net_eur": tot_net,
        "total_vat_eur": tot_vat,
        "total_gross_eur": tot_br,
        "avg_daily_kwh": kwh / days if days else 0.0,
        "avg_daily_m3": m3 / days if days else 0.0,
        "avg_unit_price_gross": (tot_br/kwh) if kwh>0 else unit_br
    }

def _compute_water(year, month, start_m3, end_m3, unit_net, vat_rate):
    days = _days_in_month(year, month)
    s = safe_get_float(start_m3 or 0); e = safe_get_float(end_m3 or 0)
    unit = safe_get_float(unit_net or 0); vat = safe_get_float(vat_rate or 0)
    m3 = max(0.0, e - s); unit_br = unit * (1 + vat/100); tot_net = m3 * unit; tot_vat = tot_net * (vat/100); tot_br = tot_net + tot_vat
    return {
        "delta_m3": m3,
        "unit_price_m3_gross": unit_br,
        "total_net_eur": tot_net,
        "total_vat_eur": tot_vat,
        "total_gross_eur": tot_br,
        "avg_daily_m3": m3 / days if days else 0.0,
        "avg_daily_cost_gross": tot_br / days if days else 0.0,
        "avg_unit_price_gross": (tot_br/m3) if m3>0 else unit_br
    }

# ---------- Payload helper ----------
def _unpack_payload(kwargs: dict) -> dict:
    p = kwargs or {}
    for k in ('data', 'payload'):
        if isinstance(p.get(k), dict): p = p[k]
    for k in ('data', 'payload'):
        if isinstance(p.get(k), dict): p = p[k]
    return p

# ---------- DB helpers ----------
def _exists_period(table, y, m):
    return bool(db_connector.execute_query(
        f"SELECT 1 FROM {table} WHERE record_year=%s AND record_month=%s LIMIT 1",
        (y, m), 'one'
    ))

def _fetch_energy_one(table, y, m, order_hint=""):
    base = f"SELECT * FROM {table} WHERE record_year=%s AND record_month=%s "
    q = base + (f"ORDER BY {order_hint} " if order_hint else "") + "LIMIT 1"
    return db_connector.execute_query(q, (y, m), 'one') or {}

# ============= READ API =============
def get_costs_data(year=None, month=None, **kwargs):
    p = _unpack_payload({'year': year, 'month': month, **kwargs})
    y = safe_get_int(p.get('year')); m = safe_get_int(p.get('month'))

    el = _fetch_energy_one(
        "costs_energy_electricity", y, m,
        "COALESCE(meter_end_kwh,0) DESC, COALESCE(meter_start_kwh,0) DESC, COALESCE(unit_price_kwh_net,0) DESC"
    )
    gas = _fetch_energy_one(
        "costs_energy_gas", y, m,
        "COALESCE(meter_end_m3,0) DESC, COALESCE(meter_start_m3,0) DESC, COALESCE(coeff_kwh_per_m3,0) DESC"
    )
    water = _fetch_energy_one(
        "costs_energy_water", y, m,
        "COALESCE(meter_curr,0) DESC, COALESCE(meter_prev,0) DESC, COALESCE(unit_price,0) DESC"
    )

    hr = db_connector.execute_query(
        "SELECT * FROM costs_hr WHERE record_year=%s AND record_month=%s LIMIT 1",
        (y, m), 'one'
    ) or {}

    op_rows = db_connector.execute_query("""
        SELECT ci.*, cc.name AS category_name
        FROM costs_items ci
        JOIN costs_categories cc ON cc.id = ci.category_id
        WHERE YEAR(ci.entry_date)=%s AND MONTH(ci.entry_date)=%s
        ORDER BY ci.entry_date DESC, ci.id DESC
    """, (y, m)) or []

    categories = db_connector.execute_query(
        "SELECT * FROM costs_categories WHERE is_active=1 ORDER BY name"
    ) or []

    comp_el = _compute_electricity(y, m, el.get('meter_start_kwh'), el.get('meter_end_kwh'),
                                   el.get('unit_price_kwh_net'), el.get('vat_rate')) if el else {}
    comp_gs = _compute_gas(y, m, gas.get('meter_start_m3'), gas.get('meter_end_m3'),
                           (gas.get('coeff_kwh_per_m3') or 0), gas.get('unit_price_kwh_net'), gas.get('vat_rate')) if gas else {}
    comp_w  = _compute_water(y, m, water.get('meter_prev'), water.get('meter_curr'),
                             water.get('unit_price'), water.get('vat_rate')) if water else {}

    return {
        "energy": {
            "electricity": el, "gas": gas, "water": water,
            "computed": {"electricity": comp_el, "gas": comp_gs, "water": comp_w}
        },
        "hr": hr,
        "operational": { "items": op_rows, "categories": categories or [] }
    }

# ============= WRITE API =============
def save_energy_data(**kwargs):
    """
    Ulož len tie časti, ktoré prišli v payload-e (electricity/gas/water).
    UPDATE ak existuje (month/year), inak INSERT.
    """
    p = _unpack_payload(kwargs)
    y = safe_get_int(p.get('year')); m = safe_get_int(p.get('month'))
    if not y or not m: return {"error": "Chýba rok alebo mesiac."}

    el  = p.get('electricity')
    gas = p.get('gas')
    w   = p.get('water')

    logger.info(f"[costs/saveEnergy] payload: y={y} m={m} el={el} gas={gas} water={w}")

    # ELEKTRINA – len ak prišla
    if isinstance(el, dict):
        if _exists_period("costs_energy_electricity", y, m):
            db_connector.execute_query("""
              UPDATE costs_energy_electricity
                 SET meter_start_kwh=%s, meter_end_kwh=%s, unit_price_kwh_net=%s, vat_rate=%s
               WHERE record_year=%s AND record_month=%s
            """, (
               safe_get_float(el.get('meter_start_kwh')),
               safe_get_float(el.get('meter_end_kwh')),
               safe_get_float(el.get('unit_price_kwh_net')),
               safe_get_float(el.get('vat_rate')),
               y, m
            ), 'none')
        else:
            db_connector.execute_query("""
              INSERT INTO costs_energy_electricity
                (record_year, record_month, meter_start_kwh, meter_end_kwh, unit_price_kwh_net, vat_rate)
              VALUES (%s,%s,%s,%s,%s,%s)
            """, (
               y, m,
               safe_get_float(el.get('meter_start_kwh')),
               safe_get_float(el.get('meter_end_kwh')),
               safe_get_float(el.get('unit_price_kwh_net')),
               safe_get_float(el.get('vat_rate'))
            ), 'none')

    # PLYN – len ak prišiel
    if isinstance(gas, dict):
        if _exists_period("costs_energy_gas", y, m):
            db_connector.execute_query("""
              UPDATE costs_energy_gas
                 SET meter_start_m3=%s, meter_end_m3=%s, coeff_kwh_per_m3=%s,
                     unit_price_kwh_net=%s, vat_rate=%s
               WHERE record_year=%s AND record_month=%s
            """, (
               safe_get_float(gas.get('meter_start_m3')),
               safe_get_float(gas.get('meter_end_m3')),
               safe_get_float(gas.get('coeff_kwh_per_m3')),
               safe_get_float(gas.get('unit_price_kwh_net')),
               safe_get_float(gas.get('vat_rate')),
               y, m
            ), 'none')
        else:
            db_connector.execute_query("""
              INSERT INTO costs_energy_gas
                (record_year, record_month, meter_start_m3, meter_end_m3, coeff_kwh_per_m3,
                 unit_price_kwh_net, vat_rate)
              VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
               y, m,
               safe_get_float(gas.get('meter_start_m3')),
               safe_get_float(gas.get('meter_end_m3')),
               safe_get_float(gas.get('coeff_kwh_per_m3')),
               safe_get_float(gas.get('unit_price_kwh_net')),
               safe_get_float(gas.get('vat_rate'))
            ), 'none')

    # VODA – len ak prišla
    if isinstance(w, dict):
        if _exists_period("costs_energy_water", y, m):
            db_connector.execute_query("""
              UPDATE costs_energy_water
                 SET meter_prev=%s, meter_curr=%s, unit_price=%s, vat_rate=%s,
                     total_bez_dph=%s, dph=%s, total_s_dph=%s
               WHERE record_year=%s AND record_month=%s
            """, (
               safe_get_float(w.get('meter_prev')),
               safe_get_float(w.get('meter_curr')),
               safe_get_float(w.get('unit_price_net')),
               safe_get_float(w.get('vat_rate')),
               safe_get_float(w.get('total_bez_dph')),
               safe_get_float(w.get('dph')),
               safe_get_float(w.get('total_s_dph')),
               y, m
            ), 'none')
        else:
            db_connector.execute_query("""
              INSERT INTO costs_energy_water
                (record_year, record_month, meter_prev, meter_curr, unit_price, vat_rate,
                 total_bez_dph, dph, total_s_dph)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
               y, m,
               safe_get_float(w.get('meter_prev')),
               safe_get_float(w.get('meter_curr')),
               safe_get_float(w.get('unit_price_net')),
               safe_get_float(w.get('vat_rate')),
               safe_get_float(w.get('total_bez_dph')),
               safe_get_float(w.get('dph')),
               safe_get_float(w.get('total_s_dph'))
            ), 'none')

    logger.info(f"[costs/saveEnergy] uložené pre {y}-{m}")
    return {"message": "Energie uložené."}

def save_hr_data(**kwargs):
    p = _unpack_payload(kwargs)
    y, m = safe_get_int(p.get('year')), safe_get_int(p.get('month'))
    if not y or not m: return {"error": "Chýba rok alebo mesiac."}
    db_connector.execute_query("""
      INSERT INTO costs_hr (record_year, record_month, total_salaries, total_levies)
      VALUES (%s,%s,%s,%s)
      ON DUPLICATE KEY UPDATE total_salaries=VALUES(total_salaries), total_levies=VALUES(total_levies)
    """, (y, m, safe_get_float(p.get('total_salaries')), safe_get_float(p.get('total_levies'))), 'none')
    return {"message": "HR uložené."}

def save_operational_cost(**kwargs):
    p = _unpack_payload(kwargs)
    required = ['entry_date', 'category_id', 'name', 'amount_net']
    if not all(k in p and p[k] for k in required): return {"error":"Chýbajú povinné údaje."}
    amount_net = safe_get_float(p['amount_net'])
    vat_rate   = None if p.get('vat_rate') in (None, '') else safe_get_float(p.get('vat_rate'))
    amount_vat = round(amount_net * (vat_rate/100.0), 2) if vat_rate is not None else None
    amount_gross = round(amount_net + (amount_vat or 0.0), 2) if vat_rate is not None else amount_net
    item_id = p.get('id')
    if item_id:
        db_connector.execute_query("""
          UPDATE costs_items
          SET entry_date=%s, category_id=%s, name=%s, description=%s, amount_net=%s, vat_rate=%s,
              amount_vat=%s, amount_gross=%s, vendor_name=%s, invoice_no=%s, cost_center=%s, is_recurring=%s
          WHERE id=%s
        """, (
          p['entry_date'], safe_get_int(p['category_id']), p['name'], p.get('description',''),
          amount_net, vat_rate, amount_vat, amount_gross,
          p.get('vendor_name'), p.get('invoice_no'), p.get('cost_center') or 'company',
          bool(p.get('is_recurring')), item_id
        ), 'none')
        return {"message":"Náklad aktualizovaný."}
    else:
        db_connector.execute_query("""
          INSERT INTO costs_items
          (entry_date, category_id, name, description, amount_net, vat_rate, amount_vat, amount_gross,
           vendor_name, invoice_no, cost_center, is_recurring)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
          p['entry_date'], safe_get_int(p['category_id']), p['name'], p.get('description',''),
          amount_net, vat_rate, amount_vat, amount_gross,
          p.get('vendor_name'), p.get('invoice_no'), p.get('cost_center') or 'company',
          bool(p.get('is_recurring'))
        ), 'none')
        return {"message":"Náklad pridaný."}

def delete_operational_cost(**kwargs):
    p = _unpack_payload(kwargs)
    if not p.get('id'): return {"error":"Chýba ID nákladu."}
    db_connector.execute_query("DELETE FROM costs_items WHERE id=%s", (p['id'],), 'none')
    return {"message":"Náklad vymazaný."}

def save_cost_category(**kwargs):
    p = kwargs.get('data') if isinstance(kwargs.get('data'), dict) else kwargs
    name = (p.get('name') or '').strip()
    if not name: return {"error":"Názov kategórie nemôže byť prázdny."}
    try:
        db_connector.execute_query("INSERT INTO costs_categories (name) VALUES (%s)", (name,), 'none')
        return {"message": f"Kategória '{name}' pridaná."}
    except Exception as e:
        if 'Duplicate entry' in str(e): return {"error": f"Kategória '{name}' už existuje."}
        raise

# ============= Dashboard (Profitability prepojenie) =============
def _sum_operational_for_month(y, m):
    row = db_connector.execute_query(
        "SELECT SUM(amount_net) AS s FROM costs_items WHERE YEAR(entry_date)=%s AND MONTH(entry_date)=%s",
        (y, m), 'one'
    ) or {}
    return safe_get_float(row.get('s') or 0)

def _energy_totals(y, m):
    el  = _fetch_energy_one("costs_energy_electricity", y, m,
           "COALESCE(meter_end_kwh,0) DESC, COALESCE(meter_start_kwh,0) DESC, COALESCE(unit_price_kwh_net,0) DESC")
    gas = _fetch_energy_one("costs_energy_gas", y, m,
           "COALESCE(meter_end_m3,0) DESC, COALESCE(meter_start_m3,0) DESC, COALESCE(coeff_kwh_per_m3,0) DESC")
    w   = _fetch_energy_one("costs_energy_water", y, m,
           "COALESCE(meter_curr,0) DESC, COALESCE(meter_prev,0) DESC, COALESCE(unit_price,0) DESC")
    el_tot  = _compute_electricity(y, m, el.get('meter_start_kwh'), el.get('meter_end_kwh'),
                                   el.get('unit_price_kwh_net'), el.get('vat_rate'))['total_gross_eur'] if el else 0.0
    gas_tot = _compute_gas(y, m, gas.get('meter_start_m3'), gas.get('meter_end_m3'),
                           (gas.get('coeff_kwh_per_m3') or 0.0),
                           gas.get('unit_price_kwh_net'), gas.get('vat_rate'))['total_gross_eur'] if gas else 0.0
    w_tot   = _compute_water(y, m, w.get('meter_prev'), w.get('meter_curr'),
                             w.get('unit_price'), w.get('vat_rate'))['total_gross_eur'] if w else 0.0
    return el_tot, gas_tot, w_tot

def _hr_total(y, m):
    r = db_connector.execute_query(
        "SELECT total_salaries, total_levies FROM costs_hr WHERE record_year=%s AND record_month=%s LIMIT 1",
        (y, m), 'one'
    ) or {}
    return safe_get_float(r.get('total_salaries') or 0) + safe_get_float(r.get('total_levies') or 0)

def get_dashboard_data(year=None, month=None, **kwargs):
    p = _unpack_payload({'year': year, 'month': month, **kwargs})
    y = safe_get_int(p.get('year')); m = safe_get_int(p.get('month'))
    prof  = profitability_handler.get_profitability_data(year=y, month=m)
    calcs = (prof or {}).get('calculations', {}) or {}
    op_profit = safe_get_float(calcs.get('total_profit') or 0)

    el_tot, gas_tot, w_tot = _energy_totals(y, m)
    hr_tot = _hr_total(y, m)
    op_tot = _sum_operational_for_month(y, m)
    total_costs = el_tot + gas_tot + w_tot + hr_tot + op_tot
    return {"summary": {"operating_profit": op_profit, "total_costs": total_costs, "company_net": op_profit - total_costs}}
# ==================== ANNUAL (JSON + HTML report) ====================

def _month_seq_year(year: int):
    return [(year, m) for m in range(1, 12+1)]

def get_energy_annual_json(year=None, types="all", **kwargs):
    """
    JSON pre ročný prehľad: mesačné série + ročné súčty a vážené priemery.
    types: "all" | "electricity" | "gas" | "water"
    """
    y = safe_get_int(year or kwargs.get('year'))
    t = (types or kwargs.get('types') or "all").lower()
    if not y:
        return {"error":"Chýba rok."}

    series = []
    # akumulátory pre vážené priemery
    e_kwh_sum = e_cost_sum = 0.0
    g_m3_sum = g_kwh_sum = g_cost_sum = 0.0
    w_m3_sum = w_cost_sum = 0.0

    for (yy, mm) in _month_seq_year(y):
        d = get_costs_data(yy, mm)
        comp = (d.get('energy') or {}).get('computed') or {}
        elc = comp.get('electricity') or {}
        gsc = comp.get('gas') or {}
        wtc = comp.get('water') or {}

        # mesačná položka
        line = {"month": mm}
        if t in ("all", "electricity"):
            e_kwh = float(elc.get('consumption_kwh') or 0.0)
            e_tot = float(elc.get('total_gross_eur') or 0.0)
            e_unit= float(elc.get('avg_unit_price_gross') or 0.0)
            line["electricity"] = {"cons_kwh": e_kwh, "total_br": e_tot, "unit_avg_gross": e_unit}
            e_kwh_sum += e_kwh; e_cost_sum += e_tot

        if t in ("all", "gas"):
            g_m3  = float(gsc.get('consumption_m3') or 0.0)
            g_kwh = float(gsc.get('consumption_kwh') or 0.0)
            g_tot = float(gsc.get('total_gross_eur') or 0.0)
            g_unit= float(gsc.get('avg_unit_price_gross') or 0.0)  # €/kWh
            line["gas"] = {"cons_m3": g_m3, "cons_kwh": g_kwh, "total_br": g_tot, "unit_avg_gross": g_unit}
            g_m3_sum += g_m3; g_kwh_sum += g_kwh; g_cost_sum += g_tot

        if t in ("all", "water"):
            w_m3  = float(wtc.get('delta_m3') or 0.0)
            w_tot = float(wtc.get('total_gross_eur') or 0.0)
            w_unit= float(wtc.get('avg_unit_price_gross') or 0.0)   # €/m3
            line["water"] = {"cons_m3": w_m3, "total_br": w_tot, "unit_avg_gross": w_unit}
            w_m3_sum += w_m3; w_cost_sum += w_tot

        series.append(line)

    summary = {}
    if t in ("all", "electricity"):
        summary["electricity"] = {
            "cons_kwh_sum": e_kwh_sum,
            "total_br_sum": e_cost_sum,
            "unit_avg_weighted": (e_cost_sum / e_kwh_sum) if e_kwh_sum>0 else 0.0
        }
    if t in ("all", "gas"):
        summary["gas"] = {
            "cons_m3_sum": g_m3_sum,
            "cons_kwh_sum": g_kwh_sum,
            "total_br_sum": g_cost_sum,
            "unit_avg_weighted": (g_cost_sum / g_kwh_sum) if g_kwh_sum>0 else 0.0  # €/kWh
        }
    if t in ("all", "water"):
        summary["water"] = {
            "cons_m3_sum": w_m3_sum,
            "total_br_sum": w_cost_sum,
            "unit_avg_weighted": (w_cost_sum / w_m3_sum) if w_m3_sum>0 else 0.0  # €/m3
        }

    return {"year": y, "types": t, "series": series, "summary": summary}

def get_energy_annual_report_html(year=None, types="all", **kwargs):
    """
    Tlačiteľný ročný report. types: all | electricity | gas | water
    """
    y = safe_get_int(year or kwargs.get('year'))
    t = (types or kwargs.get('types') or "all").lower()
    if not y:
        return "<h3>Chýba rok.</h3>"

    data = get_energy_annual_json(y, t)
    series = data.get('series', [])
    summary= data.get('summary', {})

    def table_for(kind):
        rows = []
        if kind == "electricity":
            rows.append("<tr><th>Mesiac</th><th class='num'>Spotreba (kWh)</th><th class='num'>Jedn. cena s DPH (€/kWh)</th><th class='num'>Celkom s DPH</th></tr>")
            for r in series:
                e = r.get('electricity') or {}
                rows.append(f"<tr><td>{str(r['month']).zfill(2)}</td>"
                            f"<td class='num'>{e.get('cons_kwh',0):.3f}</td>"
                            f"<td class='num'>{e.get('unit_avg_gross',0):.6f}</td>"
                            f"<td class='num'>€ {e.get('total_br',0):.2f}</td></tr>")
            s = summary.get('electricity') or {}
            rows.append(f"<tr><td><strong>Súčet / Vážený priemer</strong></td>"
                        f"<td class='num'><strong>{s.get('cons_kwh_sum',0):.3f}</strong></td>"
                        f"<td class='num'><strong>{s.get('unit_avg_weighted',0):.6f}</strong></td>"
                        f"<td class='num'><strong>€ {s.get('total_br_sum',0):.2f}</strong></td></tr>")
        if kind == "gas":
            rows.append("<tr><th>Mesiac</th><th class='num'>Spotreba (m³)</th><th class='num'>Spotreba (kWh)</th><th class='num'>Jedn. cena s DPH (€/kWh)</th><th class='num'>Celkom s DPH</th></tr>")
            for r in series:
                g = r.get('gas') or {}
                rows.append(f"<tr><td>{str(r['month']).zfill(2)}</td>"
                            f"<td class='num'>{g.get('cons_m3',0):.3f}</td>"
                            f"<td class='num'>{g.get('cons_kwh',0):.3f}</td>"
                            f"<td class='num'>{g.get('unit_avg_gross',0):.6f}</td>"
                            f"<td class='num'>€ {g.get('total_br',0):.2f}</td></tr>")
            s = summary.get('gas') or {}
            rows.append(f"<tr><td><strong>Súčet / Vážený priemer</strong></td>"
                        f"<td class='num'><strong>{s.get('cons_m3_sum',0):.3f}</strong></td>"
                        f"<td class='num'><strong>{s.get('cons_kwh_sum',0):.3f}</strong></td>"
                        f"<td class='num'><strong>{s.get('unit_avg_weighted',0):.6f}</strong></td>"
                        f"<td class='num'><strong>€ {s.get('total_br_sum',0):.2f}</strong></td></tr>")
        if kind == "water":
            rows.append("<tr><th>Mesiac</th><th class='num'>Spotreba (m³)</th><th class='num'>Jedn. cena s DPH (€/m³)</th><th class='num'>Celkom s DPH</th></tr>")
            for r in series:
                w = r.get('water') or {}
                rows.append(f"<tr><td>{str(r['month']).zfill(2)}</td>"
                            f"<td class='num'>{w.get('cons_m3',0):.3f}</td>"
                            f"<td class='num'>{w.get('unit_avg_gross',0):.6f}</td>"
                            f"<td class='num'>€ {w.get('total_br',0):.2f}</td></tr>")
            s = summary.get('water') or {}
            rows.append(f"<tr><td><strong>Súčet / Vážený priemer</strong></td>"
                        f"<td class='num'><strong>{s.get('cons_m3_sum',0):.3f}</strong></td>"
                        f"<td class='num'><strong>{s.get('unit_avg_weighted',0):.6f}</strong></td>"
                        f"<td class='num'><strong>€ {s.get('total_br_sum',0):.2f}</strong></td></tr>")
        return "<table class='table'>" + "".join(rows) + "</table>"

    kinds = ["electricity","gas","water"] if t=="all" else [t]
    sections = "".join([f"<h3 style='margin:16px 0 8px'>{'Elektrina' if k=='electricity' else ('Plyn' if k=='gas' else 'Voda')}</h3>{table_for(k)}"
                        for k in kinds])

    style = """
    <style>
      body{font-family:system-ui,Segoe UI,Arial,sans-serif;padding:16px}
      h2{margin:0 0 10px}
      table{width:100%; border-collapse:collapse}
      th,td{border:1px solid #ddd; padding:6px}
      th{text-align:left; background:#fafafa}
      .num{text-align:right}
    </style>
    """
    title = f"Energie – ročný prehľad {y}"
    return f"{style}<h2>{title}</h2>{sections}"
