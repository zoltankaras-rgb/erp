# server/akcie.py
# Blueprint "Akcie" – reťazce a promo akcie + odporúčanie výroby
# - perzistentné uloženie do JSON (funguje hneď bez DB)
# - dashboard upozornenia 5 dní vopred
# - odporúčanie výroby 3 pracovné dni pred akciou (výpočet materiálov)
#
# Registrácia v app.py:
# from server.akcie import akcie_bp
# app.register_blueprint(akcie_bp, url_prefix="/api/kancelaria/akcie")

import os, json, datetime as dt
from flask import Blueprint, request, jsonify
import db_connector

akcie_bp = Blueprint("akcie", __name__)

# --- cesty k dátam (JSON) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../Projekt/server
PROJECT_ROOT = os.path.normpath(os.path.join(BASE_DIR, ".."))  # .../Projekt
DATA_DIR = os.path.join(PROJECT_ROOT, "data")                  # .../Projekt/data

CHAINS_PATH = os.path.join(DATA_DIR, "retazce.json")
PROMOS_PATH = os.path.join(DATA_DIR, "akcie.json")


def _ensure_data_dir():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _load(path, default):
    _ensure_data_dir()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _next_id(items):
    return (max([x["id"] for x in items], default=0) + 1) if items else 1


def _parse_date(s):
    # očakávame ISO "YYYY-MM-DD"
    return dt.date.fromisoformat(s)


def _date_str(d):
    return d.isoformat()


def _is_weekend(d):
    return d.weekday() >= 5  # 5=So, 6=Ne


def working_days_before(start_date: dt.date, days: int) -> dt.date:
    """Vracia dátum o N pracovných dní skôr (víkendy preskakuje)."""
    d = start_date
    left = days
    while left > 0:
        d = d - dt.timedelta(days=1)
        if not _is_weekend(d):
            left -= 1
    return d


def count_days_inclusive(a: dt.date, b: dt.date) -> int:
    return (b - a).days + 1


# ==========================
# Hooky na systém (recept, sklad, náklady) – uprav podľa DB
# ==========================

def get_product_meta(product_id: int):
    """
    Vytiahne názov a výrobné meta z DB.
    Priorita: products -> katalog_produktov -> produkty (fallback).
    Vracia: {"unit": "kg"|"ks", "piece_weight_g": int, "name": str, "ean": str, "is_produced": bool, "category": str}
    """
    try:
        # 1) products (hlavná tabuľka)
        row = db_connector.execute_query(
            """
            SELECT p.id, p.nazov, p.ean, p.je_vyroba, p.production_unit, p.piece_weight_g
            FROM products p
            WHERE p.id = %s
            LIMIT 1
            """,
            (product_id,), fetch='one'
        )

        # 2) centr. katalóg
        if not row:
            row = db_connector.execute_query(
                """
                SELECT id, nazov, ean, je_vyroba, NULL AS production_unit, NULL AS piece_weight_g
                FROM katalog_produktov
                WHERE id = %s
                LIMIT 1
                """,
                (product_id,), fetch='one'
            )

        # 3) úplný fallback (legacy tabuľka)
        if not row:
            row = db_connector.execute_query(
                """
                SELECT id, nazov, ean, je_vyroba, NULL AS production_unit, NULL AS piece_weight_g
                FROM produkty
                WHERE id = %s
                LIMIT 1
                """,
                (product_id,), fetch='one'
            )

        if row:
            pu = row.get('production_unit')
            unit = 'ks' if (pu == 1 or str(pu).lower() == 'ks') else 'kg'
            return {
                "unit": unit,
                "piece_weight_g": int(row.get('piece_weight_g') or 0),
                "name": row.get('nazov') or f"Produkt #{product_id}",
                "ean": row.get('ean') or "",
                "is_produced": bool(row.get('je_vyroba')),
                "category": ""
            }
    except Exception:
        pass  # nech to nespadne – fallback nižšie

    # Fallback mock – keby DB padla, UI beží
    return {
        "unit": "kg",
        "piece_weight_g": 0,
        "name": f"Produkt #{product_id}",
        "ean": "",
        "is_produced": True,
        "category": ""
    }


def get_recipe_items(product_id: int):
    """
    Vráti zoznam položiek receptu: [{"material_id": int, "nazov": str, "qty_per_100kg": float}]
    TODO: dopoj na tvoje receptové tabuľky (aktuálne prázdny zoznam).
    """
    return []


def get_material_stock(material_id: int):
    """
    Vráti stav na sklade v kg (float).
    TODO: napoj na sklad. Default 0.
    """
    return 0.0


def get_material_avg_cost(material_id: int):
    """
    Vráti priemernú nákupnú cenu materiálu €/kg.
    TODO: napoj na náklady. Default None (neznáme).
    """
    return None


def estimate_daily_sales(product_id: int, chain_id: int, unit: str):
    """
    Hrubý odhad denného predaja počas akcie.
    TODO: napoj na historické predaje. Default: 50 ks alebo 50 kg denne.
    """
    return 50.0


def chain_multiplier(chain_id: int):
    """
    Umožní zvýhodniť/zoslabiť predaj podľa reťazca (napr. COOP 1.2x).
    TODO: ak chceš, pridaj per-reťazec multiplikátor do retazce.json.
    """
    chains = _load(CHAINS_PATH, {"chains": []}).get("chains", [])
    ch = next((c for c in chains if c["id"] == chain_id), None)
    if not ch:
        return 1.0
    return float(ch.get("multiplier", 1.0))


def profit_estimate(product_id: int, qty_units: float, price_net: float, unit: str):
    """
    Odhad zisku: Tržba – Náklady.
    - pre "kg": cena je €/kg → revenue = qty_kg * price_net
    - pre "ks": cena je €/ks → revenue = qty_ks * price_net
    Náklady: ak je recept (is_produced=True), spočítame z materiálov (avg cost * množstvá).
             inak None (čerstvé mäso bez receptu -> skús získať priemernú cenu produktu, ak máš).
    """
    meta = get_product_meta(product_id)
    recipe = get_recipe_items(product_id) if meta.get("is_produced") else []
    revenue = qty_units * price_net

    if not recipe:  # čerstvé alebo recept nie je zadaný
        # TODO: ak máš priemernú nákupnú cenu produktu (€/kg alebo €/ks), použi ju:
        avg_cost_per_u = None  # napr. get_product_avg_cost(product_id)
        if avg_cost_per_u is None:
            return {"revenue": revenue, "cost": None, "profit": None, "note": "Chýba priemerná cena produktu."}
        cost = qty_units * avg_cost_per_u
        return {"revenue": revenue, "cost": cost, "profit": revenue - cost, "note": ""}

    # materiálové náklady z receptu
    if unit == "ks":
        kg_final = qty_units * (meta.get("piece_weight_g", 0) or 0) / 1000.0
    else:
        kg_final = qty_units

    total_cost = 0.0
    missing_costs = []
    for it in recipe:
        need_kg = (float(it.get("qty_per_100kg", 0)) / 100.0) * kg_final
        c = get_material_avg_cost(int(it["material_id"]))
        if c is None:
            missing_costs.append(it.get("nazov", f"MAT#{it['material_id']}"))
            continue
        total_cost += need_kg * float(c)

    if missing_costs:
        return {"revenue": revenue, "cost": None, "profit": None,
                "note": f"Chýba priemerná cena: {', '.join(missing_costs)}"}
    return {"revenue": revenue, "cost": total_cost, "profit": revenue - total_cost, "note": ""}


# ==========================
# API – Reťazce
# ==========================

@akcie_bp.route("/chains/list", methods=["POST"])
def chains_list():
    data = _load(CHAINS_PATH, {"chains": []})
    return jsonify({"chains": data.get("chains", [])})


@akcie_bp.route("/chains/add", methods=["POST"])
def chains_add():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    multiplier = float(payload.get("multiplier") or 1.0)
    if not name:
        return jsonify({"ok": False, "error": "Zadaj názov reťazca."}), 400
    data = _load(CHAINS_PATH, {"chains": []})
    chains = data.get("chains", [])
    new = {
        "id": _next_id(chains),
        "name": name,
        "multiplier": multiplier,
        "created_at": dt.datetime.utcnow().isoformat()
    }
    chains.append(new)
    _save(CHAINS_PATH, {"chains": chains})
    return jsonify({"ok": True, "chain": new})


# ==========================
# API – Akcie
# ==========================

@akcie_bp.route("/list", methods=["POST"])
def promos_list():
    payload = request.get_json(silent=True) or {}
    upcoming_only = bool(payload.get("upcoming_only"))
    today = dt.date.today()
    promos = _load(PROMOS_PATH, {"promos": []}).get("promos", [])
    if upcoming_only:
        promos = [p for p in promos if _parse_date(p["date_to"]) >= today]
    return jsonify({"items": promos})


@akcie_bp.route("/add", methods=["POST"])
def promos_add():
    p = request.get_json(silent=True) or {}
    # očakávané polia: chain_id, product_id, price_net, date_from, date_to, note
    try:
        chain_id = int(p.get("chain_id"))
        product_id = int(p.get("product_id"))
        price_net = float(p.get("price_net"))
        dfrom = _parse_date(p.get("date_from"))
        dto   = _parse_date(p.get("date_to"))
    except Exception:
        return jsonify({"ok": False, "error": "Neplatné údaje akcie."}), 400

    note = (p.get("note") or "").strip()
    promos = _load(PROMOS_PATH, {"promos": []}).get("promos", [])
    new = {
        "id": _next_id(promos),
        "chain_id": chain_id,
        "product_id": product_id,
        "price_net": price_net,
        "date_from": _date_str(dfrom),
        "date_to": _date_str(dto),
        "note": note,
        "created_at": dt.datetime.utcnow().isoformat()
    }
    promos.append(new)
    _save(PROMOS_PATH, {"promos": promos})
    return jsonify({"ok": True, "promo": new})


# ==========================
# API – Dashboard upozornenia (5 dní vopred)
# ==========================

@akcie_bp.route("/dashboard", methods=["POST"])
def promos_dashboard():
    today = dt.date.today()
    horizon = today + dt.timedelta(days=5)
    promos = _load(PROMOS_PATH, {"promos": []}).get("promos", [])
    chains = {c["id"]: c for c in _load(CHAINS_PATH, {"chains": []}).get("chains", [])}
    out = []
    for p in promos:
        df = _parse_date(p["date_from"])
        dt_to = _parse_date(p["date_to"])
        # zobraz: ak začne do 5 dní, alebo už prebieha
        if (today <= df <= horizon) or (df <= today <= dt_to):
            meta = get_product_meta(int(p["product_id"]))
            chain = chains.get(p["chain_id"], {"name": "?"})
            msg = (
                f"Pozor: {df.strftime('%d.%m.%Y')}–{dt_to.strftime('%d.%m.%Y')} "
                f"prebieha akcia v {chain['name']} na {meta.get('name','produkt')} "
                f"za {p['price_net']:.2f} € bez DPH. Treba sa pripraviť."
            )
            out.append({
                "promotion_id": p["id"],
                "message": msg,
                "chain": chain["name"],
                "product": meta.get("name","produkt"),
                "from": p["date_from"],
                "to": p["date_to"],
                "price_net": p["price_net"]
            })
    return jsonify({"items": out})


# ==========================
# API – Odporúčanie výroby (3 pracovné dni pred)
# ==========================

@akcie_bp.route("/recommend", methods=["POST"])
def promo_recommend():
    payload = request.get_json(silent=True) or {}
    promo_id = int(payload.get("promotion_id", 0))
    promos = _load(PROMOS_PATH, {"promos": []}).get("promos", [])
    p = next((x for x in promos if x["id"] == promo_id), None)
    if not p:
        return jsonify({"ok": False, "error": "Akcia neexistuje."}), 404

    df = _parse_date(p["date_from"])
    dt_to = _parse_date(p["date_to"])
    chain_id = int(p["chain_id"])
    product_id = int(p["product_id"])
    price_net = float(p["price_net"])
    meta = get_product_meta(product_id)

    # odporúčaný začiatok výroby
    start_prod = working_days_before(df, 3)

    # odhad množstva (jednotka = kg alebo ks podľa produktu)
    base_daily = estimate_daily_sales(product_id, chain_id, meta.get("unit", "kg"))
    mult = chain_multiplier(chain_id)
    days = max(1, count_days_inclusive(df, dt_to))
    qty_units = base_daily * mult * days

    # materiály podľa receptu
    recipe = get_recipe_items(product_id)
    mats = []

    # finálne kg (ak ks → podľa hmotnosti kusu)
    if meta.get("unit") == "ks":
        final_kg = qty_units * (meta.get("piece_weight_g", 0)/1000.0)
    else:
        final_kg = qty_units

    for it in recipe:
        need_kg = (float(it.get("qty_per_100kg", 0))/100.0) * final_kg
        stock_kg = float(get_material_stock(int(it["material_id"])) or 0.0)
        buy_kg = max(0.0, need_kg - stock_kg)
        mats.append({
            "material_id": int(it["material_id"]),
            "nazov": it.get("nazov", f"MAT#{it['material_id']}"),
            "need_kg": round(need_kg, 3),
            "stock_kg": round(stock_kg, 3),
            "buy_kg": round(buy_kg, 3)
        })

    # zisk
    pe = profit_estimate(product_id, qty_units, price_net, meta.get("unit","kg"))

    return jsonify({
        "ok": True,
        "promotion": p,
        "product": {
            "id": product_id,
            "name": meta.get("name","produkt"),
            "unit": meta.get("unit","kg"),
            "piece_weight_g": meta.get("piece_weight_g", 0)
        },
        "recommendation": {
            "production_start": _date_str(start_prod),
            "qty_units": round(qty_units, 2),
            "qty_units_label": "kg" if meta.get("unit") == "kg" else "ks",
            "final_kg": round(final_kg, 3)
        },
        "materials": mats,
        "profit_estimate": pe
    })
# ==========================
# API – Vytvoriť plán výroby z akcie
# ==========================

@akcie_bp.route("/create_task", methods=["POST"])
def promo_create_task():
    payload = request.get_json(silent=True) or {}
    promo_id = int(payload.get("promotion_id") or 0)
    produce_date = (payload.get("produce_date") or "").strip()  # "YYYY-MM-DD"
    qty_units = float(payload.get("qty_units") or 0)

    if promo_id <= 0 or not produce_date or qty_units <= 0:
        return jsonify({"ok": False, "error": "Chýba promotion_id / dátum / množstvo > 0"}), 400

    # nájdi promo
    promos = _load(PROMOS_PATH, {"promos": []}).get("promos", [])
    promo = next((x for x in promos if x["id"] == promo_id), None)
    if not promo:
        return jsonify({"ok": False, "error": "Akcia neexistuje."}), 404

    product_id = int(promo["product_id"])
    meta = get_product_meta(product_id)

    # prepočty: uložíme plán v KG (výroba pracuje v kg)
    if meta.get("unit") == "ks":
        final_kg = qty_units * (meta.get("piece_weight_g", 0) or 0) / 1000.0
    else:
        final_kg = qty_units

    # datum_vyroby → spravíme datetime (napr. 06:00) kvôli typu stĺpca
    try:
        d = dt.datetime.strptime(produce_date, "%Y-%m-%d")
    except Exception:
        return jsonify({"ok": False, "error": "Neplatný formát dátumu (YYYY-MM-DD)"}), 400
    dt_prod = dt.datetime(d.year, d.month, d.day, 6, 0, 0)

    # INSERT do zaznamy_vyroba ako „planned“
    # (ak máš inú tabuľku pre úlohy výroby, zmeň SQL podľa seba)
    sql = """
        INSERT INTO zaznamy_vyroba
            (vyrobok_id, datum_vyroby, planovane_mnozstvo, skutocne_vyrobene, stav, celkova_cena_surovin)
        VALUES
            (%s, %s, %s, NULL, %s, NULL)
    """
    status = "planned"
    conn = None
    try:
        conn = db_connector.get_connection()
        cur = conn.cursor()
        cur.execute(sql, (product_id, dt_prod, final_kg, status))
        conn.commit()
        new_id = cur.lastrowid
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"ok": False, "error": f"DB chyba: {str(e)}"}), 500
    finally:
        try:
            if cur: cur.close()
        except: pass
        try:
            if conn and conn.is_connected(): conn.close()
        except: pass

    return jsonify({
        "ok": True,
        "task": {
            "id": new_id,
            "product_id": product_id,
            "product_name": meta.get("name",""),
            "plan_kg": round(final_kg, 3),
            "produce_date": produce_date,
            "status": status
        }
    })
