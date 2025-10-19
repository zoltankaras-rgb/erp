# ai_handler.py — Kancelária: AI Asistent (chat nad DB)
# Minimal viable "chat over ERP" s jednoduchou detekciou zámeru (intentu)
# Bez externého LLM — vie odpovedať na základné otázky a vrátiť tab. dáta.
#
# Integrácia v app.py (príklad):
#   @app.route('/api/kancelaria/ai/<action>', methods=['POST'])
#   def ai_api(action):
#       payload = request.get_json(silent=True) or {}
#       import ai_handler
#       if action == 'chat': return jsonify(ai_handler.ai_chat(**payload))
#       if action == 'suggest': return jsonify(ai_handler.ai_suggestions(**payload))
#       return jsonify({'error':'Unknown action'}), 400

from datetime import datetime, timedelta
import re
import db_connector

# --- helpers -----------------------------------------------------------------
def _month_range(year=None, month=None):
    now = datetime.now()
    y = int(year or now.year)
    m = int(month or now.month)
    start = datetime(y, m, 1)
    end = datetime(y + (1 if m==12 else 0), 1 if m==12 else (m+1), 1)
    return start, end

def _safe_get(row, key, default=0):
    try:
        v = row.get(key)
        return float(v) if v is not None else default
    except Exception:
        return default

def _has_table(table: str) -> bool:
    row = db_connector.execute_query(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s LIMIT 1",
        (table,), 'one'
    )
    return bool(row)

def _has_column(table: str, column: str) -> bool:
    row = db_connector.execute_query(
        "SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s LIMIT 1",
        (table, column), 'one'
    )
    return bool(row)

def _pick_col(table: str, candidates, default=None):
    for c in candidates:
        if _has_column(table, c):
            return c
    return default

# --- core intent handlers -----------------------------------------------------
def _intent_b2b_this_month(year=None, month=None):
    if not _has_table('b2b_objednavky'):
        return "Nemám tabuľku b2b_objednavky.", {}
    start, end = _month_range(year, month)
    agg = db_connector.execute_query(
        "SELECT COUNT(*) c, COALESCE(SUM(celkova_suma),0) t FROM b2b_objednavky WHERE datum_objednavky BETWEEN %s AND %s",
        (start, end), 'one'
    ) or {'c':0,'t':0}
    rows = db_connector.execute_query(
        """SELECT DATE_FORMAT(o.datum_objednavky,'%%d.%%m.%%Y') AS datum,
                  COALESCE(z.nazov_firmy,'') AS zakaznik,
                  COALESCE(o.status,'') AS stav,
                  COALESCE(o.celkova_suma,0) AS celkom
           FROM b2b_objednavky o
           LEFT JOIN b2b_zakaznici z ON z.id=o.zakaznik_id
           WHERE o.datum_objednavky BETWEEN %s AND %s
           ORDER BY o.datum_objednavky DESC LIMIT 20""",
        (start, end)
    ) or []
    reply = f"V tomto období evidujem {int(agg.get('c',0))} B2B objednávok v sume {float(agg.get('t',0)):.2f} €."
    return reply, {"columns":["Dátum","Zákazník","Stav","Celkom €"], "rows": rows}

def _intent_b2c_this_month(year=None, month=None):
    if not _has_table('b2c_objednavky'):
        return "Nemám tabuľku b2c_objednavky.", {}
    start, end = _month_range(year, month)
    agg = db_connector.execute_query(
        "SELECT COUNT(*) c, COALESCE(SUM(celkom_s_dph),0) t FROM b2c_objednavky WHERE datum BETWEEN %s AND %s",
        (start, end), 'one'
    ) or {'c':0,'t':0}
    rows = db_connector.execute_query(
        """SELECT DATE_FORMAT(datum,'%%d.%%m.%%Y %%H:%%i') AS datum, id AS b2c_id, body, celkom_s_dph
           FROM b2c_objednavky
           WHERE datum BETWEEN %s AND %s
           ORDER BY datum DESC LIMIT 20""",
        (start, end)
    ) or []
    reply = f"V tomto období je {int(agg.get('c',0))} B2C objednávok v sume {float(agg.get('t',0)):.2f} € (s DPH)."
    return reply, {"columns":["Dátum","ID","Body","Celkom s DPH €"], "rows": rows}

def _intent_low_stock():
    rows = db_connector.execute_query(
        """SELECT p.nazov, p.kategoria, p.jednotka,
                  COALESCE(p.min_zasoba,0) AS min_zasoba,
                  COALESCE(SUM(sp.mnozstvo),0) AS qty
           FROM sklad_polozky sp
           JOIN sklady_ext   s ON s.id = sp.sklad_id
           JOIN produkty_ext p ON p.id = sp.produkt_id
           WHERE ( (s.typ='vyrobny' AND p.typ='surovina')
                OR (s.typ='centralny' AND p.typ<>'surovina') )
           GROUP BY p.id, p.nazov, p.kategoria, p.jednotka, p.min_zasoba
           HAVING qty < p.min_zasoba
           ORDER BY (p.typ='surovina') DESC, p.kategoria, p.nazov
           LIMIT 30"""
    ) or []
    if not rows:
        return "Všetky sledované položky sú nad minimom.", {}
    return "Tu sú položky pod min. zásobou.", {"columns":["Názov","Kategória","Jednotka","Min.","Stav"],
                                               "rows":[{"Názov":r["nazov"],"Kategória":r.get("kategoria") or "",
                                                        "Jednotka":r.get("jednotka") or "", "Min.":r.get("min_zasoba"),
                                                        "Stav":r.get("qty")} for r in rows]}

def _intent_top_products():
    dv = _pick_col('zaznamy_vyroba',['datum_vyroby','datum_ukoncenia','datum','created_at','updated_at'])
    jn = _pick_col('zaznamy_vyroba',['vyrobok_id','produkt_id','product_id'])
    qt = _pick_col('zaznamy_vyroba',['skutocne_vyrobene','realne_mnozstvo','vyrobene_mnozstvo','mnozstvo_skutocne','mnozstvo'])
    if not (dv and jn and qt): return "Pre TOP produkty mi chýbajú stĺpce v zaznamy_vyroba.", {}
    since = (datetime.now().date() - timedelta(days=30))
    rows = db_connector.execute_query(
        f"""SELECT p.nazov AS produkt, SUM(zv.{qt}) AS vyrobene_kg
            FROM zaznamy_vyroba zv
            JOIN produkty_ext p ON p.id = zv.{jn}
            WHERE DATE({dv}) >= %s
            GROUP BY p.nazov
            ORDER BY vyrobene_kg DESC
            LIMIT 10""",
        (since,)
    ) or []
    return "TOP výrobky za 30 dní:", {"columns":["Produkt","Vyrobené (kg)"], "rows": rows}

# --- public API ----------------------------------------------------------------
def ai_chat(message: str = "", year=None, month=None):
    """
    Vstup: message (string), voliteľne year/month
    Výstup: { reply: str, table?: {columns:[], rows:[]}, tips?:[] }
    """
    msg = (message or "").strip()
    if not msg:
        return {"reply": "Ahoj! Spýtaj sa ma na B2B/B2C objednávky, nízke zásoby alebo TOP výrobky."}

    txt = msg.lower()

    # základné intent pravidlá
    if ('b2b' in txt) and ('objedn' in txt or 'order' in txt):
        reply, table = _intent_b2b_this_month(year, month)
        return {"reply": reply, "table": table}
    if ('b2c' in txt) and ('objedn' in txt or 'order' in txt):
        reply, table = _intent_b2c_this_month(year, month)
        return {"reply": reply, "table": table}
    if ('min' in txt and 'zásob' in txt) or ('low' in txt and 'stock' in txt):
        reply, table = _intent_low_stock()
        return {"reply": reply, "table": table}
    if ('top' in txt and 'produkt' in txt) or ('top' in txt and 'výrob' in txt):
        reply, table = _intent_top_products()
        return {"reply": reply, "table": table}

    # fallback – informatívna odpoveď
    return {
        "reply": "Rozumiem základným okruhom: 'B2B objednávky', 'B2C objednávky', 'nízke zásoby', 'TOP výrobky'. "
                 "Skús to prosím presnejšie – postupne budeme rozširovať intent pravidlá."
    }

def ai_suggestions():
    """Vráti tipy, čo sa dá pýtať (na UI tlačidlá)."""
    return {
        "suggestions": [
            "Koľko B2B objednávok máme tento mesiac?",
            "Koľko B2C objednávok je tento mesiac?",
            "Ktoré položky sú pod minimom zásob?",
            "TOP produkty za 30 dní"
        ]
    }
