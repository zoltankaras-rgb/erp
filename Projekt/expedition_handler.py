from validators import validate_required_fields, safe_get_float, safe_get_int
from logger import logger
import db_connector
from datetime import datetime
import math
import json
import secrets
import base64
from io import BytesIO

import importlib

def _get_qrcode():
    try:
        return importlib.import_module('qrcode')  # type: ignore
    except Exception:
        return None

try:
    qrcode = importlib.import_module('qrcode')  # type: ignore
except Exception:
    qrcode = None

# =================================================================
# === FUNKCIE PRE EXPEDÍCIU ===
# =================================================================
# expedition_handler.py
def get_batch_full_info(batch_id: int):
    hdr = db_connector.execute_query("""
        SELECT zv.id, zv.datum_vyroby, zv.planovane_mnozstvo, zv.skutocne_vyrobene, zv.stav,
               COALESCE(p1.nazov,p2.nazov) AS product_name,
               COALESCE(p1.ean,p2.ean)      AS ean
        FROM zaznamy_vyroba zv
        LEFT JOIN products  p1 ON p1.id=zv.vyrobok_id
        LEFT JOIN produkty  p2 ON p2.id=zv.vyrobok_id
        WHERE zv.id=%s
    """, (batch_id,), fetch='one') or {}

    rec = db_connector.execute_query("""
        SELECT r.id AS recept_id, r.nazov AS recept_nazov
        FROM recepty r
        WHERE r.vyrobok_id = %s
        LIMIT 1
    """, (hdr.get('id') and hdr.get('id')*0 + hdr.get('id'),), fetch='one') or {}

    ingredients = []
    if rec:
        rows = db_connector.execute_query("""
            SELECT COALESCE(sp1.nazov, sp2.nazov) AS surovina, rp.mnozstvo_na_davku
            FROM recepty_polozky rp
            LEFT JOIN products  sp1 ON sp1.id = rp.surovina_id
            LEFT JOIN produkty  sp2 ON sp2.id = rp.surovina_id
            WHERE rp.recept_id = %s
        """, (rec['recept_id'],), fetch='all') or []

        # škálovanie na reálne množstvo
        plan = float(hdr.get('planovane_mnozstvo') or 0) or 1.0
        real = float(hdr.get('skutocne_vyrobene') or 0) or plan
        scale = real/plan if plan else 1.0

        for r in rows:
            base = float(r.get('mnozstvo_na_davku') or 0)
            ingredients.append({
                "surovina": r.get('surovina') or '',
                "na_davku": round(base, 3),
                "na_real":  round(base*scale, 3),
            })

    return {"header": hdr, "recipe": rec, "ingredients": ingredients}

def _qr_data_uri(text: str):
    if not qrcode:
        return None
    img = qrcode.make(text)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
def get_accompanying_letter_data(batch_id: int):
    """
    Dáta pre Sprievodný list výrobku.
    Vráti: { date, items:[{productName, ean, unit, planQty, realQty, batchId}], barcode_value, barcode_png_data_url }
    """
    if not batch_id:
        return {"error": "Chýba batch_id"}

    row = db_connector.execute_query("""
        SELECT 
            zv.id                                        AS batch_id,
            DATE(zv.datum_vyroby)                        AS production_date,
            zv.planovane_mnozstvo                        AS plan_qty,
            zv.skutocne_vyrobene                         AS real_qty,
            COALESCE(p1.nazov, p2.nazov)                 AS product_name,
            COALESCE(p1.ean,   p2.ean)                   AS ean,
            COALESCE(p1.jednotka, p2.jednotka)           AS jednotka
        FROM zaznamy_vyroba zv
        LEFT JOIN products  p1 ON p1.id = zv.vyrobok_id
        LEFT JOIN produkty  p2 ON p2.id = zv.vyrobok_id
        WHERE zv.id = %s
        LIMIT 1
    """, (batch_id,), fetch='one')

    if not row:
        return {"error": "Dávka neexistuje."}

    # mapa jednotiek (prispôsob ak máš iné kódy)
    unit_map = {0:'kg', 1:'kg', 2:'ks', 3:'l', 4:'bal'}
    try:
        unit_str = unit_map.get(int(row.get('jednotka') or 0), 'kg')
    except Exception:
        unit_str = 'kg'

    item = {
        "productName": row.get("product_name") or "",
        "ean":         row.get("ean") or "",
        "unit":        unit_str,
        "planQty":     float(row.get("plan_qty") or 0),
        "realQty":     float(row.get("real_qty") or 0),
        "batchId":     int(row.get("batch_id"))
    }

    # QR kód – nech je skenovateľný reťazec, ktorý potom spracuješ v /scanPayload
    barcode_value = f"BATCH:{item['batchId']}"
    barcode_png = _qr_data_uri(barcode_value)

    # date pre šablónu (string)
    prod_date = row.get("production_date")
    date_str = prod_date.strftime("%Y-%m-%d") if hasattr(prod_date, "strftime") else str(prod_date)[:10]

    return {
        "date": date_str,
        "items": [item],
        "barcode_value": barcode_value,
        "barcode_png_data_url": barcode_png
    }
def get_expedition_data():
    """
    Dashboard expedície – prehľad finálnych výrobkov, inventúr a denných dávok.
      - recent_batches: posledných 10 ukončených dávok (zaznamy_vyroba)
      - central_stock: stav centrálneho skladu (sklad_id = 2)
      - recent_inventories: posledných 5 inventúr v sklade 2
      - pendingTasks: dočasne prázdne (UI sekciu skryje)
    """
    # 1) Posledné ukončené dávky (názov z products/produkty)
    try:
        recent_batches = db_connector.execute_query("""
            SELECT
                zv.id                                         AS id,
                zv.datum_vyroby                               AS datum_vyroby,
                COALESCE(p1.nazov, p2.nazov, CONCAT('ID ', zv.vyrobok_id)) AS nazov,
                zv.skutocne_vyrobene                          AS realne_mnozstvo,
                zv.stav                                       AS stav
            FROM zaznamy_vyroba zv
            LEFT JOIN products  p1 ON p1.id = zv.vyrobok_id
            LEFT JOIN produkty  p2 ON p2.id = zv.vyrobok_id
            WHERE zv.stav = 'Ukončené'
            ORDER BY zv.datum_vyroby DESC
            LIMIT 10
        """)
    except Exception:
        recent_batches = []

    # 2) Stav centrálneho skladu – sklad_id = 2
    try:
        central_stock = db_connector.execute_query("""
            SELECT
                sp.produkt_id                                  AS id,
                COALESCE(p1.nazov, p2.nazov)                   AS nazov,
                COALESCE(p1.typ, p2.typ)                       AS typ,
                sp.mnozstvo                                    AS mnozstvo,
                COALESCE(p1.jednotka, p2.jednotka)             AS jednotka
            FROM sklad_polozky sp
            LEFT JOIN products  p1 ON p1.id = sp.produkt_id
            LEFT JOIN produkty  p2 ON p2.id = sp.produkt_id
            WHERE sp.sklad_id = 2
            ORDER BY (COALESCE(p1.nazov, p2.nazov) IS NULL), COALESCE(p1.nazov, p2.nazov)
            LIMIT 20
        """)
    except Exception:
        central_stock = []

    # 3) Posledné inventúry v sklade 2
    try:
        recent_inventories = db_connector.execute_query("""
            SELECT
                i.id,
                COALESCE(i.datum_end, i.datum_start) AS datum,
                COUNT(ip.id) AS poloziek
            FROM inventury i
            LEFT JOIN inventury_polozky ip ON ip.inventura_id = i.id
            WHERE i.sklad_id = 2
            GROUP BY i.id, datum
            ORDER BY datum DESC
            LIMIT 5
        """)
    except Exception:
        recent_inventories = []

    pendingTasks = []
    return {
        "recent_batches":     recent_batches,
        "central_stock":      central_stock,
        "recent_inventories": recent_inventories,
        "pendingTasks":       pendingTasks
    }
# expedition_handler.py
def get_production_dates(limit=30):
    sql = """
        SELECT d
        FROM (
          SELECT DATE(zv.datum_vyroby) AS d,
                 SUM(CASE WHEN COALESCE(zv.stav,'')='Ukončené' THEN 1 ELSE 0 END) AS closed_cnt,
                 COUNT(*) AS total_cnt
          FROM zaznamy_vyroba zv
          WHERE zv.datum_vyroby IS NOT NULL
          GROUP BY DATE(zv.datum_vyroby)
        ) t
        WHERE total_cnt > closed_cnt
        ORDER BY d DESC
        LIMIT %s
    """
    rows = db_connector.execute_query(sql, (limit,), fetch='all') or []
    return [str(r['d']) for r in rows]

def get_productions_by_date(date_payload=None, **kwargs):
    """
    Vráti výrobné dávky pre zvolený deň (na prevzatie v expedícii).

    Parametre akceptované rôznymi routami:
      - string: 'YYYY-MM-DD'
      - dict:   {'date': 'YYYY-MM-DD'} alebo {'datum': ...} alebo {'date_string': ...}
      - kwargs: date=..., datum=..., date_string=...

    Výstup (zoznam dictov pre expedicia.js):
      - batchId, status, productName, plannedQty, realQty, mj ('kg' ako default),
        datum_vyroby (YYYY-MM-DD), poznamka_expedicie (prázdne)
    """
    # --- 1) extrakcia dátumu z rôznych foriem volania ---
    date_str = None

    # a) ak prišlo ako dict v 1. parametri
    if isinstance(date_payload, dict):
        date_str = date_payload.get('date') or date_payload.get('datum') or date_payload.get('date_string')
    # b) ak prišiel priamo string
    elif isinstance(date_payload, str):
        date_str = date_payload
    # c) ak prišlo cez kwargs
    if not date_str:
        date_str = kwargs.get('date') or kwargs.get('datum') or kwargs.get('date_string')

    if not date_str:
        # nič nepošleme – front-end to zvládne a zobrazí na stránke informáciu
        return []

    date_str = str(date_str)[:10]  # normalizácia 'YYYY-MM-DD'

    # --- 2) dotaz – len reálne stĺpce podľa tvojej DB ---
    query = """
        SELECT
            zv.id                                        AS batchId,
            zv.stav                                      AS status,
            COALESCE(p1.nazov, p2.nazov)                AS productName,
            zv.planovane_mnozstvo                       AS plannedQty,
            zv.skutocne_vyrobene                        AS realQty,
            DATE(zv.datum_vyroby)                       AS datum_vyroby
        FROM zaznamy_vyroba zv
        LEFT JOIN products  p1 ON p1.id = zv.vyrobok_id
        LEFT JOIN produkty  p2 ON p2.id = zv.vyrobok_id
        WHERE DATE(zv.datum_vyroby) = %s
          AND COALESCE(zv.stav,'') = 'Prijaté, čaká na tlač'
        ORDER BY zv.id ASC
    """

    rows = db_connector.execute_query(query, (date_str,)) or []

    # --- 3) konverzia na štruktúru, ktorú očakáva expedicia.js ---
    result = []
    for r in rows:
        dv = r.get('datum_vyroby')
        if hasattr(dv, 'strftime'):
            dv = dv.strftime('%Y-%m-%d')
        else:
            dv = str(dv)[:10] if dv is not None else None

        result.append({
            "batchId":               r.get("batchId"),
            "status":                r.get("status"),
            "productName":           r.get("productName") or "",
            "plannedQty":            float(r.get("plannedQty") or 0),
            "realQty":               float(r.get("realQty") or 0),
            "expectedPieces":        None,        # UI to používa len ak mj == 'ks'
            "realPieces":            None,        # dtto
            "mj":                    "kg",        # default – ak chceš 'ks' pre niektoré výrobky, doplníme mapovanie
            "datum_vyroby":          dv,
            "poznamka_expedicie":    ""
        })

    return result

def get_production_dates():
    """
    Zoznam dátumov (YYYY-MM-DD), pre ktoré existujú výrobné dávky vhodné na prevzatie.
    Logika:
      - berieme len záznamy so zadaným datum_vyroby,
      - vylúčime jednoznačne ukončené/zrušené stavy (aby šlo o "na prevzatie"),
      - zoradíme zostupne a ohraničíme na posledných 30 dní.
    Ak nič nevyhovuje (napr. iné názvy stavov), vrátime fallback: posledných 14 rôznych dátumov.
    """
    # 1) pokus: všetko okrem ukončených/zrušených
    rows = db_connector.execute_query("""
        SELECT DISTINCT DATE(zv.datum_vyroby) AS d
        FROM zaznamy_vyroba zv
        WHERE zv.datum_vyroby IS NOT NULL
          AND (zv.stav IS NULL OR zv.stav NOT IN ('Ukončené','Zrušené'))
        ORDER BY d DESC
        LIMIT 30
    """) or []

    dates = []
    for r in rows:
        d = r.get('d')
        # DB môže vrátiť date/datetime/str – normalizujeme na 'YYYY-MM-DD'
        dates.append(d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10])

    # 2) fallback – ak vyššie nič nenašlo (iné názvy stavov)
    if not dates:
        rows2 = db_connector.execute_query("""
            SELECT DISTINCT DATE(zv.datum_vyroby) AS d
            FROM zaznamy_vyroba zv
            WHERE zv.datum_vyroby IS NOT NULL
            ORDER BY d DESC
            LIMIT 14
        """) or []
        for r in rows2:
            d = r.get('d')
            dates.append(d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10])

    return dates
def complete_multiple_productions(items=None, **kwargs):
    if items is None:
        items = kwargs.get('items')
    if isinstance(items, dict) and 'items' in items:
        items = items['items']
    if not isinstance(items, list):
        return {"ok": False, "message": "Neplatný formát dát (očakáva sa zoznam položiek)."}

    updated = 0
    for it in items:
        try:
            batch_id = it.get("batchId")
            if not batch_id:
                continue

            status_raw = (it.get("visualCheckStatus") or "").strip().upper()
            actual_val = it.get("actualValue")

            if status_raw == "OK":
                new_status = "Prijaté, čaká na tlač"
            elif "NEPRIJ" in status_raw:
                new_status = "NEPRIJATÉ"
            else:
                new_status = "Skontrolované"

            wrote_qty = False
            if status_raw == "OK" and actual_val not in (None, "", "null"):
                try:
                    qty = float(actual_val)
                    db_connector.execute_query(
                        "UPDATE zaznamy_vyroba SET skutocne_vyrobene=%s, stav=%s WHERE id=%s",
                        (qty, new_status, batch_id)
                    )
                    wrote_qty = True
                    updated += 1
                except Exception:
                    wrote_qty = False

            if not wrote_qty:
                db_connector.execute_query(
                    "UPDATE zaznamy_vyroba SET stav=%s WHERE id=%s",
                    (new_status, batch_id)
                )
                updated += 1

        except Exception:
            continue

    return {"ok": True, "updated": updated, "message": f"Prevzatie uložené ({updated}) položiek."}


import json

def finalize_day(payload=None, **kwargs):
    """
    Uzávierka dňa pre expedíciu:
      - nájde všetky dávky v stave 'Prijaté, čaká na tlač' pre zvolený deň,
      - za každú vytvorí PRÍJEM do inventory_movements (sklad_id=2, movement_type=1),
      - nastaví stav dávky na 'Ukončené',
      - vráti súhrn.
    Očakáva: payload = {'date_string': 'YYYY-MM-DD', 'workerName': '...'} (worker nepovinný).
    """
    # --- 1) vyparsuj dátum ---
    date_str = None
    if isinstance(payload, dict):
        date_str = payload.get('date_string') or payload.get('date') or payload.get('datum')
    if not date_str:
        date_str = kwargs.get('date_string') or kwargs.get('date') or kwargs.get('datum')
    if not date_str:
        return {"ok": False, "message": "Chýba dátum uzávierky (date_string)."}

    date_str = str(date_str)[:10]
    worker = None
    if isinstance(payload, dict):
        worker = payload.get('workerName') or payload.get('worker_name')

    # --- 2) načítaj prijaté dávky dňa (čo treba prijať na sklad) ---
    rows = db_connector.execute_query("""
        SELECT
            zv.id                AS batchId,
            zv.vyrobok_id        AS produkt_id,
            zv.skutocne_vyrobene AS qty_kg,
            zv.celkova_cena_surovin AS raw_cost
        FROM zaznamy_vyroba zv
        WHERE DATE(zv.datum_vyroby) = %s
          AND COALESCE(zv.stav,'') = 'Prijaté, čaká na tlač'
    """, (date_str,)) or []

    if not rows:
        return {"ok": True, "inserted": 0, "message": f"Pre {date_str} nie sú žiadne prijaté dávky na uzávierku."}

    inserted = 0
    for r in rows:
        batch_id   = r.get("batchId")
        produkt_id = r.get("produkt_id")
        qty        = float(r.get("qty_kg") or 0)
        raw_cost   = float(r.get("raw_cost") or 0)

        if not produkt_id or qty <= 0:
            # ak nie je reálna váha, príjem nerobíme – len uzavrieme stav
            db_connector.execute_query("UPDATE zaznamy_vyroba SET stav='Ukončené' WHERE id=%s", (batch_id,))
            continue

        # jednotková cena (ak máš surovinový náklad na dávku)
        unit_cost = round(raw_cost / qty, 4) if raw_cost > 0 else 0.0

        note = json.dumps({
            "finalized_by": worker or "",
            "date": date_str
        }, separators=(",",":"))[:250]

        # --- 3) vlož PRÍJEM do inventory_movements (sklad 2) ---
        db_connector.execute_query("""
            INSERT INTO inventory_movements
                (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
            VALUES
                (NOW(6), %s, %s, %s, %s, %s, 'zaznamy_vyroba', %s, %s)
        """, (2, produkt_id, qty, unit_cost, 1, batch_id, note))
        inserted += 1

        # --- 4) uzavri dávku ---
        db_connector.execute_query("UPDATE zaznamy_vyroba SET stav='Ukončené' WHERE id=%s", (batch_id,))

    return {"ok": True, "inserted": inserted,
            "message": f"Uzávierka hotová. Zapísané príjmy: {inserted} (deň {date_str})."}

# expedition_handler.py
def get_acceptance_doc(accept_id: str):
    """
    Vytiahne položky príjemky z 'zaznamy_prijem' podľa tagu ACC v stĺpci 'dodavatel'.
    """
    if not accept_id:
        return {"error": "missing accept_id"}

    sql = """
        SELECT
            zp.datum,
            COALESCE(p.nazov, pp.nazov) AS produkt,
            zp.mnozstvo AS qty,
            COALESCE(zp.cena, 0) AS unit_cost
        FROM zaznamy_prijem zp
        LEFT JOIN products  p  ON p.id  = zp.produkt_id
        LEFT JOIN produkty  pp ON pp.id = zp.produkt_id
        WHERE zp.sklad_id = 2 AND zp.dodavatel LIKE %s
        ORDER BY zp.id
    """
    rows = db_connector.execute_query(sql, (f"%ACC:{accept_id}%",), fetch='all') or []
    if not rows:
        return {"error": "Príjemka neexistuje (neplatné accept_id)."}

    total = sum(float(r.get('qty') or 0) for r in rows)
    dt = rows[0].get('datum')
    when = dt.strftime("%d.%m.%Y %H:%M") if hasattr(dt, "strftime") else str(dt)

    return {
        "accept_id": accept_id,
        "when": when,
        "total_kg": round(total, 3),
        "items": [{
            "produkt": r.get('produkt') or '',
            "qty": float(r.get('qty') or 0),
            "unit_cost": float(r.get('unit_cost') or 0),
        } for r in rows]
    }
def get_accepted_by_date(date_str: str):
    sql = """
        SELECT
            zv.id AS batchId,
            COALESCE(p1.nazov, p2.nazov) AS productName,
            zv.skutocne_vyrobene        AS realQty,
            DATE(zv.datum_vyroby)       AS datum_vyroby
        FROM zaznamy_vyroba zv
        LEFT JOIN products  p1 ON p1.id = zv.vyrobok_id
        LEFT JOIN produkty  p2 ON p2.id = zv.vyrobok_id
        WHERE DATE(zv.datum_vyroby)=%s
          AND COALESCE(zv.stav,'')='Prijaté, čaká na tlač'
        ORDER BY zv.id
    """
    return db_connector.execute_query(sql, (date_str,), fetch='all') or []
def get_accompanying_letter_data(batch_id):
    """Získa dáta pre sprievodný list (opravené na reálnu schému)."""
    if not batch_id:
        return {"error":"Chýba batch_id"}
    row = db_connector.execute_query("""
        SELECT 
            zv.id                                        AS batch_id,
            DATE(zv.datum_vyroby)                        AS production_date,
            zv.planovane_mnozstvo                        AS plan_qty,
            zv.skutocne_vyrobene                         AS real_qty,
            COALESCE(p1.nazov, p2.nazov)                 AS product_name,
            COALESCE(p1.ean,   p2.ean)                   AS ean,
            COALESCE(p1.jednotka, p2.jednotka)           AS jednotka
        FROM zaznamy_vyroba zv
        LEFT JOIN products  p1 ON p1.id = zv.vyrobok_id
        LEFT JOIN produkty  p2 ON p2.id = zv.vyrobok_id
        WHERE zv.id = %s
        LIMIT 1
    """, (batch_id,), fetch='one')
    if not row:
        return {"error":"Dávka neexistuje."}
    unit_map = {0:'kg',1:'kg',2:'ks',3:'l',4:'bal'}
    try:
        unit_str = unit_map.get(int(row.get('jednotka') or 0), 'kg')
    except Exception:
        unit_str = 'kg'
    item = {
        "productName": row.get("product_name") or "",
        "ean":         row.get("ean") or "",
        "unit":        unit_str,
        "planQty":     float(row.get("plan_qty") or 0),
        "realQty":     float(row.get("real_qty") or 0),
        "batchId":     int(row.get("batch_id"))
    }
    barcode_value = f"BATCH:{item['batchId']}"
    try:
        from io import BytesIO as _BIO
        import base64 as _b64
        _mod = _get_qrcode()
        if _mod:
            buf = _BIO()
            _mod.make(barcode_value).save(buf, format='PNG')
            barcode_png = 'data:image/png;base64,' + _b64.b64encode(buf.getvalue()).decode('ascii')
        else:
            raise Exception('qrcode not available')
    except Exception:
        barcode_png = None
    prod_date = row.get("production_date")
    date_str = prod_date.strftime("%Y-%m-%d") if hasattr(prod_date, "strftime") else str(prod_date)[:10]
    return {"date":date_str,"items":[item],"barcode_value":barcode_value,"barcode_png_data_url":barcode_png}

def get_slicable_products():
    """Získa zoznam všetkých produktov, ktoré sú určené na krájanie."""
    return db_connector.execute_query("SELECT ean, nazov_vyrobku as name FROM produkty WHERE typ_polozky = 'VYROBOK_KRAJANY' ORDER BY nazov_vyrobku")

def start_slicing_request(packaged_product_ean, planned_pieces):
    """Spracuje požiadavku na krájanie - odpíše zdrojový produkt a vytvorí úlohu."""
    if not all([packaged_product_ean, planned_pieces and safe_get_int(planned_pieces) > 0]): return {"error": "Musíte vybrať produkt a zadať platný počet kusov."}
    
    p_info = db_connector.execute_query("SELECT target.ean as target_ean, target.nazov_vyrobku as target_name, target.vaha_balenia_g as target_weight_g, target.zdrojovy_ean, source.nazov_vyrobku as source_name FROM produkty as target LEFT JOIN produkty as source ON target.zdrojovy_ean = source.ean WHERE target.ean = %s", (packaged_product_ean,), fetch='one')
    if not p_info or not p_info.get('zdrojovy_ean'): return {"error": "Produkt nebol nájdený alebo nie je prepojený so zdrojovým produktom."}
    
    required_kg = (safe_get_int(planned_pieces) * safe_get_float(p_info['target_weight_g'])) / 1000
    cost_info = db_connector.execute_query("SELECT cena_za_jednotku as unit_cost FROM zaznamy_vyroba WHERE nazov_vyrobku = %s AND stav = 'Ukončené' ORDER BY datum_ukoncenia DESC LIMIT 1", (p_info['source_name'],), fetch='one')
    total_cost = required_kg * safe_get_float(cost_info.get('unit_cost') or 0.0)
    
    db_connector.execute_query("UPDATE produkty SET aktualny_sklad_finalny_kg = aktualny_sklad_finalny_kg - %s WHERE ean = %s", (required_kg, p_info['zdrojovy_ean']), fetch='none')
    
    batch_id = f"KRAJANIE-{p_info['target_name'][:10]}-{datetime.now().strftime('%y%m%d%H%M')}"
    details = json.dumps({"operacia": "krajanie", "cielovyEan": p_info["target_ean"], "cielovyNazov": p_info["target_name"], "planovaneKs": planned_pieces})
    log_params = (batch_id, 'Prebieha krájanie', datetime.now(), p_info['source_name'], required_kg, datetime.now(), total_cost, details)
    db_connector.execute_query("INSERT INTO zaznamy_vyroba (id_davky, stav, datum_vyroby, nazov_vyrobku, planovane_mnozstvo_kg, datum_spustenia, celkova_cena_surovin, detaily_zmeny) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", log_params, fetch='none')
    
    return {"message": f"Požiadavka vytvorená. Odpočítaných {required_kg:.2f} kg produktu '{p_info['source_name']}'."}

def finalize_slicing_transaction(log_id, actual_pieces):
    """Finalizuje úlohu krájania."""
    if not all([log_id, actual_pieces is not None and safe_get_int(actual_pieces) >= 0]): return {"error": "Chýba ID úlohy alebo platný počet kusov."}

    original_task = db_connector.execute_query("SELECT * FROM zaznamy_vyroba WHERE id_davky = %s AND stav = 'Prebieha krájanie'", (log_id,), 'one')
    if not original_task: return {"error": f"Úloha krájania {log_id} nebola nájdená alebo už bola spracovaná."}
    
    try: details = json.loads(original_task.get('detaily_zmeny'))
    except: return {"error": "Chyba v zázname o krájaní: poškodené detaily."}
    
    target_ean, target_name = details.get('cielovyEan'), details.get('cielovyNazov')
    target_product = db_connector.execute_query("SELECT vaha_balenia_g FROM produkty WHERE ean = %s", (target_ean,), 'one')
    if not target_product or not target_product.get('vaha_balenia_g'): return {"error": f"Produkt '{target_name}' nemá definovanú váhu balenia."}
    
    real_kg = (safe_get_int(actual_pieces) * safe_get_float(target_product['vaha_balenia_g'])) / 1000
    update_params = ("Prijaté, čaká na tlač", target_name, actual_pieces, real_kg, log_id)
    db_connector.execute_query("UPDATE produkty SET stav = %s, nazov_vyrobku = %s, realne_mnozstvo_ks = %s, realne_mnozstvo_kg = %s WHERE id_davky = %s", update_params, 'none')

    return {"message": f"Úloha pre '{target_name}' ukončená s {actual_pieces} ks."}

def get_all_final_products():
    """Získa zoznam všetkých finálnych produktov (kg aj ks)."""
    return db_connector.execute_query("SELECT ean, nazov_vyrobku as name, mj as unit FROM produkty WHERE typ_polozky IN ('VÝROBOK', 'VYROBOK_KRAJANY', 'VÝROBOK_KUSOVY') ORDER BY nazov_vyrobku")

def manual_receive_product(data):
    """Spracuje manuálny príjem finálneho výrobku na sklad."""
    ean, qty_str, worker, date = data.get('ean'), data.get('quantity'), data.get('workerName'), data.get('receptionDate')
    if not all([ean, qty_str, worker, date]): return {"error": "Všetky polia sú povinné."}
    
    product = db_connector.execute_query("SELECT nazov_vyrobku, mj, vaha_balenia_g FROM produkty WHERE ean = %s", (ean,), 'one')
    if not product: return {"error": "Produkt s daným EAN nebol nájdený."}

    qty = safe_get_float(qty_str)
    qty_kg = qty if product['mj'] == 'kg' else (qty * safe_get_float(product.get('vaha_balenia_g') or 0.0) / 1000)
    db_connector.execute_query("UPDATE produkty SET aktualny_sklad_finalny_kg = aktualny_sklad_finalny_kg + %s WHERE ean = %s", (qty_kg, ean), 'none')

    batch_id = f"MANUAL-PRIJEM-{datetime.now().strftime('%y%m%d%H%M')}"
    log_params = (batch_id, 'Ukončené', date, datetime.now(), product['nazov_vyrobku'], qty if product['mj'] == 'kg' else None, qty if product['mj'] == 'ks' else None, f"Manuálne prijal: {worker}")
    db_connector.execute_query("INSERT INTO zaznamy_vyroba (id_davky, stav, datum_vyroby, datum_ukoncenia, nazov_vyrobku, realne_mnozstvo_kg, realne_mnozstvo_ks, poznamka_expedicie) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", log_params, 'none')
    return {"message": f"Úspešne prijatých {qty} {product['mj']} produktu '{product['nazov_vyrobku']}'."}

def log_manual_damage(data):
    """Zapíše manuálnu škodu a odpočíta produkt zo skladu."""
    ean, qty_str, worker, note = data.get('ean'), data.get('quantity'), data.get('workerName'), data.get('note')
    if not all([ean, qty_str, worker, note]): return {"error": "Všetky polia sú povinné."}

    product = db_connector.execute_query("SELECT nazov_vyrobku, mj, vaha_balenia_g FROM produkty WHERE ean = %s", (ean,), 'one')
    if not product: return {"error": "Produkt s daným EAN nebol nájdený."}
    
    qty = safe_get_float(qty_str)
    qty_kg = qty if product['mj'] == 'kg' else (qty * safe_get_float(product.get('vaha_balenia_g') or 0.0) / 1000)
    db_connector.execute_query("UPDATE produkty SET aktualny_sklad_finalny_kg = aktualny_sklad_finalny_kg - %s WHERE ean = %s", (qty_kg, ean), 'none')

    skoda_params = (datetime.now(), f"MANUAL-SKODA-{datetime.now().strftime('%y%m%d%H%M')}", product['nazov_vyrobku'], f"{qty} {product['mj']}", note, worker)
    db_connector.execute_query("INSERT INTO skody (datum, id_davky, nazov_vyrobku, mnozstvo, dovod, pracovnik) VALUES (%s, %s, %s, %s, %s, %s)", skoda_params, 'none')
    return {"message": f"Škoda zapísaná. Sklad znížený o {qty_kg:.2f} kg."}

def get_products_for_inventory():
    """
    Získa zoznam všetkých finálnych a tovarových produktov
    pre zobrazenie v inventúrnom formulári expedície.
    """
    query = """
        SELECT 
            p.ean, p.nazov_vyrobku, p.predajna_kategoria, 
            p.aktualny_sklad_finalny_kg, p.mj, p.vaha_balenia_g
        FROM produkty p 
        WHERE p.typ_polozky LIKE 'VÝROBOK%%' OR p.typ_polozky LIKE 'TOVAR%%'
        ORDER BY p.predajna_kategoria, p.nazov_vyrobku
    """
    products = db_connector.execute_query(query)
    
    categorized_products = {}
    for product in products:
        category = product.get('predajna_kategoria') or 'Nezaradené'
        if category not in categorized_products:
            categorized_products[category] = []
        
        kg_stock = safe_get_float(product.get('aktualny_sklad_finalny_kg') or 0.0)
        weight_g = safe_get_float(product.get('vaha_balenia_g') or 0.0)
        if product.get('mj') == 'ks' and weight_g > 0:
            product['system_stock_display'] = f"{(kg_stock * 1000 / weight_g):.2f}".replace('.', ',')
        else:
            product['system_stock_display'] = f"{kg_stock:.2f}".replace('.', ',')

        categorized_products[category].append(product)
        
    return categorized_products

def submit_product_inventory(inventory_data, worker_name):
    """
    Spracuje dáta z inventúry finálnych produktov, zapíše rozdiely
    a aktualizuje stav skladu.
    """
    if not inventory_data:
        return {"error": "Neboli zadané žiadne platné reálne stavy."}

    eans = [item['ean'] for item in inventory_data]
    if not eans:
        return {"message": "Žiadne položky na spracovanie."}
    placeholders = ','.join(['%s'] * len(eans))
    
    products_query = f"""
        SELECT 
            p.ean, p.nazov_vyrobku, p.predajna_kategoria,
            p.aktualny_sklad_finalny_kg, p.mj, p.vaha_balenia_g,
            (SELECT zv.cena_za_jednotku 
             FROM zaznamy_vyroba zv 
             WHERE zv.nazov_vyrobku = p.nazov_vyrobku AND zv.stav = 'Ukončené' AND zv.cena_za_jednotku > 0
             ORDER BY zv.datum_ukoncenia DESC LIMIT 1) as unit_cost
        FROM produkty p
        WHERE p.ean IN ({placeholders})
    """
    all_products_list = db_connector.execute_query(products_query, tuple(eans))
    products_map = {p['ean']: p for p in all_products_list}

    differences_to_log = []
    updates_to_produkty = []

    for item in inventory_data:
        ean, real_qty_str = item.get('ean'), item.get('realQty')
        product_info = products_map.get(ean)
        
        if not all([ean, real_qty_str, product_info]): continue

        real_qty_num = safe_get_float(real_qty_str.replace(',', '.'))
        real_qty_kg = 0
        
        if product_info['mj'] == 'kg':
            real_qty_kg = real_qty_num
        elif product_info['mj'] == 'ks' and product_info.get('vaha_balenia_g'):
            real_qty_kg = (real_qty_num * safe_get_float(product_info['vaha_balenia_g'])) / 1000.0
        
        system_qty_kg = safe_get_float(product_info.get('aktualny_sklad_finalny_kg') or 0.0)
        
        if abs(real_qty_kg - system_qty_kg) > 0.001:
            diff_kg = real_qty_kg - system_qty_kg
            unit_cost = safe_get_float(product_info.get('unit_cost') or 0.0)
            price_per_kg = unit_cost
            
            if product_info['mj'] == 'ks' and product_info.get('vaha_balenia_g') and product_info['vaha_balenia_g'] > 0:
                price_per_kg = (unit_cost * 1000) / safe_get_float(product_info['vaha_balenia_g'])

            diff_value_eur = diff_kg * price_per_kg

            log_entry = (datetime.now(), ean, product_info['nazov_vyrobku'], product_info['predajna_kategoria'], system_qty_kg, real_qty_kg, diff_kg, diff_value_eur, worker_name)
            differences_to_log.append(log_entry)
            updates_to_produkty.append((real_qty_kg, ean))

    if differences_to_log:
        db_connector.execute_query(
            """INSERT INTO inventurne_rozdiely_produkty 
               (datum, ean_produktu, nazov_produktu, predajna_kategoria, systemovy_stav_kg, realny_stav_kg, rozdiel_kg, hodnota_rozdielu_eur, pracovnik) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            differences_to_log, fetch='none', multi=True
        )
    if updates_to_produkty:
        db_connector.execute_query(
            "UPDATE produkty SET aktualny_sklad_finalny_kg = %s WHERE ean = %s",
            updates_to_produkty, fetch='none', multi=True
        )
    
    return {"message": f"Inventúra finálnych produktov dokončená. Aktualizovaných {len(updates_to_produkty)} položiek."}

def get_traceability_info(batch_id):
    """
    Získa všetky dostupné informácie o výrobnej šarži pre účely sledovateľnosti.
    """
    if not batch_id:
        return {"error": "Chýba ID šarže."}

    batch_info_query = """
        SELECT 
            zv.id_davky, zv.nazov_vyrobku, zv.stav,
            zv.datum_vyroby, zv.datum_spustenia, zv.datum_ukoncenia,
            zv.planovane_mnozstvo_kg, zv.realne_mnozstvo_kg, zv.realne_mnozstvo_ks,
            p.mj, p.ean
        FROM zaznamy_vyroba zv
        LEFT JOIN produkty p ON zv.nazov_vyrobku = p.nazov_vyrobku
        WHERE zv.id_davky = %s
    """
    batch_info = db_connector.execute_query(batch_info_query, (batch_id,), fetch='one')

    if not batch_info:
        return {"error": f"Šarža s ID '{batch_id}' nebola nájdená."}

    ingredients_query = """
        SELECT nazov_suroviny, pouzite_mnozstvo_kg
        FROM zaznamy_vyroba_suroviny
        WHERE id_davky = %s
        ORDER BY pouzite_mnozstvo_kg DESC
    """
    ingredients = db_connector.execute_query(ingredients_query, (batch_id,))

    return {
        "batch_info": batch_info,
        "ingredients": ingredients
    }
def get_slicing_needs_from_orders(plan_date):
    """
    Agreguje B2B/B2C objednávky pre daný dátum do požiadaviek na krájanie.
    NIČ NEZAPISUJE – len vráti zoznam {target_ean, target_name, planned_pieces, source_ean, source_name, target_weight_g}.
    """
    if not plan_date:
        return []

    # B2B podľa požadovaného dátumu dodania
    b2b_rows = db_connector.execute_query("""
        SELECT 
            p.ean                 AS target_ean,
            p.nazov_vyrobku       AS target_name,
            p.vaha_balenia_g      AS target_weight_g,
            p.zdrojovy_ean        AS source_ean,
            ps.nazov_vyrobku      AS source_name,
            SUM(oi.mnozstvo)      AS planned_pieces
        FROM b2b_objednavky o
        JOIN b2b_objednavky_polozky oi ON oi.objednavka_id = o.id
        JOIN produkty p                 ON p.ean = oi.ean_produktu
        LEFT JOIN produkty ps           ON ps.ean = p.zdrojovy_ean
        WHERE DATE(o.pozadovany_datum_dodania) = %s
          AND (p.typ_polozky LIKE 'VYROBOK_KRAJANY%%' OR p.typ_polozky LIKE 'VÝROBOK_KRAJANY%%')
        GROUP BY p.ean, p.nazov_vyrobku, p.vaha_balenia_g, p.zdrojovy_ean, ps.nazov_vyrobku
        ORDER BY p.nazov_vyrobku
    """, (plan_date,))

    # B2C podľa dátumu objednávky (alebo si upravíš na plán expedície)
    try:
        b2c_rows = db_connector.execute_query("""
            SELECT 
                p.ean                 AS target_ean,
                p.nazov_vyrobku       AS target_name,
                p.vaha_balenia_g      AS target_weight_g,
                p.zdrojovy_ean        AS source_ean,
                ps.nazov_vyrobku      AS source_name,
                SUM(oi.mnozstvo)      AS planned_pieces
            FROM b2c_objednavky o
            JOIN b2c_objednavky_polozky oi ON oi.objednavka_id = o.id
            JOIN produkty p                 ON p.id = oi.produkt_id
            LEFT JOIN produkty ps           ON ps.ean = p.zdrojovy_ean
            WHERE DATE(o.datum) = %s
              AND (p.typ_polozky LIKE 'VYROBOK_KRAJANY%%' OR p.typ_polozky LIKE 'VÝROBOK_KRAJANY%%')
            GROUP BY p.ean, p.nazov_vyrobku, p.vaha_balenia_g, p.zdrojovy_ean, ps.nazov_vyrobku
            ORDER BY p.nazov_vyrobku
        """, (plan_date,))
    except Exception:
        b2c_rows = []

    # zlep: zgrupuj rovnaké target_ean z B2B+B2C
    combined = {}
    for row in (b2b_rows or []) + (b2c_rows or []):
        key = row['target_ean']
        if key not in combined:
            combined[key] = {**row}
        else:
            combined[key]['planned_pieces'] = (combined[key].get('planned_pieces') or 0) + (row.get('planned_pieces') or 0)
    return list(combined.values())
import json, uuid
from datetime import datetime

def _short_id():
    return uuid.uuid4().hex[:10]

# expedition_handler.py

import secrets, re
from decimal import Decimal, InvalidOperation

def accept_productions(payload: dict):
    """
    Očakáva payload:
      { "items": [{ "batchId", "workerName", "actualValue", "note"?, "unit"?, "productName"? }, ...] }
    """
    items = (payload or {}).get('items') or []
    if not items:
        return {"error": "Žiadne položky na prevzatie."}

    def _to_qty(x):
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None
        # toleruj 1 234,567  alebo 1,5kg / 2ks / 3l / 4bal
        s = s.replace(" ", "").replace(",", ".")
        s = re.sub(r"(kg|ks|l|bal)$", "", s, flags=re.IGNORECASE)
        try:
            q = Decimal(s)
            if q <= 0:
                return None
            return q.quantize(Decimal("0.001"))
        except InvalidOperation:
            return None

    CENTRAL_WAREHOUSE_ID = 2
    NEW_STATUS = 'Prijaté, čaká na tlač'

    conn = db_connector.get_connection()
    accepted, errors = [], []
    try:
        cur = conn.cursor(dictionary=True)

        for it in items:
            try:
                batch_id = int(it.get('batchId') or 0)
                worker   = (it.get('workerName') or 'expedícia').strip()
                note_ui  = (it.get('note') or '').strip()
                qty      = _to_qty(it.get('actualValue'))

                if batch_id <= 0 or qty is None:
                    raise ValueError("Neplatné batchId alebo množstvo (skontroluj, či nie je 0 a čiarka vs. bodka).")

                # 1) načítaj dávku – vyrobok_id môže byť NULL, ošetríme fallbackom
                cur.execute("""
                    SELECT id, vyrobok_id, COALESCE(skutocne_vyrobene, 0) AS real_qty
                    FROM zaznamy_vyroba
                    WHERE id = %s
                """, (batch_id,))
                zv = cur.fetchone()
                if not zv:
                    raise ValueError(f"Dávka {batch_id} neexistuje.")

                produkt_id = zv.get('vyrobok_id')

                if not produkt_id:
                    # fallback podľa názvu z FE
                    pname = (it.get('productName') or '').strip()
                    if pname:
                        cur.execute("SELECT id FROM products WHERE nazov=%s LIMIT 1", (pname,))
                        rowp = cur.fetchone()
                        if not rowp:
                            cur.execute("SELECT id FROM produkty WHERE nazov=%s LIMIT 1", (pname,))
                            rowp = cur.fetchone()
                        if rowp:
                            produkt_id = int(rowp['id'])

                if not produkt_id:
                    raise ValueError("Dávke chýba vyrobok_id a produkt sa nepodarilo nájsť ani podľa názvu.")

                produkt_id = int(produkt_id)

                # 2) vlož príjem (ACC tag do 'dodavatel')
                accept_id = secrets.token_hex(5).upper()
                acc_tag   = f"ACC:{accept_id}|{worker}"
                if note_ui:
                    acc_tag = f"{acc_tag}|{note_ui}"
                acc_tag = acc_tag[:200]

                cur.execute("""
                    INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, cena, dodavatel)
                    VALUES (%s, %s, NOW(6), %s, %s, %s)
                """, (CENTRAL_WAREHOUSE_ID, produkt_id, str(qty), "0", acc_tag))

                # 3) navýš sklad 2
                cur.execute("""
                    SELECT id, COALESCE(mnozstvo, 0) AS mnozstvo
                    FROM sklad_polozky
                    WHERE sklad_id=%s AND produkt_id=%s
                    FOR UPDATE
                """, (CENTRAL_WAREHOUSE_ID, produkt_id))
                row = cur.fetchone()
                if row:
                    new_qty = (Decimal(str(row['mnozstvo'])) + qty).quantize(Decimal("0.001"))
                    cur.execute("UPDATE sklad_polozky SET mnozstvo=%s WHERE id=%s", (str(new_qty), row['id']))
                else:
                    cur.execute("""
                        INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo)
                        VALUES (%s, %s, %s)
                    """, (CENTRAL_WAREHOUSE_ID, produkt_id, str(qty)))

                # 4) stav dávky + doplň real_qty, ak chýbal
                cur.execute("""
                    UPDATE zaznamy_vyroba
                    SET stav=%s,
                        skutocne_vyrobene = CASE
                            WHEN (skutocne_vyrobene IS NULL OR skutocne_vyrobene = 0) THEN %s
                            ELSE skutocne_vyrobene
                        END
                    WHERE id=%s
                """, (NEW_STATUS, str(qty), batch_id))

                accepted.append({"accept_id": accept_id, "batch_id": batch_id})

            except Exception as ex:
                # ulož detail chyby pre danú položku a pokračuj
                errors.append(f"batch {it.get('batchId')}: {ex}")

        conn.commit()

        msg = f"Prevzatie uložené. Položiek: {len(accepted)}" + (f", chyby: {len(errors)}" if errors else "")
        if errors:
            # ukáž prvú chybu, nech to hneď vidíš vo FE
            msg += f" | 1. chyba: {errors[0]}"
        return {"ok": True, "message": msg, "accepted": accepted, "errors": errors}

    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": f"accept_productions failed: {e}"}
    finally:
        try:
            if conn and conn.is_connected():
                conn.close()
        except Exception:
            pass

def return_to_production(payload=None, **kwargs):
    """
    Vráti tovar do výroby (sklad 2 -> sklad 1) na prepracovanie.
    payload: {batchId, qty_kg, reason}
    """
    data = payload if isinstance(payload, dict) else {}
    batch_id = int(data.get("batchId") or 0)
    qty = float(data.get("qty_kg") or 0)
    reason = (data.get("reason") or "").strip()
    if batch_id<=0 or qty<=0:
        return {"error":"Neplatný batch alebo množstvo."}

    zv = db_connector.execute_query("SELECT vyrobok_id FROM zaznamy_vyroba WHERE id=%s", (batch_id,)) or []
    if not zv:
        return {"error":"Dávka neexistuje."}
    produkt_id = zv[0]['vyrobok_id']

    note = json.dumps({"reason":reason or "rework"}, separators=(",",":"))[:250]

    # výdaj z centrálneho
    db_connector.execute_query("""
        INSERT INTO inventory_movements
          (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
        VALUES (NOW(6), %s, %s, %s, 0, %s, 'zaznamy_vyroba', %s, %s)
    """, (2, produkt_id, -qty, 6, batch_id, note))

    # príjem do výroby (sklad 1)
    db_connector.execute_query("""
        INSERT INTO inventory_movements
          (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
        VALUES (NOW(6), %s, %s, %s, 0, %s, 'zaznamy_vyroba', %s, %s)
    """, (1, produkt_id, qty, 6, batch_id, note))

    # označ dávku
    db_connector.execute_query(
        "UPDATE zaznamy_vyroba SET stav='Vrátené na prepracovanie' WHERE id=%s",
        (batch_id,)
    )
    return {"ok":True, "message":"Tovar bol vrátený do výroby na prepracovanie."}
