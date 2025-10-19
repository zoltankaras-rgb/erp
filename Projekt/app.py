# pyright: reportMissingImports=false, reportMissingModuleSource=false
from flask import (
    Flask, render_template, jsonify, request, session, redirect, url_for,
    make_response, send_from_directory, send_file, Response
)
from flask_mail import Mail
from datetime import datetime, timedelta, date
from functools import wraps
import os
import io
import traceback
import inspect
import json
import hashlib, binascii, secrets

from dotenv import load_dotenv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# === interné moduly ===
from logger import logger
import db_connector
import data_handler
import auth_handler  # nechávam pre iné časti, interný login/check/logout robíme lokálne

# CSRF helpery
from csrf import csrf_protect, inject_csrf, ensure_csrf_token

# Handlery modulov
import production_handler
import expedition_handler
import office_handler
import office_catalog_stock_handler
import b2b_handler
import b2c_handler
import fleet_handler
import hygiene_handler
import profitability_handler
import costs_handler
import pdf_generator
from notification_handler import (
    send_order_confirmation_email,
    send_b2c_order_confirmation_email_with_pdf
)
from server.akcie import akcie_bp

# --------------------------------------------------------------------------------------
# Inicializácia
# --------------------------------------------------------------------------------------
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.json.ensure_ascii = False
app.config['JSON_AS_ASCII'] = False

# 🔁 Auto-reload šablón a vypnutie cache statických súborov (DEV)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# SECRET_KEY (nutný pre session)
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise ValueError("KRITICKÁ CHYBA: SECRET_KEY nie je nastavený v .env súbore!")

app.permanent_session_lifetime = timedelta(hours=8)
# cookies
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = "Lax"
app.config['SESSION_COOKIE_SECURE'] = False  # v dev prostredí

# Mail
app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "465")),
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_USE_SSL=os.getenv("MAIL_USE_SSL", "True").lower() == "true",
    MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "False").lower() == "true",
    MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com"),
)
mail = Mail(app)
app.register_blueprint(akcie_bp, url_prefix="/api/kancelaria/akcie")

# --------------------------------------------------------------------------------------
# Pomocníci (DB a pod.)
# --------------------------------------------------------------------------------------
def _db_execute_one(query, params=None):
    """Fallback na execute_one; ak ho v db_connector nemáš, použije execute_query."""
    fn = getattr(db_connector, "execute_one", None)
    if callable(fn):
        return fn(query, params)
    rows = db_connector.execute_query(query, params) or []
    return rows[0] if rows else None

# --------------------------------------------------------------------------------------
# Mod auth – pomocníci (per-modulová autentifikácia)
# --------------------------------------------------------------------------------------
def _detect_module_from_request(default='vyroba'):
    """
    'vyroba' | 'expedicia' | 'kancelaria' – podľa URL/Refereru
    """
    txt = f"{request.path} {request.headers.get('Referer','')}".lower()
    if '/expedicia' in txt:   return 'expedicia'
    if '/kancelaria' in txt:  return 'kancelaria'
    if '/vyroba' in txt:      return 'vyroba'
    return default

def _mod_is_authenticated(mod_name: str) -> bool:
    mods = session.get('mod_auth') or {}
    return bool(mods.get(mod_name))

def _mod_set_authenticated(mod_name: str, val: bool):
    mods = session.get('mod_auth') or {}
    mods[mod_name] = bool(val)
    session['mod_auth'] = mods

# --------------------------------------------------------------------------------------
# Dekorátory
# --------------------------------------------------------------------------------------
def login_required(role=None):
    """
    role: None | "kancelaria" | "admin" | ["kancelaria","admin"] | ...
    - 401: neprihlásený
    - 403: prihlásený, ale nemá rolu
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                return jsonify({'error': 'Prístup zamietnutý. Prosím, prihláste sa.'}), 401
            if role is not None:
                allowed = [role] if isinstance(role, str) else list(role)
                if user.get('role') not in allowed:
                    return jsonify({'error': 'Nemáte oprávnenie na túto akciu.'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def b2c_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'b2c_user' not in session:
            return jsonify({'error': 'Pre túto akciu musíte byť prihlásený.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def handle_request(handler_func, *args, **kwargs):
    """
    Jednotný wrapper: vyrobí payload z JSON + route kwargs a zavolá handler cez _call_handler.
    """
    try:
        payload = {}
        if request.method in ['POST', 'PUT', 'PATCH'] and (request.is_json or request.mimetype == 'application/json'):
            payload = request.get_json(silent=True) or {}
        payload = {**payload, **kwargs}

        result = _call_handler(handler_func, payload)

        if isinstance(result, Response):
            return result
        if isinstance(result, dict) and result.get("error"):
            return jsonify(result), 400

        # nikdy neposielaj JSON null do FE
        if result is None:
            return jsonify({"ok": True}), 200

        return jsonify(result), 200
    except Exception:
        logger.error(
            "SERVER ERROR in handler '%s'\n%s",
            getattr(handler_func, '__name__', 'unknown'),
            traceback.format_exc()
        )
        return jsonify({'error': "Interná chyba servera. Kontaktujte administrátora."}), 500


# --------------------------------------------------------------------------------------
# CSRF & UTF-8
# --------------------------------------------------------------------------------------
@app.before_request
def _ensure_csrf_token_safe():
    try:
        ensure_csrf_token()
    except Exception as e:
        app.logger.warning(f"ensure_csrf_token: {e}")

@app.before_request
def _csrf_protect_safe():
    if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
        return None

    # výnimky: login/check/logout – nech login nepadá na CSRF
    if request.path.startswith(('/api/internal/login',
                                '/api/internal/check_session',
                                '/api/internal/logout')):
        return None

    token = (
        request.headers.get('X-CSRFToken')
        or request.headers.get('X-CSRF-Token')
        or (request.get_json(silent=True) or {}).get('csrf_token')
        or request.form.get('csrf_token')
        or request.args.get('csrf_token')
    )
    expected = session.get('csrf_token')

    if not token or not expected or token != expected:
        return jsonify({'error': 'CSRF validation failed'}), 403

    return None

@app.after_request
def _inject_csrf_safe(response):
    try:
        ensure_csRF = ensure_csrf_token()  # istota, že token existuje v session
        token = session.get('csrf_token')
        if token:
            # nastav oboje – frontend niekde číta 'XSRF-TOKEN'
            response.set_cookie('csrf_token', token, samesite='Lax', httponly=False)
            response.set_cookie('XSRF-TOKEN', token, samesite='Lax', httponly=False)
        return inject_csrf(response)
    except Exception as e:
        app.logger.error(f"inject_csrf failed: {e}")
        return response

@app.after_request
def force_utf8_for_html(response):
    if response is not None and response.mimetype == 'text/html':
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------
@app.route('/')
def index():
    if 'user' in session:
        role = session['user'].get('role')
        if role == 'expedicia':
            return redirect(url_for('page_expedicia'))
        if role in ('kancelaria', 'admin'):
            return redirect(url_for('page_kancelaria'))
    return redirect(url_for('page_vyroba'))

@app.route('/vyroba')
def page_vyroba():
    user = session.get('user')
    # musí mať rolu a zároveň pečiatku pre modul vyroba
    if (not user or user.get('role') not in ('vyroba', 'kancelaria', 'admin')
        or not _mod_is_authenticated('vyroba')):
        return render_template('login.html')
    return render_template('vyroba.html')

@app.route('/expedicia')
def page_expedicia():
    user = session.get('user')
    if (not user or user.get('role') not in ('expedicia', 'admin')
        or not _mod_is_authenticated('expedicia')):
        return render_template('login.html')
    return render_template('expedicia.html')

@app.route('/kancelaria')
def page_kancelaria():
    user = session.get('user')
    if (not user or user.get('role') not in ('kancelaria', 'admin')
        or not _mod_is_authenticated('kancelaria')):
        return render_template('login.html')
    return render_template('kancelaria.html')

@app.route('/b2b')
def page_b2b():
    return render_template('b2b.html')

@app.route('/b2c')
def page_b2c():
    return render_template('b2c.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/x-icon')

# --------------------------------------------------------------------------------------
# Interné prihlásenie (zjednotené – auth_handler + pečiatka modulu)
# --------------------------------------------------------------------------------------
PBKDF2_ITER = 250_000  # podľa tvojho create_internal_user.py

@app.post('/api/internal/login')
def api_internal_login():
    data = request.get_json(silent=True) or request.form or {}
    # použijeme tvoju overovaciu logiku (správny hashing, email/username, is_active)
    result = auth_handler.internal_login(**data)
    if result.get('error'):
        return (result['error'], 401)

    # nastav pečiatku pre konkrétny modul (vyroba/expedicia/kancelaria)
    mod = (data.get('module') or '').strip().lower()
    if mod not in ('vyroba','expedicia','kancelaria'):
        mod = _detect_module_from_request(default='vyroba')
    _mod_set_authenticated(mod, True)

    return ('', 204)

@app.get('/api/internal/check_session')
def internal_check_session():
    u = session.get('user')
    mod = request.args.get('module') or _detect_module_from_request()
    return jsonify({
        "authenticated": bool(u),
        "loggedIn": bool(u),
        "ok": bool(u),
        "module": mod,
        "moduleAuthenticated": _mod_is_authenticated(mod),
        "user": u,
        "user_id": session.get('user_id'),
        "role": session.get('role')
    }), 200

@app.post('/api/internal/logout')
def api_internal_logout():
    session.clear()
    return ('', 204)

# --------------------------------------------------------------------------------------
# API – Výroba
# --------------------------------------------------------------------------------------
def _vyroba_menu_data_adapter():
    try:
        rec = production_handler.get_categorized_recipes()
        recipes = rec.get('data', rec) if isinstance(rec, dict) else {}
    except Exception:
        recipes = {}
    return {
        "recipes": recipes,
        "planned": production_handler.get_planned_production_tasks_by_category(),
        "running": production_handler.get_running_production_tasks_by_category(),
        "warehouse": production_handler.get_warehouse_state()
    }

@app.context_processor
def inject_csrf_to_templates():
    try:
        ensure_csrf_token()  # vytvorí session['csrf_token'] ak chýba
    except Exception:
        pass
    return {"csrf_token": session.get("csrf_token", "")}

@app.route('/api/vyroba/getMenuData')
@login_required(role=['vyroba', 'kancelaria'])
def get_vyroba_menu_data():
    return handle_request(lambda: _vyroba_menu_data_adapter())

@app.route('/api/vyroba/recipes')
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_recipes():
    return handle_request(production_handler.get_categorized_recipes)

@app.route('/api/vyroba/planned')
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_planned():
    return handle_request(production_handler.get_planned_production_tasks_by_category)

@app.route('/api/vyroba/running')
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_running():
    return handle_request(production_handler.get_running_production_tasks_by_category)

# Rozklik detail prebiehajúcej dávky
@app.route('/api/vyroba/running/detail', methods=['POST'])
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_running_detail():
    return handle_request(production_handler.get_running_production_detail)

# Štart/finish výroby
@app.route('/api/vyroba/start', methods=['POST'])
@login_required(role='vyroba')
def api_vyroba_start():
    return handle_request(production_handler.start_production, workerName=session['user'].get('full_name'))

@app.route('/api/vyroba/startProduction', methods=['POST'])
@login_required(role='vyroba')
def start_vyroba_production():
    return handle_request(production_handler.start_production, workerName=session['user'].get('full_name'))

@app.route('/api/vyroba/finish', methods=['POST'])
@login_required(role=['vyroba', 'expedicia'])
def api_vyroba_finish():
    return handle_request(production_handler.finish_production, workerName=session['user'].get('full_name'))

# Sklad
@app.route('/api/sklad/getWarehouse')
@login_required(role=['vyroba', 'kancelaria'])
def get_sklad_warehouse():
    return handle_request(production_handler.get_warehouse_state)

@app.route('/api/vyroba/getWarehouseState')
@login_required(role=['vyroba', 'kancelaria'])
def get_vyroba_warehouse_state():
    return handle_request(production_handler.get_warehouse_state)

@app.route('/api/sklad/items')
@login_required(role=['vyroba', 'kancelaria'])
def api_sklad_items():
    return handle_request(lambda: production_handler.get_all_warehouse_items())

# Kalkulácia surovín
@app.route('/api/vyroba/calculateIngredients', methods=['POST'])
@login_required(role=['vyroba', 'kancelaria'])
def calculate_vyroba_ingredients():
    data = request.get_json(silent=True) or {}
    vyrobok_id = int(data.get('vyrobok_id') or 0)
    planned_weight = float(data.get('plannedWeight') or 0)
    if vyrobok_id <= 0 or planned_weight <= 0:
        return jsonify({"error": "Chýba vyrobok_id alebo plannedWeight > 0."}), 400

    sql = """
        SELECT
            rp.surovina_id,
            rp.mnozstvo_na_davku AS per100,
            p.nazov,
            COALESCE(sp.mnozstvo, 0) AS sklad_qty,
            COALESCE(sp.priemerna_cena, 0) AS unit_cost
        FROM recepty_polozky rp
        JOIN recepty r ON r.id = rp.recept_id
        JOIN products p ON p.id = rp.surovina_id
        LEFT JOIN sklad_polozky sp
               ON sp.produkt_id = p.id AND sp.sklad_id = 1
        WHERE r.vyrobok_id = %s
    """
    rows = db_connector.execute_query(sql, (vyrobok_id,)) or []
    if not rows:
        return jsonify({"error": "Výrobok nemá definovaný recept."}), 400

    mult = planned_weight / 100.0
    items, missing, total_cost = [], [], 0.0
    for r in rows:
        required = float(r['per100']) * mult
        in_stock = float(r['sklad_qty'] or 0.0)
        unit_cost = float(r['unit_cost'] or 0.0)
        total_cost += unit_cost * required
        if in_stock + 1e-9 < required:
            missing.append({
                "product_id": r['surovina_id'],
                "name": r['nazov'],
                "required": round(required, 3),
                "in_stock": round(in_stock, 3),
                "shortage": round(required - in_stock, 3)
            })
        items.append({
            "product_id": r['surovina_id'],
            "name": r['nazov'],
            "required_kg": round(required, 3),
            "in_stock_kg": round(in_stock, 3),
            "unit_cost": round(unit_cost, 4),
            "total_cost": round(unit_cost * required, 2)
        })
    return jsonify({
        "ingredients": items,
        "can_start": len(missing) == 0,
        "missing": missing,
        "plannedWeight": planned_weight,
        "total_cost_estimate": round(total_cost, 2)
    })

# Inventúra – sklady, skupiny, uloženie kategórie, dokončenie
@app.route('/api/vyroba/inventory/warehouses')
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_inventory_warehouses():
    return handle_request(production_handler.list_inventory_warehouses)

# --- Inventúra: skupiny (Mäso, Obaly, Koreniny, Pomocný materiál, Ostatné)
@app.route('/api/vyroba/inventory/groups')
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_inventory_groups():
    grp = (request.args.get('group') or '').strip()
    return handle_request(production_handler.get_production_inventory_groups, group=grp)

# --- Inventúra: uloženie jednej kategórie
@app.route('/api/vyroba/inventory/submitCategory', methods=['POST'])
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_inventory_submit_cat():
    return handle_request(production_handler.submit_inventory_category)

# --- Inventúra: dokončenie celej inventúry (ak chceš jedným krokom)
@app.route('/api/vyroba/inventory/complete', methods=['POST'])
@login_required(role=['vyroba', 'kancelaria'])
def api_vyroba_inventory_complete():
    return handle_request(production_handler.update_inventory)

# Weekly needs/plan (proxy)
@app.route('/api/vyroba/weeklyNeeds')
@login_required(role=['vyroba', 'kancelaria'])
def vyroba_weekly_needs():
    return jsonify({"items": []})

@app.route('/api/vyroba/weeklyPlan')
@login_required(role=['vyroba', 'kancelaria'])
def vyroba_weekly_plan():
    return jsonify({"items": []})

# Ručný odpis (nový aj legacy aliasy)
@app.route('/api/sklad/writeoff', methods=['POST'])
@login_required(role=['vyroba', 'kancelaria'])
def api_sklad_writeoff():
    return handle_request(production_handler.manual_warehouse_write_off, workerName=session['user'].get('full_name'))

@app.route('/api/vyroba/manualWriteOff', methods=['POST'])
@login_required(role=['vyroba', 'kancelaria'])
def manual_vyroba_write_off():
    return handle_request(production_handler.manual_warehouse_write_off, workerName=session['user'].get('full_name'))

# --------------------------------------------------------------------------------------
# API – Expedícia
# --------------------------------------------------------------------------------------
@app.route('/api/expedicia/slicing/needs', methods=['POST'])
@login_required(role='expedicia')
def api_slicing_needs_from_orders():
    payload = request.get_json(silent=True) or {}
    return handle_request(expedition_handler.get_slicing_needs_from_orders, plan_date=payload.get('plan_date'))

@app.route('/api/expedicia/scanPayload', methods=['POST'])
@login_required(role=['expedicia','kancelaria','vyroba'])
def scan_payload():
    data = request.json or {}
    code = (data.get('code') or '').strip()
    if code.startswith('BATCH:'):
        batch_id = int(code.split(':',1)[1])
        return jsonify(expedition_handler.get_batch_full_info(batch_id))
    return jsonify({"error":"Neznámy formát kódu."}), 400

@app.route('/api/expedicia/getExpeditionData')
@login_required(role='expedicia')
def get_exp_data():
    return handle_request(expedition_handler.get_expedition_data)

@app.route('/api/expedicia/getProductionDates')
@login_required(role='expedicia')
def get_prod_dates():
    return handle_request(expedition_handler.get_production_dates)

@app.route('/api/expedicia/getProductionsByDate', methods=['POST'])
@login_required(role='expedicia')
def get_prods_by_date():
    payload = request.get_json(silent=True) or {}
    try:
        data = _call_handler(expedition_handler.get_productions_by_date, payload)
    except Exception:
        app.logger.error("getProductionsByDate failed:\n%s", traceback.format_exc())
        return jsonify({"items": [], "error": "server"}), 200

    # skry prijaté/ukončené
    def _is_pending(item):
        st = (item or {}).get('status') or ''
        st = str(st).strip()
        return st not in ('Prijaté, čaká na tlač', 'Prijaté', 'Ukončené')

    if isinstance(data, dict):
        items = data.get('items') or data.get('productions') or []
        filtered = [x for x in items if _is_pending(x)]
        if 'items' in data:
            data['items'] = filtered
        elif 'productions' in data:
            data['productions'] = filtered
        else:
            data = filtered
        return jsonify(data), 200

    if isinstance(data, list):
        return jsonify([x for x in data if _is_pending(x)]), 200

    return jsonify([]), 200

@app.post('/api/expedicia/completeProductions')
@login_required(role='expedicia')
def api_complete_productions():
    raw = request.get_json(silent=True)
    if isinstance(raw, list):
        payload = {"items": raw}
    elif isinstance(raw, dict) and "items" in raw:
        payload = {"items": raw["items"]}
    else:
        payload = {"items": []}
    return handle_request(expedition_handler.complete_multiple_productions, payload)

@app.post('/api/expedicia/finalizeDay')
@login_required(role='expedicia')
def api_finalize_day():
    data = request.get_json(silent=True) or {}
    return handle_request(expedition_handler.finalize_day, data)

@app.route('/api/expedicia/getAccompanyingLetter', methods=['POST'])
@login_required(role=['expedicia', 'kancelaria'])
def get_letter():
    data = expedition_handler.get_accompanying_letter_data(**(request.json or {}))
    if 'error' in data:
        return make_response(f"<h1>Chyba: {data['error']}</h1>", 404)
    worker = (request.json or {}).get('workerName')
    template_data = {
        "title": "Sprievodný List",
        "report_date": datetime.now().strftime('%d.%m.%Y %H:%M'),
        "data": {**data, 'prebral': worker}
    }
    return make_response(render_template('daily_report_template.html', is_accompanying_letter=True, **template_data))

@app.route('/api/expedicia/getAcceptedByDate', methods=['POST'])
@login_required(role='expedicia')
def api_get_accepted_by_date():
    data = request.json or {}
    d = data.get('date') or data.get('datum')
    if not d:
        return jsonify({"items":[]})
    items = expedition_handler.get_accepted_by_date(d)
    return jsonify({"items": items})

@app.route('/api/expedicia/finalizeSlicing', methods=['POST'])
@login_required(role='expedicia')
def finalize_slicing_api():
    return handle_request(finalize_slicing_transaction)

@app.route('/api/expedicia/manualReceive', methods=['POST'])
@login_required(role='expedicia')
def manual_receive_api():
    return handle_request(manual_receive_product)

@app.route('/api/expedicia/logDamage', methods=['POST'])
@login_required(role='expedicia')
def log_damage_api():
    return handle_request(log_manual_damage)

@app.route('/api/expedicia/getProductsForInventory')
@login_required(role=['expedicia', 'kancelaria'])
def get_products_for_inventory_api():
    return handle_request(get_products_for_inventory)

@app.route('/api/expedicia/getAllFinalProducts')
@login_required(role=['expedicia', 'kancelaria'])
def get_final_products():
    return handle_request(expedition_handler.get_all_final_products)

# --- DOPLNKY PRE EXPEDÍCIU ---
@app.route('/api/expedicia/getSlicableProducts')
@login_required(role='expedicia')
def api_get_slicable_products():
    return handle_request(expedition_handler.get_slicable_products)

@app.route('/api/expedicia/startSlicingRequest', methods=['POST'])
@login_required(role='expedicia')
def api_start_slicing_request():
    return handle_request(expedition_handler.start_slicing_request)

@app.route('/api/expedicia/submitProductInventory', methods=['POST'])
@login_required(role='expedicia')
def api_submit_product_inventory():
    payload = request.get_json(silent=True) or {}
    return handle_request(
        expedition_handler.submit_product_inventory,
        inventory_data=payload.get('inventoryData'),
        worker_name=payload.get('WorkerName') or payload.get('workerName')
    )

# Prijať položky
@app.post('/api/expedicia/acceptProductions')
@login_required(role='expedicia')
def api_accept_productions():
    data = request.get_json(silent=True) or {}
    return handle_request(expedition_handler.accept_productions, **data)

# Tlač príjemky podľa accept_id
@app.get('/api/expedicia/printAcceptance')
@login_required(role=['expedicia', 'kancelaria'])
def api_print_acceptance_get():
    accept_id = (request.args.get('accept_id') or '').strip()
    info = expedition_handler.get_acceptance_doc(accept_id)
    if not info or 'error' in info:
        return make_response(f"<h1>{info.get('error','Neplatné accept_id')}</h1>", 404)
    return render_template('expedicia/acceptance_receipt.html', info=info)

# Návrat do výroby
@app.post('/api/expedicia/returnToProduction')
@login_required(role='expedicia')
def api_return_to_production():
    data = request.get_json(silent=True) or {}
    return handle_request(expedition_handler.return_to_production, **data)

# --------------------------------------------------------------------------------------
# Inteligentné volanie handlerov
# --------------------------------------------------------------------------------------
def _call_handler(handler, payload: dict):
    """
    Flexibilné volanie handlera.
    """
    try:
        sig = inspect.signature(handler)
    except (ValueError, TypeError):
        try:
            return handler(**payload)
        except TypeError:
            return handler(payload)

    params = sig.parameters
    accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

    # required non-var parametre
    required = []
    for name, p in params.items():
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        if p.default is inspect._empty:
            required.append(name)

    # #1: jeden required param, nie je v payload -> pošli celý payload pod tým menom
    if len(required) == 1 and required[0] not in payload:
        key = required[0]
        try:
            return handler(**{key: payload})
        except TypeError:
            return handler(payload)

    # #2: ak handler prijíma **kwargs a required sú pokryté
    if accepts_kwargs and all((name in payload) for name in required):
        return handler(**payload)

    # #3: pošli len tie kľúče, ktoré handler pozná
    filtered = {k: payload[k] for k, p in params.items()
                if k in payload and p.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)}

    # #4: presne 1 non-var parameter a je POVINNÝ -> pošli dict pozične
    non_var_params = [p for p in params.values()
                      if p.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)]
    if len(non_var_params) == 1 and not filtered:
        only_param = non_var_params[0]
        if only_param.default is inspect._empty:
            return handler(payload)
        return handler()

    # #5: skús kwargs cez filtered, inak fallbacky
    try:
        if filtered:
            return handler(**filtered)
        if not non_var_params and not accepts_kwargs:
            return handler()
        return handler(payload)
    except TypeError:
        return handler(payload)

# ===== Kancelária – Dodacie listy (list, detail, pdf) =====
def _dl_parse_date(s, default):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return default

# --- Pomocné: robustný parse dátumu z UI / JSON / RFC stringov ---
def _dl_parse_any_date(s, default=None):
    if not s:
        return default
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    txt = str(s).strip()
    try:
        return datetime.strptime(txt[:10], "%Y-%m-%d").date()
    except Exception:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(txt, fmt).date()
        except Exception:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(txt, fmt).date()
        except Exception:
            pass
    return default

def _dl_sql_date_txt(s):
    d = _dl_parse_any_date(s, None)
    return d.strftime("%Y-%m-%d") if d else None

def api_delivery_notes_list(payload):
    """
    GET /api/kancelaria/receive/delivery-notes?from=YYYY-MM-DD&to=YYYY-MM-DD&warehouse_id=1
    Vracia: [{supplier, day:'YYYY-MM-DD', items, total_qty, total_value}, ...]
    """
    today = datetime.today().date()

    def _parse_any_date(s, default):
        if not s:
            return default
        if isinstance(s, date):
            return s
        if isinstance(s, datetime):
            return s.date()
        txt = str(s).strip()
        try:
            return datetime.strptime(txt[:10], "%Y-%m-%d").date()
        except Exception:
            pass
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                return datetime.strptime(txt, fmt).date()
            except Exception:
                pass
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(txt, fmt).date()
            except Exception:
                pass
        return default

    def _to_sql_date(d):
        return d.strftime("%Y-%m-%d") if isinstance(d, (date, datetime)) else str(d)[:10]

    def _to_iso_day_cell(v):
        if isinstance(v, datetime):
            return v.date().strftime("%Y-%m-%d")
        if isinstance(v, date):
            return v.strftime("%Y-%m-%d")
        s = str(v).strip()
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            return s[:10]
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except Exception:
                pass
        return s[:10]

    d1 = _parse_any_date(payload.get('from'), today.replace(day=1))
    d2 = _parse_any_date(payload.get('to'),   today)
    wh = payload.get('warehouse_id')

    sql = """
        SELECT
            zp.dodavatel AS supplier,
            DATE(zp.datum) AS day,
            COUNT(*) AS items,
            SUM(zp.mnozstvo) AS total_qty,
            SUM(zp.mnozstvo * zp.cena) AS total_value
        FROM zaznamy_prijem zp
        WHERE zp.datum >= %s AND zp.datum < DATE_ADD(%s, INTERVAL 1 DAY)
    """
    params = [_to_sql_date(d1), _to_sql_date(d2)]
    if wh:
        sql += " AND zp.sklad_id = %s"
        params.append(int(wh))
    sql += " GROUP BY supplier, day ORDER BY day DESC, supplier ASC"

    rows = db_connector.execute_query(sql, tuple(params), fetch='all') or []
    for r in rows:
        r['day'] = _to_iso_day_cell(r.get('day'))

    return rows

def api_delivery_note_detail(payload):
    supplier = (payload.get('supplier') or '').strip()
    day = (payload.get('day') or '').strip()
    if not supplier or not day:
        return {'error':'missing supplier/day'}

    wh = payload.get('warehouse_id')
    sql = """
        SELECT zp.id,
               COALESCE(p.nazov, sp.nazov) AS produkt,
               zp.mnozstvo, zp.cena
          FROM zaznamy_prijem zp
     LEFT JOIN products p ON p.id = zp.produkt_id
     LEFT JOIN sklad_produkty sp ON sp.id = zp.produkt_id
         WHERE zp.dodavatel=%s AND DATE(zp.datum)=%s
    """
    params = [supplier, day]
    if wh:
        sql += " AND zp.sklad_id = %s"
        params.append(int(wh))
    sql += " ORDER BY zp.id"
    rows = db_connector.execute_query(sql, tuple(params), fetch='all') or []
    return {'supplier': supplier, 'day': day, 'items': rows}

def api_delivery_note_pdf(payload):
    """
    GET /api/kancelaria/receive/delivery-note/pdf?supplier=...&day=YYYY-MM-DD
    """
    supplier = (payload.get('supplier') or '').strip()

    def _parse_any_date(s, default=None):
        if not s:
            return default
        if isinstance(s, date):
            return s
        if isinstance(s, datetime):
            return s.date()
        txt = str(s).strip()
        try:
            return datetime.strptime(txt[:10], "%Y-%m-%d").date()
        except Exception:
            pass
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                return datetime.strptime(txt, fmt).date()
            except Exception:
                pass
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(txt, fmt).date()
            except Exception:
                pass
        return default

    d = _parse_any_date(payload.get('day'), None)
    if not supplier or not d:
        return {'error': 'missing supplier/day'}
    day_iso = d.strftime("%Y-%m-%d")

    def _register_sk_font():
        REG, BOLD = "SKSans", "SKSans-Bold"
        if REG in pdfmetrics.getRegisteredFontNames():
            return REG, BOLD
        candidates_regular = [
            os.path.join(app.root_path, 'static', 'fonts', 'DejaVuSans.ttf'),
            os.path.join(app.root_path, 'static', 'fonts', 'NotoSans-Regular.ttf'),
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ]
        candidates_bold = [
            os.path.join(app.root_path, 'static', 'fonts', 'DejaVuSans-Bold.ttf'),
            os.path.join(app.root_path, 'static', 'fonts', 'NotoSans-Bold.ttf'),
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        reg_path = next((p for p in candidates_regular if os.path.exists(p)), None)
        bold_path = next((p for p in candidates_bold if os.path.exists(p)), None)
        if not reg_path:
            return "Helvetica", "Helvetica-Bold"
        pdfmetrics.registerFont(TTFont(REG, reg_path))
        pdfmetrics.registerFont(TTFont(BOLD if bold_path else REG, bold_path or reg_path))
        return REG, BOLD

    FONT_REG, FONT_BOLD = _register_sk_font()

    wh = payload.get('warehouse_id')
    sql = """
        SELECT COALESCE(p.nazov, sp.nazov) AS produkt,
               zp.mnozstvo, zp.cena
          FROM zaznamy_prijem zp
     LEFT JOIN products p ON p.id = zp.produkt_id
     LEFT JOIN sklad_produkty sp ON sp.id = zp.produkt_id
         WHERE zp.dodavatel=%s AND DATE(zp.datum)=%s
    """
    params = [supplier, day_iso]
    if wh:
        sql += " AND zp.sklad_id = %s"
        params.append(int(wh))
    sql += " ORDER BY zp.id"

    rows = db_connector.execute_query(sql, tuple(params), fetch='all') or []

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x, y = 20*mm, H - 20*mm

    def _num(v, n=3):
        try:
            return f"{float(v):,.{n}f}".replace(",", " ").replace(".", ",")
        except Exception:
            return "0"

    c.setAuthor("ERP MIK s.r.o.")
    try:
        c.setTitle(f"Dodací list – {supplier} – {day_iso}")
    except Exception:
        pass

    c.setFont(FONT_BOLD, 14)
    c.drawString(x, y, "Dodací list – príjem")
    c.setFont(FONT_REG, 10)
    y -= 6*mm; c.drawString(x, y, f"Dodávateľ: {supplier}")
    y -= 5*mm; c.drawString(x, y, f"Dátum: {day_iso}")
    y -= 8*mm

    c.setFont(FONT_BOLD, 10)
    c.drawString(x, y, "Produkt")
    c.drawString(x+90*mm,  y, "Množstvo (kg)")
    c.drawString(x+120*mm, y, "Cena/kg (€)")
    c.drawString(x+150*mm, y, "Spolu (€)")
    y -= 4*mm; c.line(x, y, W-20*mm, y); y -= 2*mm
    c.setFont(FONT_REG, 10)

    total = 0.0
    for r in rows:
        if y < 25*mm:
            c.showPage(); y = H - 20*mm
            c.setFont(FONT_BOLD, 10)
            c.drawString(x, y, "Produkt")
            c.drawString(x+90*mm,  y, "Množstvo (kg)")
            c.drawString(x+120*mm, y, "Cena/kg (€)")
            c.drawString(x+150*mm, y, "Spolu (€)")
            y -= 4*mm; c.line(x, y, W-20*mm, y); y -= 2*mm
            c.setFont(FONT_REG, 10)

        prod  = r.get('produkt') or ''
        qty   = float(r.get('mnozstvo') or 0)
        price = float(r.get('cena') or 0)
        line  = qty * price
        total += line

        c.drawString(x, y, str(prod))
        c.drawRightString(x+110*mm, y, _num(qty,3))
        c.drawRightString(x+140*mm, y, _num(price,4))
        c.drawRightString(W-20*mm,  y, _num(line,2))
        y -= 6*mm

    y -= 4*mm
    c.setFont(FONT_BOLD, 11)
    c.drawRightString(W-20*mm, y, f"Spolu: {_num(total,2)} €")

    c.showPage(); c.save()
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf',
                     download_name=f"dodaci_list_{supplier}_{day_iso}.pdf".replace(' ', '_'))

# ===== Recepty – META uloženie (bez zmeny DB) =====
RECIPES_META_DIR = os.path.join(app.root_path, 'data', 'recipes_meta')
os.makedirs(RECIPES_META_DIR, exist_ok=True)

def _recipe_meta_path(recipe_id: int) -> str:
    return os.path.join(RECIPES_META_DIR, f"{int(recipe_id)}.json")

def _recipe_meta_default():
    return {
        "version": 1,
        "header": {
            "batch_size_kg": 100.0,
            "yield_expected_kg": None,
            "shelf_life_days": None,
            "storage_temp_c": None,
            "allergens": [],
            "labels_text": ""
        },
        "norms": {
            "salt_pct": None,
            "fat_pct": None,
            "water_pct": None,
            "ph_target": None,
            "additives": []
        },
        "process": [],
        "qc": [],
        "notes": ""
    }

def erp_recipes_meta_get(payload):
    recipe_id = int(payload.get("recipe_id") or 0)
    if recipe_id <= 0:
        return {"error": "missing recipe_id"}
    p = _recipe_meta_path(recipe_id)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return {"ok": True, "meta": json.load(f)}
        except Exception as e:
            return {"error": f"read meta failed: {e}"}
    return {"ok": True, "meta": _recipe_meta_default()}

def erp_recipes_meta_save(payload):
    recipe_id = int(payload.get("recipe_id") or 0)
    meta = payload.get("meta")
    if recipe_id <= 0 or not isinstance(meta, dict):
        return {"error": "missing recipe_id or invalid meta"}
    try:
        with open(_recipe_meta_path(recipe_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return {"ok": True}
    except Exception as e:
        return {"error": f"save meta failed: {e}"}

def erp_recipes_list(payload):
    cat = payload.get("category_id")
    q = (payload.get("q") or "").strip()
    params = []
    sql = """
        SELECT r.id AS recipe_id, p.id AS product_id, p.nazov, p.ean,
               pc.name AS prod_category
          FROM recepty r
          JOIN products p ON p.id = r.vyrobok_id
     LEFT JOIN production_categories pc ON pc.id = p.production_category_id
         WHERE 1=1
    """
    if cat:
        sql += " AND p.production_category_id = %s"
        params.append(int(cat))
    if q:
        sql += " AND (p.nazov LIKE %s OR p.ean LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY p.nazov"
    rows = db_connector.execute_query(sql, tuple(params), fetch='all') or []
    return {"items": rows}

def erp_recipes_print(payload):
    recipe_ids = payload.get("recipe_ids") or []
    if not recipe_ids:
        rid = payload.get("recipe_id")
        if rid: recipe_ids = [rid]
    recipe_ids = [int(x) for x in recipe_ids if int(x) > 0]
    if not recipe_ids:
        return {"error": "no recipes to print"}

    REG, BOLD = "SKSans", "SKSans-Bold"
    if REG not in pdfmetrics.getRegisteredFontNames():
        candidates_regular = [
            os.path.join(app.root_path, 'static', 'fonts', 'DejaVuSans.ttf'),
            os.path.join(app.root_path, 'static', 'fonts', 'NotoSans-Regular.ttf'),
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ]
        candidates_bold = [
            os.path.join(app.root_path, 'static', 'fonts', 'DejaVuSans-Bold.ttf'),
            os.path.join(app.root_path, 'static', 'fonts', 'NotoSans-Bold.ttf'),
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        reg = next((p for p in candidates_regular if os.path.exists(p)), None)
        bold = next((p for p in candidates_bold if os.path.exists(p)), None)
        if reg:
            pdfmetrics.registerFont(TTFont(REG, reg))
            pdfmetrics.registerFont(TTFont(BOLD if bold else REG, bold or reg))
        else:
            REG, BOLD = "Helvetica", "Helvetica-Bold"

    def _read_recipe(recipe_id):
        info = db_connector.execute_query("""
            SELECT r.id AS recipe_id, p.id AS product_id, p.nazov, p.ean,
                   pc.name AS prod_category, p.production_unit, p.piece_weight_g
              FROM recepty r
              JOIN products p ON p.id = r.vyrobok_id
         LEFT JOIN production_categories pc ON pc.id = p.production_category_id
             WHERE r.id = %s
        """, (recipe_id,), fetch='one') or {}
        items = db_connector.execute_query("""
            SELECT rp.surovina_id, m.nazov, rp.mnozstvo_na_davku
              FROM recepty_polozky rp
              JOIN products m ON m.id = rp.surovina_id
             WHERE rp.recept_id = %s
             ORDER BY m.nazov
        """, (recipe_id,), fetch='all') or []
        meta = _recipe_meta_default()
        p = _recipe_meta_path(recipe_id)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass
        return info, items, meta

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    def num(v, n=3):
        try: return f"{float(v):,.{n}f}".replace(",", " ").replace(".", ",")
        except: return ""

    for rid in recipe_ids:
        info, items, meta = _read_recipe(rid)
        c.setFont(BOLD, 14)
        c.drawString(20*mm, H-20*mm, f"Receptúra – {info.get('nazov','')}")
        c.setFont(REG, 10)
        c.drawString(20*mm, H-26*mm, f"EAN: {info.get('ean','')}")
        c.drawString(90*mm, H-26*mm, f"Kategória: {info.get('prod_category','')}")
        c.drawString(20*mm, H-31*mm, f"Dávka (kg): {num(meta['header'].get('batch_size_kg') or 100, 3)}")
        if meta['header'].get('yield_expected_kg'):
            c.drawString(90*mm, H-31*mm, f"Oč. výťažnosť (kg): {num(meta['header']['yield_expected_kg'],3)}")

        y = H-40*mm
        c.setFont(BOLD, 11); c.drawString(20*mm, y, "Normy"); y -= 5*mm; c.setFont(REG, 10)
        norms = meta.get('norms', {})
        line = []
        if norms.get('salt_pct') is not None: line.append(f"Soľ: {num(norms['salt_pct'],2)} %")
        if norms.get('fat_pct')  is not None: line.append(f"Tuk: {num(norms['fat_pct'],2)} %")
        if norms.get('water_pct')is not None: line.append(f"Voda: {num(norms['water_pct'],2)} %")
        if norms.get('ph_target')is not None: line.append(f"pH: {norms['ph_target']}")
        c.drawString(20*mm, y, " | ".join(line)); y -= 6*mm
        adds = norms.get('additives') or []
        if adds:
            addon_text = ", ".join([f"{a.get('name','')} {a.get('mg_per_kg','')} mg/kg" for a in adds])
            c.drawString(20*mm, y, "Prísady: " + addon_text)
            y -= 6*mm

        c.setFont(BOLD, 11)
        c.drawString(20*mm, y, "Suroviny (na 100 kg)")
        y -= 5*mm
        c.setFont(REG, 10)
        c.drawString(20*mm, y, "Surovina")
        c.drawRightString(110*mm, y, "Množstvo (kg)")
        y -= 4*mm
        c.line(20*mm, y, 120*mm, y)
        y -= 2*mm

        for it in items:
            if y < 25*mm:
                c.showPage(); y = H-20*mm; c.setFont(REG, 10)
            c.drawString(20*mm, y, it.get('nazov',''))
            c.drawRightString(110*mm, y, num(it.get('mnozstvo_na_davku'), 3))
            y -= 5*mm

        steps = meta.get('process') or []
        if y < 40*mm: c.showPage(); y = H-20*mm
        c.setFont(BOLD, 11); c.drawString(20*mm, y, "Postup práce"); y -= 5*mm; c.setFont(REG, 10)
        if steps:
            for s in steps:
                if y < 25*mm: c.showPage(); y = H-20*mm; c.setFont(REG,10)
                t = f"{s.get('no','')}. {s.get('title','')}"
                extras = []
                if s.get('grinder_mm'): extras.append(f"mletie: {s['grinder_mm']} mm")
                if s.get('temp_c') is not None: extras.append(f"t: {s['temp_c']} °C")
                if s.get('time_min') is not None: extras.append(f"čas: {s['time_min']} min")
                if s.get('rpm'): extras.append(f"RPM: {s['rpm']}")
                c.drawString(20*mm, y, t + ("  [" + ", ".join(extras) + "]" if extras else ""))
                y -= 5*mm
                notes = s.get('notes','')
                if notes:
                    for line in notes.splitlines():
                        if y < 25*mm: c.showPage(); y = H-20*mm; c.setFont(REG,10)
                        c.drawString(25*mm, y, f"– {line}")
                        y -= 5*mm
        else:
            c.drawString(20*mm, y, "—"); y -= 5*mm

        notes = meta.get('notes') or meta.get('header',{}).get('labels_text','')
        if notes:
          if y < 30*mm: c.showPage(); y = H-20*mm
          c.setFont(BOLD, 11); c.drawString(20*mm, y, "Poznámky / Návod"); y -= 5*mm; c.setFont(REG, 10)
          for line in notes.splitlines():
              if y < 25*mm: c.showPage(); y = H-20*mm
              c.drawString(20*mm, y, line); y -= 5*mm

        c.showPage()

    c.save(); buf.seek(0)
    return send_file(buf, mimetype='application/pdf', download_name="receptury.pdf")

# --------------------------------------------------------------------------------------
# API – Kancelária (dispatcher)
# --------------------------------------------------------------------------------------
@app.route('/api/kancelaria/<path:subpath>', methods=['GET', 'POST'])
@login_required(role=['kancelaria','admin'])
def kancelaria_api(subpath):
    endpoint_map = {
        # --- SKLAD/RAW ---
        'getWarehouses':                 office_catalog_stock_handler.get_warehouses,
        'raw/getCategories':             office_catalog_stock_handler.raw_get_categories,
        'raw/list':                      office_catalog_stock_handler.raw_list_by_category,
        'raw/addMaterialProduct':        office_catalog_stock_handler.raw_add_material_product,
        'raw/receive':                   office_catalog_stock_handler.raw_receive_material,
        'raw/writeoff':                  office_catalog_stock_handler.raw_writeoff_material,
        # --- PRÍJEM VÝROBNÝ SKLAD ---
        'prodReceive/getSuppliers':   office_catalog_stock_handler.prod_receive_get_suppliers,
        'prodReceive/getTemplate':    office_catalog_stock_handler.prod_receive_get_template,
        'prodReceive/saveBatch':      office_catalog_stock_handler.prod_receive_save_batch,

        # --- ERP ADMIN / KATALÓG ---
        'erp/catalog/overview':          getattr(office_handler, 'erp_catalog_overview', lambda *a, **k: {"ok": True}),
        'erp/catalog/salesCategories':   office_handler.erp_get_sales_categories,
        'erp/catalog/addSalesCategory':  office_handler.erp_add_sales_category,
        'erp/catalog/addProduct':        office_handler.erp_add_catalog_product,

        # --- Dashboard & dáta ---
        'getDashboardData':              office_handler.get_kancelaria_dashboard_data,
        'getKancelariaBaseData':         office_handler.get_kancelaria_base_data,
        'getComprehensiveStockView':     office_handler.get_comprehensive_stock_view,
        'receiveStockItems':             office_catalog_stock_handler.receive_multiple_stock_items,

        # --- Plánovanie / forecast ---
        'getProductionPlan':             office_handler.calculate_production_plan,
        'createTasksFromPlan':           office_handler.create_production_tasks_from_plan,
        'get_7_day_forecast':            office_handler.get_7_day_order_forecast,
        # 'create_urgent_task':          office_handler.create_urgent_production_task,
        'getPurchaseSuggestions':        office_handler.get_purchase_suggestions,
        'getProductionStats':            office_handler.get_production_stats,

        # --- Promo ---
        'get_promotions_data':           office_handler.get_promotions_data,
        'manage_promotion_chain':        office_handler.manage_promotion_chain,
        'save_promotion':                office_handler.save_promotion,
        'delete_promotion':              office_handler.delete_promotion,

        # --- Staršie katalóg API (kompatibilita) ---
        'addCatalogItem':                office_handler.add_catalog_item,
        'updateCatalogItem':             office_handler.update_catalog_item,
        'deleteCatalogItem':             office_handler.delete_catalog_item,
        'getProductsForMinStock':        office_handler.get_products_for_min_stock,
        'updateMinStockLevels':          office_handler.update_min_stock_levels,

        # --- Recepty ---
        'addNewRecipe':                  office_handler.add_new_recipe,
        'getAllRecipes':                 office_handler.get_all_recipes_for_editing,
        'getRecipeDetails':              office_handler.get_recipe_details,
        'updateRecipe':                  office_handler.update_recipe,
        'deleteRecipe':                  office_handler.delete_recipe,
        'getSlicingManagementData':      office_handler.get_slicing_management_data,
        'linkSlicedProduct':             office_handler.link_sliced_product,
        'createAndLinkSlicedProduct':    office_handler.create_and_link_sliced_product,

        # --- B2B admin ---
        'getPendingB2BRegistrations':    b2b_handler.get_pending_b2b_registrations,
        'approveB2BRegistration':        b2b_handler.approve_b2b_registration,
        'rejectB2BRegistration':         b2b_handler.reject_b2b_registration,
        'b2b/getCustomersAndPricelists': b2b_handler.get_customers_and_pricelists,
        'b2b/updateCustomer':            b2b_handler.update_customer_details,
        'b2b/getPricelistsAndProducts':  b2b_handler.get_pricelists_and_products,
        'b2b/createPricelist':           b2b_handler.create_pricelist,
        'b2b/getPricelistDetails':       b2b_handler.get_pricelist_details,
        'b2b/updatePricelist':           b2b_handler.update_pricelist,
        'b2b/getAnnouncement':           b2b_handler.get_announcement,
        'b2b/saveAnnouncement':          b2b_handler.save_announcement,
        'b2b/getAllOrders':              b2b_handler.get_all_b2b_orders,

        # --- B2C admin ---
        'b2c/get_orders':                office_handler.get_b2c_orders_for_admin,
        'b2c/finalize_order':            office_handler.finalize_b2c_order,
        'b2c/credit_points':             office_handler.credit_b2c_loyalty_points,
        'b2c/cancel_order':              office_handler.cancel_b2c_order,
        'b2c/get_customers':             office_handler.get_b2c_customers_for_admin,
        'b2c/get_pricelist_admin':       office_handler.get_b2c_pricelist_for_admin,
        'b2c/update_pricelist':          office_handler.update_b2c_pricelist,
        'b2c/get_rewards':               office_handler.get_b2c_rewards_for_admin,
        'b2c/add_reward':                office_handler.add_b2c_reward,
        'b2c/toggle_reward_status':      office_handler.toggle_b2c_reward_status,

        # --- FLEET ---
        'fleet/getData':                 fleet_handler.get_fleet_data,
        'fleet/saveLog':                 fleet_handler.save_daily_log,
        'fleet/saveVehicle':             getattr(fleet_handler, 'save_vehicle_safe', fleet_handler.save_vehicle),
        'fleet/saveRefueling':           fleet_handler.save_refueling,
        'fleet/deleteRefueling':         fleet_handler.delete_refueling,
        'fleet/getAnalysis':             fleet_handler.get_fleet_analysis,
        'fleet/getCosts':                fleet_handler.get_fleet_costs,
        'fleet/saveCost':                fleet_handler.save_fleet_cost,
        'fleet/deleteCost':              fleet_handler.delete_fleet_cost,

        # --- Hygiena/HACCP ---
        'hygiene/getPlan':               hygiene_handler.get_hygiene_plan_for_date,
        'hygiene/getAgents':             hygiene_handler.get_hygiene_agents,
        'hygiene/saveAgent':             hygiene_handler.save_hygiene_agent,
        'hygiene/getTasks':              hygiene_handler.get_all_hygiene_tasks,
        'hygiene/saveTask':              hygiene_handler.save_hygiene_task,
        'hygiene/logStart':              hygiene_handler.log_hygiene_start,
        'hygiene/logFinish':             hygiene_handler.log_hygiene_finish,
        'hygiene/logCompletion':         hygiene_handler.log_hygiene_completion,
        'hygiene/checkLog':              hygiene_handler.check_hygiene_log,

        # --- Ziskovosť ---
        'profitability/getData':                 profitability_handler.get_profitability_data,
        'profitability/saveDepartmentData':      profitability_handler.save_department_data,
        'profitability/saveProductionData':      profitability_handler.save_production_profit_data,
        'profitability/setupSalesChannel':       profitability_handler.setup_new_sales_channel,
        'profitability/saveSalesChannelData':    profitability_handler.save_sales_channel_data,
        'profitability/saveCalculation':         profitability_handler.save_calculation,
        'profitability/deleteCalculation':       profitability_handler.delete_calculation,
        'profitability/getDashboard':            profitability_handler.get_profitability_dashboard,

        # --- Náklady ---
        'costs/getData':           costs_handler.get_costs_data,
        'costs/saveEnergy':        costs_handler.save_energy_data,
        'costs/saveHR':            costs_handler.save_hr_data,
        'costs/saveOperational':   costs_handler.save_operational_cost,
        'costs/deleteOperational': costs_handler.delete_operational_cost,
        'costs/saveCategory':      costs_handler.save_cost_category,
        'costs/getDashboard':      costs_handler.get_dashboard_data,
        'costs/getAnnual':         costs_handler.get_energy_annual_json,

        # --- HACCP ---
        'getHaccpDocs':            office_handler.get_haccp_docs,
        'getHaccpDocContent':      office_handler.get_haccp_doc_content,
        'saveHaccpDoc':            office_handler.save_haccp_doc,

        # --- Suroviny – príjem ---
        'stock/receive/meat':      office_catalog_stock_handler.receive_meat_items,
        'stock/receive/other':     office_catalog_stock_handler.receive_other_items,
        'raw/products/meat':       office_catalog_stock_handler.raw_list_products_meat,
        'raw/products/other':      office_catalog_stock_handler.raw_list_products_other,

        # --- Dodávatelia ---
        'erp/suppliers/list':      office_catalog_stock_handler.erp_list_suppliers,
        'erp/suppliers/add':       office_catalog_stock_handler.erp_add_supplier,

        # --- Reporty príjmu (výrobný sklad) ---
        'reports/receipts/summary': office_catalog_stock_handler.report_receipts_summary,
        'reports/receipts/pdf':     office_catalog_stock_handler.report_receipts_pdf,

        # --- ERP ADMIN: Recepty + výrobné meta ---
        'erp/recipes/products':     office_catalog_stock_handler.erp_recipes_products,
        'erp/recipes/materials':    office_catalog_stock_handler.erp_recipes_materials,
        'erp/recipes/get':          office_catalog_stock_handler.erp_recipe_get,
        'erp/recipes/save':         office_catalog_stock_handler.erp_recipe_save,
        'erp/prodcat/list':         office_catalog_stock_handler.erp_prodcat_list,
        'erp/prodcat/add':          office_catalog_stock_handler.erp_prodcat_add,
        'erp/product/prodmeta/get': office_catalog_stock_handler.erp_product_prodmeta_get,
        'erp/product/prodmeta/save':office_catalog_stock_handler.erp_product_prodmeta_save,

        # --- Reporty príjmu (alias) ---
        'reports/receipts':         office_catalog_stock_handler.report_receipts_summary,

        # --- Dodacie listy (výrobný sklad) ---
        'receive/delivery-notes':        api_delivery_notes_list,
        'receive/delivery-note/detail':  api_delivery_note_detail,
        'receive/delivery-note/pdf':     api_delivery_note_pdf,

        # --- ERP: Recepty – meta, list, tlač ---
        'erp/recipes/meta/get':   erp_recipes_meta_get,
        'erp/recipes/meta/save':  erp_recipes_meta_save,
        'erp/recipes/list':       erp_recipes_list,
        'erp/recipes/print':      erp_recipes_print,
    }
    handler = endpoint_map.get(subpath)
    if handler is None:
        return jsonify({"error": f"Neznámy endpoint: {subpath}"}), 404

    payload = {}
    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
    payload.update({k: v for k, v in (request.args or {}).items() if k not in payload})

    try:
        resp = _call_handler(handler, payload)
        if isinstance(resp, Response):
            return resp
        if resp is None:
            return jsonify({"message": "OK"}), 200
        if isinstance(resp, (str, bytes)):
            return jsonify({"message": resp if isinstance(resp, str) else resp.decode('utf-8','ignore')}), 200
        return jsonify(resp), 200
    except Exception as e:
        app.logger.error(f"[kancelaria_api:{subpath}] {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Server error v {subpath}: {str(e)}"}), 200

# --- AI Assistant ---
import ai_handler

@app.route('/api/kancelaria/ai/<action>', methods=['POST'])
@login_required(role=['kancelaria','admin'])
def ai_api(action):
    payload = request.get_json(silent=True) or {}
    if action == 'chat':
        return jsonify(ai_handler.ai_chat(**payload))
    elif action == 'suggest':
        return jsonify(ai_handler.ai_suggestions())
    return jsonify({'error':'Unknown action'}), 400

# --- Communication Center (webmail) ---
@app.route('/api/kancelaria/comm/<action>', methods=['POST'])
@login_required(role=['kancelaria','admin'])
def comm_api(action):
    import communication_handler as comm
    p = request.get_json(silent=True) or {}

    if action == 'sync':        return jsonify(comm.comm_sync_inbox())
    if action == 'list':        return jsonify(comm.comm_list(p))
    if action == 'get':         return jsonify(comm.comm_get(p.get('id')))
    if action == 'unreadCount': return jsonify({"unread": comm.comm_unread_count()})
    if action == 'markRead':    return jsonify(comm.comm_mark_read(p.get('id'), bool(p.get('read', True))))

    if action == 'send':        return jsonify(comm.comm_send_mime())
    if action == 'delete':      return jsonify(comm.comm_delete(p, bool(p.get('purge', False))))
    if action == 'markSpam':    return jsonify(comm.comm_mark_spam(p.get('ids')))

    if action == 'editorConfig':        return jsonify(comm.comm_editor_config(p.get('owner_email')))
    if action == 'saveSignature':       return jsonify(comm.comm_save_signature(p.get('owner_email'), p.get('display_name',''), p.get('signature_html',''), bool(p.get('make_default', True))))
    if action == 'savePrefs':           return jsonify(comm.comm_save_prefs(p.get('owner_email'), p.get('font_family','Inter, Arial, sans-serif'), p.get('font_size','14px'), p.get('font_color','#111111')))
    if action == 'signatures':          return jsonify(comm.comm_list_signatures(p.get('owner_email')))
    if action == 'setDefaultSignature': return jsonify(comm.comm_set_default_signature(p.get('id'), p.get('owner_email')))
    if action == 'deleteSignature':     return jsonify(comm.comm_delete_signature(p.get('id'), p.get('owner_email')))

    if action == 'smtpProbe':   return jsonify(comm.comm_smtp_probe())
    if action == 'imapProbe':   return jsonify(comm.comm_imap_probe())

    return jsonify({'error':'Unknown action'}), 400

@app.route('/api/kancelaria/comm/attachment/<int:att_id>', methods=['GET'])
@login_required(role=['kancelaria','admin'])
def comm_attachment_download(att_id):
    import communication_handler as comm
    res = comm.comm_get_attachment_stream(att_id)
    if isinstance(res, Response) or hasattr(res, 'direct_passthrough'):
        return res
    return jsonify(res), 404

# --------------------------------------------------------------------------------------
# Reporty
# --------------------------------------------------------------------------------------
@app.route('/traceability/<batch_id>')
@login_required(role=['expedicia', 'kancelaria'])
def page_traceability(batch_id):
    return render_template('traceability.html', batch_id=batch_id)

@app.route('/api/traceability/<batch_id>')
@login_required(role=['expedicia', 'kancelaria'])
def get_api_traceability_info(batch_id):
    return handle_request(expedition_handler.get_traceability_info, batch_id=batch_id)

@app.route('/report/receipt')
@login_required(role='kancelaria')
def report_receipt():
    return office_handler.get_receipt_report_html(
        request.args.get('period', 'day'),
        request.args.get('category', 'Všetky')
    )

@app.route('/report/profitability')
@login_required(role=['kancelaria', 'admin'])
def report_profitability():
    return profitability_handler.get_profitability_report_html(**request.args)

@app.route('/report/costs/energy')
def report_costs_energy():
    return costs_handler.get_energy_report_html(**request.args)

@app.route('/report/costs/energyAnnual')
def report_costs_energy_annual():
    return costs_handler.get_energy_annual_report_html(**request.args)

@app.route('/report/inventory')
@login_required(role='kancelaria')
def report_inventory():
    return office_handler.get_inventory_difference_report_html(
        request.args.get('date')
    )

@app.route('/report/fleet')
@login_required(role=['kancelaria', 'admin'])
def report_fleet():
    return fleet_handler.get_report_html_content(**request.args)

@app.route('/report/hygiene')
@login_required(role='kancelaria')
def report_hygiene():
    data = hygiene_handler.get_hygiene_report_data(
        date=request.args.get('date'),
        period=request.args.get('period', 'denne'),
        task=request.args.get('task'),
        agent_id=request.args.get('agent_id')
    )
    if not data:
        return "<h1>Chyba: Nepodarilo sa vygenerovať dáta pre report.</h1>", 400
    return make_response(render_template('hygiene_report_template.html', **data))

@app.route('/api/kancelaria/b2b/get_order_details/<int:order_id>')
@login_required(role='kancelaria')
def get_b2b_order_details(order_id):
    return handle_request(lambda: b2b_handler.get_order_details(order_id))

@app.route('/api/kancelaria/b2b/print_order_pdf/<int:order_id>')
@login_required(role='kancelaria')
def print_b2b_order_pdf_route(order_id):
    order_data_result = b2b_handler.get_b2b_order_details(id=order_id)
    if 'error' in order_data_result:
        return make_response(f"<h1>Chyba: {order_data_result['error']}</h1>", 404)
    order_data = order_data_result.get("order")
    pdf_content, _ = pdf_generator.create_order_files(order_data)
    response = make_response(pdf_content)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=objednavka_{order_data.get("order_number", order_id)}.pdf'
    return response

# --------------------------------------------------------------------------------------
# Pomocné funkcie – expedícia (ponechané)
# --------------------------------------------------------------------------------------
def finalize_slicing_transaction(data):
    log_id = data.get("logId")
    actual_pieces = int(data.get("actualPieces") or 0)
    if not log_id or actual_pieces <= 0:
        return {"error": "Chýba log alebo neplatný počet kusov."}

    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM slicing_logs WHERE id = %s", (log_id,))
        log = cursor.fetchone()
        if not log:
            return {"error": "Log krájania neexistuje."}

        source_id = log["source_product_id"]
        target_id = log["sliced_product_id"]

        cursor.execute("""
            UPDATE sklad_polozky
            SET mnozstvo = mnozstvo - 1
            WHERE sklad_id = 2 AND produkt_id = %s
        """, (source_id,))

        cursor.execute("""
            SELECT id, mnozstvo FROM sklad_polozky
            WHERE sklad_id = 2 AND produkt_id = %s
        """, (target_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE sklad_polozky SET mnozstvo = %s WHERE id = %s",
                (row["mnozstvo"] + actual_pieces, row["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo) VALUES (2, %s, %s)",
                (target_id, actual_pieces)
            )

        cursor.execute("""
            UPDATE slicing_logs
            SET actual_pieces = %s, status = 'finished', finished_at = NOW()
            WHERE id = %s
        """, (actual_pieces, log_id))

        conn.commit()
        return {"message": f"Krájanie bolo dokončené ({actual_pieces} ks)."}
    except Exception as e:
        if conn: conn.rollback()
        raise e
    finally:
        if conn and conn.is_connected(): conn.close()

def manual_receive_product(data):
    produkt_id = data.get("produkt_id")
    mnozstvo = float(data.get("mnozstvo") or 0.0)
    cena = float(data.get("cena") or 0.0)
    worker = data.get("workerName") or "neznámy"
    if not produkt_id or mnozstvo <= 0:
        return {"error": "Chýba produkt alebo neplatné množstvo."}

    sklad_id = 2
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO zaznamy_prijem (sklad_id, produkt_id, datum, mnozstvo, cena, dodavatel)
            VALUES (%s, %s, NOW(), %s, %s, %s)
        """, (sklad_id, produkt_id, mnozstvo, cena, worker))

        cursor.execute("""
            SELECT id, mnozstvo, priemerna_cena
            FROM sklad_polozky
            WHERE sklad_id = %s AND produkt_id = %s
        """, (sklad_id, produkt_id))
        row = cursor.fetchone()

        if row:
            new_qty = float(row[1]) + mnozstvo
            new_price = ((row[1] * float(row[2] or 0)) + (mnozstvo * cena)) / new_qty if new_qty > 0 else cena
            cursor.execute(
                "UPDATE sklad_polozky SET mnozstvo = %s, priemerna_cena = %s WHERE id = %s",
                (new_qty, new_price, row[0])
            )
        else:
            cursor.execute(
                "INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, nakupna_cena) VALUES (2, %s, %s, %s)",
                (produkt_id, mnozstvo, cena)
            )

        conn.commit()
        return {"message": f"Príjem produktu {produkt_id} bol uložený."}
    except Exception as e:
        if conn: conn.rollback()
        raise e
    finally:
        if conn and conn.is_connected(): conn.close()

def log_manual_damage(data):
    produkt_id = data.get("produkt_id")
    mnozstvo = float(data.get("mnozstvo") or 0.0)
    worker = data.get("workerName") or "neznámy"
    note = data.get("note") or "nezadané"
    if not produkt_id or mnozstvo <= 0:
        return {"error": "Chýba produkt alebo neplatné množstvo."}

    sklad_id = 2
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, mnozstvo FROM sklad_polozky
            WHERE sklad_id = %s AND produkt_id = %s
        """, (sklad_id, produkt_id))
        row = cursor.fetchone()
        if not row:
            return {"error": "Produkt sa v sklade nenašiel."}
        if row[1] < mnozstvo:
            return {"error": "Na sklade nie je dostatok množstva na odpis."}

        cursor.execute(
            "UPDATE sklad_polozky SET mnozstvo = %s WHERE id = %s",
            (row[1] - mnozstvo, row[0])
        )
        cursor.execute("""
            INSERT INTO skody (datum, id_davky, nazov_vyrobku, mnozstvo, dovod, pracovnik)
            SELECT NOW(), NULL, p.nazov, %s, %s, %s
            FROM produkty p WHERE p.id = %s
        """, (mnozstvo, note, worker, produkt_id))

        conn.commit()
        return {"message": f"Odpis škody {mnozstvo} ks/kg produktu {produkt_id} bol zapísaný."}
    except Exception as e:
        if conn: conn.rollback()
        raise e
    finally:
        if conn and conn.is_connected(): conn.close()

def get_products_for_inventory():
    # centrál = sklad_id = 2
    query = """
        SELECT p.id as produkt_id, COALESCE(p.nazov, pp.nazov) AS nazov,
               COALESCE(p.typ, pp.typ) AS typ,
               sp.mnozstvo, COALESCE(p.jednotka, pp.jednotka) AS jednotka
        FROM sklad_polozky sp
   LEFT JOIN products  p  ON p.id  = sp.produkt_id
   LEFT JOIN produkty  pp ON pp.id = sp.produkt_id
       WHERE sp.sklad_id = 2
       ORDER BY nazov
    """
    return db_connector.execute_query(query)

# --------------------------------------------------------------------------------------
# Spustenie (DEV auto-reload)
# --------------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=True,
        threaded=True
    )
