# -*- coding: utf-8 -*-
"""
production_handler.py — modul Výroba (nová schéma)

Zhrnutie:
- Len nové tabuľky: products, recepty, recepty_polozky, sklad_polozky,
  zaznamy_vyroba, inventory_movements, writeoff_logs, production_categories, product_categories.
- Stavové prechody: "Automaticky naplánované" → "Vo výrobe" → "Prijaté, čaká na expedíciu".
- Evidencia pohybov do inventory_movements:
    movement_type: 1 = príjem, 2 = výdaj na výrobu, 3 = ručný odpis
- Weighted Moving Average (WMA) v update_stock() pre príjem (delta > 0).
- Transakcie, kontrola zásob, čitateľné chyby (žiadne pády requestu).
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple
import logging
import traceback

try:
    import db_connector as db
except Exception as e:
    raise ImportError("Tento modul vyžaduje modul 'db_connector' s get_connection().") from e

# -----------------------------
# Konštanty a mapovania
# -----------------------------

WAREHOUSE_PROD = 1  # ID výrobného skladu

# Typy pohybov v inventory_movements
MOVEMENT_IN           = 1  # príjem (dokončenie výroby)
MOVEMENT_PROD_ISSUE   = 2  # výdaj na výrobu (odpísané suroviny)
MOVEMENT_WRITEOFF     = 3  # ručný odpis

TYPE_MAP = {
    0: 'surovina',
    1: 'surovina',   # raw
    2: 'vyrobok',    # finished
    3: 'krajaný',    # sliced
    4: 'externy',    # externally bought
}

# -----------------------------
# Helpery
# -----------------------------

def _type_key(val: Any) -> str:
    try:
        return TYPE_MAP.get(int(val), 'externy')
    except Exception:
        return 'externy'

def d(x: Any) -> Decimal:
    if x is None: return Decimal('0')
    if isinstance(x, Decimal): return x
    try: return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError): return Decimal('0')

def q2(x: Decimal) -> Decimal:
    return d(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def q3(x: Decimal) -> Decimal:
    return d(x).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

def safe_get_int(x: Any, default: int = 0) -> int:
    try: return int(x)
    except (TypeError, ValueError): return default

def safe_get_float(x: Any, default: float = 0.0) -> float:
    try: return float(x)
    except (TypeError, ValueError): return default

def _fetchone(cur) -> Dict[str, Any]:
    row = cur.fetchone()
    return row if row else {}

def _fetchall(cur) -> List[Dict[str, Any]]:
    rows = cur.fetchall()
    return rows if rows else []

# --------------------------------------------
# Aktualizácia skladu s WMA (weighted average)
# --------------------------------------------

def update_stock(*, product_id: int, sklad_id: int, delta: Decimal, cena: Optional[Decimal],
                 conn=None, allow_negative: bool = False) -> None:
    """
    Zmení stav v sklad_polozky o 'delta'.
    - Pri delta > 0 a zadanom 'cena' prepočíta WMA (priemerna_cena).
    - Pri delta < 0 sa cena nemení (len množstvo).
    - allow_negative=True dovolí ísť do mínusu (vedomé rozhodnutie).
    """
    owns_conn = False
    if conn is None:
        conn = db.get_connection()
        owns_conn = True

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, mnozstvo, priemerna_cena
            FROM sklad_polozky
            WHERE sklad_id=%s AND produkt_id=%s
            FOR UPDATE
        """, (sklad_id, product_id))
        rec = _fetchone(cur)

        old_qty = d(rec.get('mnozstvo', 0)) if rec else Decimal('0')
        old_avg = d(rec.get('priemerna_cena', 0)) if rec else Decimal('0')
        new_qty = old_qty + d(delta)

        if new_qty < 0 and not allow_negative:
            raise ValueError("Nedostatočná zásoba pre odpísanie (sklad by šiel do mínusu).")

        new_avg = old_avg
        if d(delta) > 0 and cena is not None and new_qty > 0:
            new_avg = (old_qty * old_avg + d(delta) * d(cena)) / new_qty

        if rec:
            cur.execute("""
                UPDATE sklad_polozky
                   SET mnozstvo=%s, priemerna_cena=%s
                 WHERE id=%s
            """, (q3(new_qty), q2(new_avg), rec['id']))
        else:
            cur.execute("""
                INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena)
                VALUES (%s,%s,%s,%s)
            """, (sklad_id, product_id, q3(new_qty), q2(cena if cena is not None else old_avg)))

        if owns_conn: conn.commit()
    except Exception:
        if owns_conn: conn.rollback()
        raise
    finally:
        if owns_conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

# -----------------------
# Prehľady pre front-end
# -----------------------

def get_warehouse_state(sklad_id: int = WAREHOUSE_PROD) -> Dict[str, Any]:
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                p.id AS product_id,
                p.nazov AS name,
                p.typ   AS type,
                sp.mnozstvo AS quantity,
                sp.priemerna_cena AS price,
                p.min_zasoba
            FROM sklad_polozky sp
            JOIN products p ON sp.produkt_id = p.id
            WHERE sp.sklad_id = %s
            ORDER BY p.nazov
        """, (sklad_id,))
        items = _fetchall(cur)
        out = {'surovina': [], 'vyrobok': [], 'krajaný': [], 'externy': [], 'all': items}
        for it in items:
            out[_type_key(it.get('type'))].append(it)
        return out
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def get_categorized_recipes() -> Dict[str, Any]:
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                p.id,
                p.nazov AS vyrobok,
                COALESCE(pc.name, 'Nezaradené') AS kategoria
            FROM products p
            JOIN recepty r ON r.vyrobok_id = p.id
            LEFT JOIN production_categories pc ON pc.id = p.production_category_id
            ORDER BY kategoria, vyrobok
        """)
        rows = _fetchall(cur)
        data: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            data.setdefault(r['kategoria'], []).append({"id": r["id"], "name": r["vyrobok"]})
        return {"data": data}
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def get_planned_production_tasks_by_category() -> Dict[str, List[Dict[str, Any]]]:
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                zv.id AS logId,
                p.nazov AS productName,
                zv.planovane_mnozstvo AS plannedQty,
                COALESCE(pc.name, 'Nezaradené') AS category
            FROM zaznamy_vyroba zv
            JOIN products p ON p.id = zv.vyrobok_id
            LEFT JOIN production_categories pc ON pc.id = p.production_category_id
            WHERE zv.stav = 'Automaticky naplánované'
            ORDER BY category, p.nazov
        """)
        rows = _fetchall(cur)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for t in rows:
            planned = safe_get_float(t.get('plannedQty') or 0)
            t['displayQty'] = f"{planned:.2f} kg"
            out.setdefault(t['category'], []).append(t)
        return out
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def get_running_production_tasks_by_category() -> Dict[str, List[Dict[str, Any]]]:
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                zv.id AS logId,
                p.nazov AS productName,
                zv.planovane_mnozstvo AS plannedQty,
                COALESCE(pc.name, 'Nezaradené') AS category
            FROM zaznamy_vyroba zv
            JOIN products p ON p.id = zv.vyrobok_id
            LEFT JOIN production_categories pc ON pc.id = p.production_category_id
            WHERE zv.stav = 'Vo výrobe'
            ORDER BY category, p.nazov
        """)
        rows = _fetchall(cur)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for t in rows:
            planned = safe_get_float(t.get('plannedQty') or 0)
            t['displayQty'] = f"{planned:.2f} kg"
            out.setdefault(t['category'], []).append(t)
        return out
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def get_all_warehouse_items(sklad_id: int = WAREHOUSE_PROD) -> List[Dict[str, Any]]:
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT p.id, p.nazov AS name, p.typ
            FROM sklad_polozky sp
            JOIN products p ON p.id = sp.produkt_id
            WHERE sp.sklad_id=%s
            ORDER BY p.nazov
        """, (sklad_id,))
        rows = _fetchall(cur)
        return [{"id": r["id"], "name": r["name"]} for r in rows]
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

# --------------------------------
# Výroba — hlavné akčné funkcie
# --------------------------------
def start_production(data: Dict[str, Any], workerName: Optional[str] = None) -> Dict[str, Any]:
    """
    Štart výroby s podporou:
      - úprav množstiev pôvodných surovín (use_original_qty_kg),
      - jednorazových náhrad (to_id, to_qty_kg),
      - povolenia odpisu do mínusu (forceStart=True).

    Očakávaný payload:
      {
        vyrobok_id|productName, plannedWeight, productionDate?,
        overrides: [ {from_id, use_original_qty_kg, to_id?, to_qty_kg?}, ... ],
        override_author?: str,
        forceStart?: bool
      }
    """
    conn = None  # dôležité: nikdy nevolať rollback/close na None
    try:
        # ---- Vstupy
        vyrobok_id      = safe_get_int(data.get('vyrobok_id') or 0)
        productName     = (data.get('productName') or '').strip()
        planned_weight  = d(data.get('plannedWeight') or 0)
        production_date = (data.get('productionDate') or date.today().isoformat())
        existing_id     = safe_get_int(data.get('existingLogId') or 0)
        workerName      = (workerName or data.get('workerName') or '').strip()
        force_start     = bool(data.get('forceStart') or False)

        overrides_in     = data.get('overrides') or []
        override_author  = (data.get('override_author') or '').strip()

        # ---- Vyhľadaj produkt podľa názvu, ak neprišlo id
        if not vyrobok_id and productName:
            tmp = db.get_connection()
            try:
                cur = tmp.cursor(dictionary=True)
                cur.execute("SELECT id FROM products WHERE nazov=%s", (productName,))
                pr = _fetchone(cur)
            finally:
                if getattr(tmp, "is_connected", lambda: False)():
                    tmp.close()
            if not pr:
                return {"error": f'Produkt "{productName}" nebol nájdený.'}
            vyrobok_id = pr['id']

        if not vyrobok_id or planned_weight <= 0:
            return {"error": "Chýbajú údaje (výrobok alebo množstvo)."}

        # ---- Normalizácia overrides -> dict {from_id: {use_orig, to_id, to_qty}}
        override_map: Dict[int, Dict[str, Any]] = {}
        for it in (overrides_in or []):
            f = safe_get_int((it or {}).get('from_id') or 0)
            if f <= 0:
                continue
            use_orig = d((it or {}).get('use_original_qty_kg') or 0)
            to_id    = safe_get_int((it or {}).get('to_id') or 0) or None
            to_qty   = d((it or {}).get('to_qty_kg') or 0)
            if use_orig < 0: use_orig = Decimal('0')
            if to_qty   < 0: to_qty   = Decimal('0')
            override_map[f] = {"use_orig": use_orig, "to_id": to_id, "to_qty": to_qty}

        if override_map and not override_author:
            return {"error": "Pri úprave množstiev/náhrad je povinné meno pracovníka (override_author)."}

        # ---- DB
        conn = db.get_connection()
        cur  = conn.cursor(dictionary=True)

        # 1) Recept (množstvá sú na 100 kg výrobku)
        cur.execute("""
            SELECT rp.surovina_id, rp.mnozstvo_na_davku AS per100, p.nazov
            FROM recepty_polozky rp
            JOIN recepty r ON r.id=rp.recept_id
            JOIN products p ON p.id = rp.surovina_id
            WHERE r.vyrobok_id=%s
        """, (vyrobok_id,))
        recipe = _fetchall(cur)
        if not recipe:
            cur.close(); conn.close(); conn = None
            return {"error": "Výrobok nemá definovaný recept."}

        mult = (planned_weight / Decimal('100'))

        # 2) Potreby po úpravách + kontrola zásob + nacenenie
        needs: List[Tuple[int, Decimal, Decimal]] = []  # (produkt_id, qty, unit_cost)
        missing: List[Dict[str, Any]] = []
        total_cost = Decimal('0')

        def _add_need(prod_id: int, qty: Decimal):
            nonlocal total_cost, missing, needs
            if qty <= 0:
                return
            cur.execute("""
                SELECT COALESCE(SUM(sp.mnozstvo),0) AS qty,
                       COALESCE(AVG(sp.priemerna_cena),0) AS price
                FROM sklad_polozky sp
                WHERE sp.sklad_id=%s AND sp.produkt_id=%s
            """, (WAREHOUSE_PROD, prod_id))
            row = _fetchone(cur)
            instock   = d(row.get('qty') or 0)
            unit_cost = d(row.get('price') or 0)

            if instock + Decimal('0.0000001') < qty:
                cur.execute("SELECT nazov FROM products WHERE id=%s", (prod_id,))
                nm = _fetchone(cur).get('nazov', f'ID {prod_id}')
                missing.append({
                    "product_id": prod_id,
                    "name": nm,
                    "required_kg": float(q3(qty)),
                    "in_stock_kg": float(q3(instock)),
                    "shortage_kg": float(q3(qty - instock))
                })
            total_cost += unit_cost * qty
            needs.append((prod_id, qty, unit_cost))

        for ing in recipe:
            base_sid      = safe_get_int(ing['surovina_id'])
            base_required = d(ing['per100']) * mult

            adj = override_map.get(base_sid)
            if adj:
                _add_need(base_sid, adj['use_orig'])
                if adj['to_id'] and adj['to_qty'] > 0:
                    _add_need(adj['to_id'], adj['to_qty'])
            else:
                _add_need(base_sid, base_required)

        # 3) Chýbajúce suroviny → žiadosť o potvrdenie
        if missing and not force_start:
            cur.close(); conn.close(); conn = None
            return {
                "warning": "Na sklade chýbajú suroviny pre plánovanú dávku. Spustením pôjde sklad do mínusu.",
                "requires_confirmation": True,
                "missing": missing,
                "plannedWeight": float(q3(planned_weight)),
                "product_id": vyrobok_id,
                "productName": productName
            }

        # 4) Založ/aktualizuj dávku
        if existing_id:
            cur.execute("""
                UPDATE zaznamy_vyroba
                   SET datum_vyroby=%s,
                       planovane_mnozstvo=%s,
                       stav='Vo výrobe',
                       celkova_cena_surovin=%s
                 WHERE id=%s
            """, (production_date, q3(planned_weight), q2(total_cost), existing_id))
            batch_id = existing_id
        else:
            cur.execute("""
                INSERT INTO zaznamy_vyroba
                  (vyrobok_id, datum_vyroby, planovane_mnozstvo, skutocne_vyrobene, stav, celkova_cena_surovin)
                VALUES (%s,%s,%s,NULL,'Vo výrobe',%s)
            """, (vyrobok_id, production_date, q3(planned_weight), q2(total_cost)))
            batch_id = cur.lastrowid

        # 5) Odpis surovín + trace
        allow_negative = bool(missing) or bool(force_start)

        override_note = ""
        if override_map:
            pairs = []
            for f, spec in override_map.items():
                cur.execute("SELECT nazov FROM products WHERE id=%s", (f,))
                fn = _fetchone(cur).get('nazov', f'ID {f}')
                if spec.get('to_id'):
                    cur.execute("SELECT nazov FROM products WHERE id=%s", (spec['to_id'],))
                    tn = _fetchone(cur).get('nazov', f'ID {spec["to_id"]}')
                    pairs.append(f"{fn}: orig {q3(spec['use_orig'])} kg; náhrada {tn} {q3(spec['to_qty'])} kg")
                else:
                    pairs.append(f"{fn}: orig {q3(spec['use_orig'])} kg")
            override_note = f" | Úpravy: {', '.join(pairs)}; Autor: {override_author or workerName}"

        for prod_id, qty_dec, unit_cost in needs:
            update_stock(
                product_id=prod_id,
                sklad_id=WAREHOUSE_PROD,
                delta=-qty_dec,
                cena=None,
                conn=conn,
                allow_negative=allow_negative
            )
            cur.execute("""
                INSERT INTO inventory_movements
                  (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
                VALUES (NOW(6), %s, %s, %s, %s, %s, 'zaznamy_vyroba', %s, %s)
            """, (WAREHOUSE_PROD, prod_id, q3(-qty_dec), q2(unit_cost), MOVEMENT_PROD_ISSUE, batch_id,
                  ((workerName or '') + override_note)[:255]))

        conn.commit()
        cur.close(); conn.close(); conn = None

        msg = "Výroba spustená, suroviny odpísané."
        if allow_negative:
            msg += " Upozornenie: niektoré položky šli do mínusu."
        return {"message": msg, "batch_id": batch_id, "went_negative": allow_negative}

    except Exception as ex:
        logging.error("start_production crashed:\n%s", traceback.format_exc())
        try:
            if conn and getattr(conn, "is_connected", lambda: False)():
                conn.rollback()
                conn.close()
        except Exception:
            pass
        return {"error": f"Start výroby zlyhal: {ex}"}

def get_running_production_detail(data: Dict[str, Any]) -> Dict[str, Any]:
    batch_id = safe_get_int(data.get('batch_id') or data.get('logId') or 0)
    if batch_id <= 0:
        return {"error": "Chýba batch_id."}

    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT zv.vyrobok_id, p.nazov AS product_name,
                   zv.planovane_mnozstvo
            FROM zaznamy_vyroba zv
            JOIN products p ON p.id = zv.vyrobok_id
            WHERE zv.id=%s
        """, (batch_id,))
        base = _fetchone(cur)
        if not base:
            return {"error": "Dávka neexistuje."}

        planned = d(base.get('planovane_mnozstvo') or 0)
        mult = planned / Decimal('100')

        cur.execute("""
            SELECT rp.surovina_id, pr.nazov, rp.mnozstvo_na_davku AS per100
            FROM recepty_polozky rp
            JOIN recepty r ON r.id=rp.recept_id
            JOIN products pr ON pr.id = rp.surovina_id
            WHERE r.vyrobok_id=%s
        """, (base['vyrobok_id'],))
        std_rows = _fetchall(cur)
        standard = [{
            "product_id": r['surovina_id'],
            "name": r['nazov'],
            "required_kg": float(q3(d(r['per100']) * mult))
        } for r in std_rows]

        cur.execute("""
            SELECT im.produkt_id, p.nazov, SUM(-im.qty_change) AS used_kg
            FROM inventory_movements im
            JOIN products p ON p.id = im.produkt_id
            WHERE im.ref_table='zaznamy_vyroba' AND im.ref_id=%s AND im.movement_type IN (%s)
            GROUP BY im.produkt_id, p.nazov
            ORDER BY p.nazov
        """, (batch_id, MOVEMENT_PROD_ISSUE))
        used_rows = _fetchall(cur)
        used = [{
            "product_id": r['produkt_id'],
            "name": r['nazov'],
            "used_kg": float(q3(d(r['used_kg'] or 0)))
        } for r in used_rows]

        cur.execute("""
            SELECT note FROM inventory_movements
            WHERE ref_table='zaznamy_vyroba' AND ref_id=%s AND note IS NOT NULL AND note <> ''
            ORDER BY id DESC LIMIT 1
        """, (batch_id,))
        note_row = _fetchone(cur)
        override_note = note_row.get('note', '') if note_row else ''

        return {
            "batch_id": batch_id,
            "product": base.get('product_name'),
            "planned_kg": float(q3(planned)),
            "standard_ingredients": standard,
            "used_ingredients": used,
            "override_note": override_note
        }
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def finish_production(data: Dict[str, Any], workerName: Optional[str] = None) -> Dict[str, Any]:
    batch_id = safe_get_int(data.get('batchId') or 0)
    real_output = d(data.get('realOutput') or 0)
    workerName = (workerName or data.get('workerName') or '').strip()
    if batch_id <= 0 or real_output <= 0:
        return {"error": "Chýbajú údaje (batchId alebo realOutput)."}

    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT vyrobok_id, planovane_mnozstvo, celkova_cena_surovin
            FROM zaznamy_vyroba
            WHERE id=%s
            FOR UPDATE
        """, (batch_id,))
        zv = _fetchone(cur)
        if not zv:
            return {"error": f"Dávka ID {batch_id} neexistuje."}

        product_id = safe_get_int(zv['vyrobok_id'])
        total_cost = d(zv.get('celkova_cena_surovin') or 0)

        if total_cost <= 0:
            cur.execute("""
                SELECT SUM(-im.qty_change * im.unit_cost) AS cost
                FROM inventory_movements im
                WHERE im.ref_table='zaznamy_vyroba' AND im.ref_id=%s AND im.movement_type=%s
            """, (batch_id, MOVEMENT_PROD_ISSUE))
            total_cost = d(_fetchone(cur).get('cost') or 0)

        unit_cost = total_cost / real_output if real_output > 0 else Decimal('0')

        update_stock(product_id=product_id, sklad_id=WAREHOUSE_PROD, delta=real_output, cena=unit_cost, conn=conn)
        cur.execute("""
            INSERT INTO inventory_movements
              (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
            VALUES (NOW(6), %s, %s, %s, %s, %s, 'zaznamy_vyroba', %s, %s)
        """, (WAREHOUSE_PROD, product_id, q3(real_output), q2(unit_cost), MOVEMENT_IN, batch_id, workerName))

        cur.execute("""
            UPDATE zaznamy_vyroba
               SET skutocne_vyrobene=%s,
                   stav='Prijaté, čaká na expedíciu'
             WHERE id=%s
        """, (q3(real_output), batch_id))

        conn.commit()
        return {"message": "Výroba dokončená, výrobok prijatý na sklad.", "batch_id": batch_id}
    except Exception as ex:
        conn.rollback()
        return {"error": f"Dokončenie výroby zlyhalo: {ex}"}
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def manual_warehouse_write_off(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ručný odpis zo skladu (writeoff_logs + inventory_movements + update_stock).
    data:
      product_id?: int      # preferované
      itemName?: str        # fallback podľa názvu
      quantity: float (kg)
      note?: str
      workerName: str
    """
    product_id = safe_get_int(data.get('product_id') or 0)
    itemName   = (data.get('itemName') or '').strip()
    qty        = d(data.get('quantity') or 0)
    note       = (data.get('note') or '').strip()
    worker     = (data.get('workerName') or '').strip()

    if qty <= 0 or not worker:
        return {"error": "Pracovník a množstvo > 0 sú povinné."}

    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        # 1) Identifikuj produkt podľa ID (preferované) alebo názvu (fallback).
        pid = 0
        display_name = itemName
        if product_id > 0:
            cur.execute("SELECT id, nazov FROM products WHERE id=%s", (product_id,))
            row = _fetchone(cur)
            if not row:
                return {"error": f"Produkt ID {product_id} neexistuje."}
            pid = row['id']
            display_name = row['nazov']
        else:
            if not itemName:
                return {"error": "Chýba produkt (product_id alebo itemName)."}
            cur.execute("SELECT id, nazov FROM products WHERE nazov=%s", (itemName,))
            row = _fetchone(cur)
            if not row:
                return {"error": f"Položka '{itemName}' neexistuje."}
            pid = row['id']
            display_name = row['nazov']

        # 2) Zisti aktuálnu priemernú cenu pre trace.
        cur.execute("""
            SELECT priemerna_cena FROM sklad_polozky
            WHERE sklad_id=%s AND produkt_id=%s
        """, (WAREHOUSE_PROD, pid))
        unit_cost = d(_fetchone(cur).get('priemerna_cena') or 0)

        # 3) Odpis + logy
        update_stock(product_id=pid, sklad_id=WAREHOUSE_PROD, delta=-qty, cena=None, conn=conn)
        cur.execute("""
            INSERT INTO writeoff_logs
                (ts, sklad_id, produkt_id, qty, reason_code, reason_text, actor_user_id, signature_text)
            VALUES (NOW(6), %s, %s, %s, %s, %s, %s, %s)
        """, (WAREHOUSE_PROD, pid, q3(qty), 0, note, 0, worker))
        writeoff_id = cur.lastrowid

        cur.execute("""
            INSERT INTO inventory_movements
                (ts, sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
            VALUES (NOW(6), %s, %s, %s, %s, %s, 'writeoff_logs', %s, %s)
        """, (WAREHOUSE_PROD, pid, -q3(qty), q2(unit_cost), MOVEMENT_WRITEOFF, writeoff_id, note))

        conn.commit()
        return {"ok": True, "message": f"Odpočítaných {q3(qty)} kg z '{display_name}'.", "product_id": pid, "name": display_name}
    except Exception as ex:
        if conn: conn.rollback()
        return {"error": f"Ručný odpis zlyhal: {ex}"}
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

# ----------------------------
# Inventúra (výrobný sklad)
# ----------------------------

INVENTORY_GROUPS = {
    "Mäso": {"names": ["Mäso", "Maso"]},
    "Obaly": {"names": ["Obaly"]},
    "Koreniny": {"names": ["Koreniny", "Koreni"]},
    "Pomocný materiál": {"names": ["Pomocný materiál", "Pomocny material", "Pomocny", "Pomocný"]},
}

def get_production_inventory_groups(data: Dict[str, Any] = None) -> Dict[str, Any]:
    only_group = ((data or {}).get('group') or '').strip()
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT p.id, p.nazov, COALESCE(pc.name,'Ostatné') AS cat, COALESCE(sp.mnozstvo,0) AS system_qty
            FROM sklad_polozky sp
            JOIN products p ON p.id = sp.produkt_id
            LEFT JOIN product_categories pc ON pc.id = p.kategoria_id
            WHERE sp.sklad_id=%s
            ORDER BY pc.name, p.nazov
        """, (WAREHOUSE_PROD,))
        rows = _fetchall(cur)

        groups = {k: [] for k in INVENTORY_GROUPS.keys()}
        groups["Ostatné"] = []
        for r in rows:
            cat_name = (r.get('cat') or '').strip()
            placed = False
            for gname, meta in INVENTORY_GROUPS.items():
                if cat_name in meta['names']:
                    groups[gname].append({"product_id": r['id'], "name": r['nazov'], "systemQty": float(q3(r['system_qty']))})
                    placed = True
                    break
            if not placed:
                groups["Ostatné"].append({"product_id": r['id'], "name": r['nazov'], "systemQty": float(q3(r['system_qty']))})

        if only_group:
            return {"groups": {only_group: groups.get(only_group, [])}}
        return {"groups": groups}
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

def submit_inventory_category(data: Dict[str, Any]) -> Dict[str, Any]:
    group_name = (data.get('group_name') or '').strip() or 'Nezaradené'
    worker_name = (data.get('worker_name') or data.get('workerName') or '').strip()
    items = data.get('items') or []
    if not items:
        return {"error": "Chýbajú položky na inventúru."}

    payload = {
        "warehouse_id": WAREHOUSE_PROD,
        "worker_name": worker_name,
        "inventory_data": [{"name": it.get("name"), "systemQty": 0, "realQty": it.get("realQty"), "type": group_name} for it in items]
    }
    return update_inventory(payload)

def update_inventory(data: Dict[str, Any]) -> Dict[str, Any]:
    inventory_data = data.get('inventory_data') or data.get('items') or []
    worker_name = (data.get('worker_name') or data.get('workerName') or '').strip()
    warehouse_id = safe_get_int(data.get('warehouse_id') or data.get('warehouseId') or WAREHOUSE_PROD)

    if not inventory_data:
        return {"error": "Neboli zadané žiadne položky inventúry."}

    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        product_names = [it.get('name') for it in inventory_data if it.get('name')]
        if not product_names:
            return {"error": "Chýbajú názvy položiek."}
        placeholders = ",".join(["%s"] * len(product_names))
        cur.execute(f"SELECT id, nazov FROM products WHERE nazov IN ({placeholders})", tuple(product_names))
        name_to_id = {r['nazov']: r['id'] for r in _fetchall(cur)}

        updates = inserts = differences = 0

        for item in inventory_data:
            name = item.get('name')
            if not name or name not in name_to_id:
                continue
            product_id = name_to_id[name]

            system_qty = d(item.get('systemQty') or 0)
            real_qty = d(item.get('realQty') or 0)
            if (real_qty - system_qty).copy_abs() <= Decimal('0.001'):
                continue

            cur.execute("""
                SELECT id, mnozstvo, priemerna_cena
                FROM sklad_polozky
                WHERE sklad_id=%s AND produkt_id=%s
                FOR UPDATE
            """, (warehouse_id, product_id))
            rec = _fetchone(cur)
            unit_price = d(rec.get('priemerna_cena') or 0)

            if rec:
                cur.execute("UPDATE sklad_polozky SET mnozstvo=%s WHERE id=%s", (q3(real_qty), rec['id']))
                updates += 1
            else:
                cur.execute("""
                    INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena)
                    VALUES (%s,%s,%s,%s)
                """, (warehouse_id, product_id, q3(real_qty), q2(unit_price)))
                inserts += 1

            diff = real_qty - system_qty
            diff_value = q2(unit_price * diff)
            differences += 1
            cur.execute("""
                INSERT INTO inventurne_rozdiely
                  (datum, nazov_suroviny, typ_suroviny, systemovy_stav_kg, realny_stav_kg, rozdiel_kg, hodnota_rozdielu_eur, pracovnik)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (datetime.now(), name, item.get('type') or '', q3(system_qty), q3(real_qty), q3(diff), diff_value, worker_name))

        conn.commit()
        return {"message": f"Inventúra hotová. Aktualizované: {updates}, vložené: {inserts}, rozdiely: {differences}."}
    except Exception as ex:
        conn.rollback()
        return {"error": f"Inventúra zlyhala: {ex}"}
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()

# ----------------------------
# (Voliteľné) zoznam skladov pre výber – ak by si chcel v budúcnosti
# ----------------------------

def list_inventory_warehouses(data: Dict[str, Any] = None) -> Dict[str, Any]:
    conn = db.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        warehouses = []
        try:
            cur.execute("SELECT id, nazov FROM warehouses ORDER BY nazov")
            rows = _fetchall(cur)
            if rows:
                warehouses = [{"id": r["id"], "name": r["nazov"]} for r in rows]
        except Exception:
            pass

        if not warehouses:
            try:
                cur.execute("SELECT id, nazov FROM sklady ORDER BY nazov")
                rows = _fetchall(cur)
                warehouses = [{"id": r["id"], "name": r["nazov"]} for r in rows]
            except Exception:
                warehouses = []

        return {"warehouses": warehouses}
    finally:
        if getattr(conn, "is_connected", lambda: False)():
            conn.close()
