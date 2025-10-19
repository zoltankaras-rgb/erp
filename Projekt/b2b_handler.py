from validators import validate_required_fields, safe_get_float, safe_get_int
import hashlib
import os
import secrets
import traceback
import io
from datetime import datetime, timedelta
from logger import logger  

import db_connector
import notification_handler
import pdf_generator

# PDF / ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# =================================================================
# === BEZPEČNOSTNÉ FUNKCIE PRE PRÁCU S HESLAMI ===
# =================================================================

def generate_password_hash(password: str):
    """Vygeneruje bezpečnú 'soľ' (salt) a hash pre zadané heslo pomocou PBKDF2."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 250000)
    return salt.hex(), key.hex()

def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Overí, či sa zadané heslo zhoduje s uloženou soľou a hashom."""
    try:
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(hash_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 250000)
        return new_key == stored_key
    except (ValueError, TypeError):
        return False

# =================================================================
# === ZÍSKAVANIE DÁT PRE ZÁKAZNÍKA (CENNÍKY / PRODUKTY) ===
# =================================================================

def get_products_for_pricelist(pricelist_id: int):
    """Získa produkty a ich ceny pre konkrétny cenník, zoskupené podľa kategórie (prepísané na produkt_id)."""
    if not pricelist_id:
        return {"error": "Chýba ID cenníka."}

    # Cenníkové položky naviazané na produkty
    query = """
        SELECT 
            cp.id AS cennik_polozka_id,
            cp.produkt_id,
            p.nazov,
            p.jednotka,
            p.kategoria,
            p.dph,
            cp.cena
        FROM b2b_cennik_polozky cp
        JOIN produkty p ON cp.produkt_id = p.id
        WHERE cp.cennik_id = %s
        ORDER BY p.kategoria, p.nazov
    """
    rows = db_connector.execute_query(query, (pricelist_id,))

    # Výstup zoskupený podľa kategórií
    grouped = {}
    for r in rows:
        kat = r["kategoria"] or "Nezaradené"
        if kat not in grouped:
            grouped[kat] = []
        grouped[kat].append({
            "produkt_id": r["produkt_id"],
            "nazov": r["nazov"],
            "jednotka": r["jednotka"],
            "cena": safe_get_float(r["cena"] or 0),
            "dph": safe_get_float(r["dph"] or 0)
        })

    return grouped

def get_customer_data(user_id):
    """Získa dáta pre zákazníka, vrátane oznamu a cenníkov."""
    pricelists_query = """
        SELECT c.id, c.nazov_cennika 
        FROM b2b_cenniky c 
        JOIN b2b_zakaznik_cennik zc ON c.id = zc.cennik_id 
        WHERE zc.zakaznik_id = %s
    """
    pricelists = db_connector.execute_query(pricelists_query, (user_id,))
    announcement_record = db_connector.execute_query("SELECT hodnota FROM b2b_nastavenia WHERE kluc = 'oznam'", fetch='one')
    announcement = announcement_record['hodnota'] if announcement_record else ""
    response = {"pricelists": pricelists, "announcement": announcement}
    if pricelists and len(pricelists) == 1:
        response.update(get_products_for_pricelist(pricelist_id=pricelists[0]['id']))
    return response

# =================================================================
# === PRIHLASOVANIE, REGISTRÁCIA, OBJEDNÁVKY ===
# =================================================================

def process_b2b_login(data: dict):
    """Spracuje prihlásenie B2B zákazníka a vráti dáta pre portál."""
    zakaznik_id, password = data.get('zakaznik_id'), data.get('password')
    if not zakaznik_id or not password:
        return {"error": "Musíte zadať prihlasovacie meno aj heslo."}

    query = """
        SELECT id, nazov_firmy, email, heslo_hash, heslo_salt, je_schvaleny, je_admin
        FROM b2b_zakaznici
        WHERE zakaznik_id = %s AND typ = 'B2B'
    """
    user = db_connector.execute_query(query, (zakaznik_id,), fetch='one')

    if not user or not verify_password(password, user['heslo_salt'], user['heslo_hash']):
        return {"error": "Nesprávne prihlasovacie meno alebo heslo."}
    
    if not user['je_admin'] and not user['je_schvaleny']:
        return {"error": "Váš účet ešte nebol schválený administrátorom."}

    response_data = {
        "id": user['id'],
        "zakaznik_id": zakaznik_id,
        "nazov_firmy": user['nazov_firmy'],
        "email": user['email'],
        "role": "admin" if user['je_admin'] else "zakaznik"
    }
    
    if not user['je_admin']:
        response_data.update(get_customer_data(user['id']))

    return {"message": "Prihlásenie úspešné.", "userData": response_data}

def process_b2b_registration(data: dict):
    """Spracuje novú B2B registráciu, odošle notifikácie a uloží do DB."""
    required = ['email', 'nazov_firmy', 'adresa', 'adresa_dorucenia', 'telefon', 'password']
    if not all(field in data for field in required):
        return {"error": "Všetky polia sú povinné."}
    if not data.get('gdpr'):
        return {"error": "Musíte súhlasiť so spracovaním osobných údajov."}
    
    # Kontrola existujúceho emailu len pre typ B2B
    if db_connector.execute_query(
        "SELECT id FROM b2b_zakaznici WHERE email = %s AND typ = 'B2B'",
        (data['email'],),
        fetch='one'
    ):
        return {"error": "B2B účet s týmto e-mailom už existuje."}

    salt, hsh = generate_password_hash(data['password'])
    params = (
        data['email'],
        data['nazov_firmy'],
        data['adresa'],
        data.get('adresa_dorucenia'),
        data['telefon'],
        hsh,
        salt,
        True,        # gdpr_suhlas
        'B2B',       # typ
        ''           # zakaznik_id pridelí admin pri schválení
    )
    
    db_connector.execute_query(
        """
        INSERT INTO b2b_zakaznici
        (email, nazov_firmy, adresa, adresa_dorucenia, telefon, heslo_hash, heslo_salt, gdpr_suhlas, typ, zakaznik_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        params,
        fetch='none'
    )
    
    try:
        notification_handler.send_registration_pending_email(data['email'], data['nazov_firmy'])
        notification_handler.send_new_registration_admin_alert(data)
    except Exception:
        logger.debug("--- VAROVANIE: Registrácia bola úspešná, ale e-maily sa nepodarilo odoslať. Skontrolujte .env nastavenia. ---")
        logger.debug(traceback.format_exc())

    return {"message": "Registrácia prebehla úspešne. Na Váš e-mail sme odoslali potvrdenie. Váš účet bude aktívny po schválení administrátorom."}

def submit_b2b_order(data: dict):
    """
    Spracuje finálne odoslanie B2B objednávky.
    OČAKÁVANÝ VSTUP (nový frontend):
      items: [{ produkt_id, quantity, price, dph?, unit?, item_note? }, ...]
    Dočasne podporíme aj legacy: ak príde `ean` a nie je `produkt_id`, pokúsime sa ho namapovať na produkt_id.
    """
    user_id = data.get('userId')
    items = data.get('items')
    note = data.get('note')
    delivery_date = data.get('deliveryDate')
    customer_email = data.get('customerEmail')
    customer_name = data.get('customerName')
    
    if not all([user_id, items, delivery_date, customer_email]):
        return {"error": "Chýbajú povinné údaje pre spracovanie objednávky."}

    # Legacy mapovanie EAN -> produkt_id (len ak treba)
    fixed_items = []
    for it in items:
        produkt_id = it.get('produkt_id')
        if not produkt_id and it.get('ean'):
            row = db_connector.execute_query("SELECT id FROM produkty WHERE ean = %s", (it['ean'],), fetch='one')
            if not row:
                return {"error": f"Neviem nájsť produkt podľa EAN {it['ean']}."}
            produkt_id = row['id']
        if not produkt_id:
            return {"error": "Položka objednávky nemá produkt_id."}
        fixed_items.append({
            "produkt_id": produkt_id,
            "quantity": safe_get_float(it['quantity']),
            "price": safe_get_float(it['price']),
            "dph": safe_get_float(it.get('dph', 0)),
            "unit": it.get('unit'),            # voliteľné, na zobrazenie
            "item_note": it.get('item_note')   # voliteľné
        })
    items = fixed_items

    customer_info = db_connector.execute_query(
        "SELECT nazov_firmy, zakaznik_id, adresa FROM b2b_zakaznici WHERE id = %s",
        (user_id,), fetch='one'
    ) or {}

    final_customer_name = customer_name or customer_info.get('nazov_firmy')
    if not final_customer_name:
        return {"error": "Nepodarilo sa načítať meno zákazníka."}

    total_price_net = sum(i['price'] * i['quantity'] for i in items)
    total_price_vat = sum(i['price'] * (1 + i.get('dph', 0)/100.0) * i['quantity'] for i in items)
    order_number = f"B2B-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO b2b_objednavky
            (zakaznik_id, cislo_objednavky, pozadovany_datum_dodania, poznamka, celkova_suma_s_dph, celkova_suma_bez_dph)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, order_number, delivery_date, note, total_price_vat, total_price_net)
        )
        order_id = cursor.lastrowid
        
        items_to_insert = [
            (order_id, i['produkt_id'], i['quantity'], i['price'])
            for i in items
        ]
        cursor.executemany(
            """
            INSERT INTO b2b_objednavky_polozky
            (objednavka_id, produkt_id, mnozstvo, cena)
            VALUES (%s, %s, %s, %s)
            """,
            items_to_insert
        )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        logger.debug("!!! KRITICKÁ CHYBA pri ukladaní objednávky do DB !!!")
        logger.debug(traceback.format_exc())
        return {"error": "Objednávku sa nepodarilo uložiť do databázy."}
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

    # Podklady pre PDF/CSV (použijeme produkt_id a dotiahneme názvy pre dokumenty)
    enriched_items = []
    for it in items:
        prod = db_connector.execute_query(
            "SELECT nazov, jednotka, dph FROM produkty WHERE id = %s",
            (it['produkt_id'],), fetch='one'
        ) or {}
        enriched_items.append({
            "produkt_id": it["produkt_id"],
            "ean": None,  # už nepoužívame, necháme None kvôli spätnému súladu
            "name": prod.get("nazov"),
            "unit": prod.get("jednotka") or it.get("unit") or "",
            "quantity": it["quantity"],
            "price": it["price"],
            "dph": safe_get_float(prod.get("dph") or it.get("dph") or 0),
            "item_note": it.get("item_note")
        })

    order_data_for_docs = {
        'order_number': order_number,
        'deliveryDate': delivery_date,
        'note': note,
        'customerName': final_customer_name,
        'userId': user_id,
        'customerEmail': customer_email,
        'items': enriched_items,
        'totalNet': total_price_net,
        'totalVat': total_price_vat,
        'order_date': datetime.now().strftime('%d.%m.%Y'),
        'customerLoginId': customer_info.get('zakaznik_id', 'N/A'),
        'customerAddress': customer_info.get('adresa', 'Neuvedená'),
        'customerIco': 'Neuvedené',
        'customerDic': 'Neuvedené',
        'customerIcDph': 'Neuvedené'
    }

    try:
        pdf_content, csv_content = pdf_generator.create_order_files(order_data_for_docs)
    except Exception:
        logger.debug(f"--- VAROVANIE: Objednávka {order_number} bola uložená, ale dokumenty sa nepodarilo vygenerovať. E-maily nemusia byť odoslané. ---")
        logger.debug(traceback.format_exc())
        return {
            "status": "success",
            "message": f"Objednávka {order_number} bola prijatá, ale pri generovaní dokumentov nastala chyba."
        }
    
    return {
        "status": "success",
        "message": f"Vaša objednávka {order_number} bola úspešne prijatá.",
        "order_data": order_data_for_docs,
        "pdf_attachment": pdf_content,
        "csv_attachment": csv_content
    }

# =================================================================
# === OBNOVA HESLA ===
# =================================================================

def request_password_reset(data: dict):
    email = data.get('email')
    if not email:
        return {"error": "E-mail je povinný údaj."}

    user = db_connector.execute_query(
        "SELECT id FROM b2b_zakaznici WHERE email = %s",
        (email,), fetch='one'
    )
    # Bezpečnostne neurčujeme existenciu účtu
    if not user:
        return {"message": "Ak účet s týmto e-mailom existuje, odkaz na obnovu hesla bol odoslaný."}

    token = secrets.token_urlsafe(32)
    token_expiry = datetime.now() + timedelta(minutes=15)
    db_connector.execute_query(
        "UPDATE b2b_zakaznici SET reset_token = %s, reset_token_expiry = %s WHERE id = %s",
        (token, token_expiry, user['id']), fetch='none'
    )
    reset_link = f"http://127.0.0.1:5000/b2b?action=resetPassword&token={token}"
    
    try:
        notification_handler.send_password_reset_email(email, reset_link)
    except Exception:
        logger.debug("--- VAROVANIE: Žiadosť o reset hesla bola zaznamenaná, ale e-mail sa nepodarilo odoslať. ---")
        logger.debug(traceback.format_exc())

    return {"message": "Ak účet s týmto e-mailom existuje, odkaz na obnovu hesla bol odoslaný."}

def perform_password_reset(data: dict):
    token, new_password = data.get('token'), data.get('password')
    if not token or not new_password:
        return {"error": "Token a nové heslo sú povinné."}

    user = db_connector.execute_query(
        "SELECT id, reset_token_expiry FROM b2b_zakaznici WHERE reset_token = %s",
        (token,), fetch='one'
    )
    if not user or user['reset_token_expiry'] < datetime.now():
        return {"error": "Odkaz na obnovu hesla je neplatný alebo jeho platnosť vypršala."}

    salt, hsh = generate_password_hash(new_password)
    db_connector.execute_query(
        """
        UPDATE b2b_zakaznici
        SET heslo_hash = %s, heslo_salt = %s, reset_token = NULL, reset_token_expiry = NULL
        WHERE id = %s
        """,
        (hsh, salt, user['id']),
        fetch='none'
    )
    return {"message": "Heslo bolo úspešne zmenené. Môžete sa prihlásiť."}

# =================================================================
# === ADMINISTRÁCIA B2B (pre interný systém) ===
# =================================================================

def get_pending_b2b_registrations():
    return db_connector.execute_query(
        """
        SELECT id, nazov_firmy, adresa, adresa_dorucenia, email, telefon, datum_registracie
        FROM b2b_zakaznici
        WHERE je_schvaleny = 0 AND typ = 'B2B'
        ORDER BY datum_registracie DESC
        """
    )

def approve_b2b_registration(data: dict):
    reg_id, customer_id = data.get('id'), data.get('customerId')
    if not reg_id or not customer_id:
        return {"error": "Chýba ID registrácie alebo ID odberateľa."}

    if db_connector.execute_query(
        "SELECT id FROM b2b_zakaznici WHERE zakaznik_id = %s",
        (customer_id,), fetch='one'
    ):
        return {"error": f"Zákaznícke číslo '{customer_id}' už je pridelené."}

    db_connector.execute_query(
        "UPDATE b2b_zakaznici SET je_schvaleny = 1, zakaznik_id = %s WHERE id = %s",
        (customer_id, reg_id), fetch='none'
    )

    customer_info = db_connector.execute_query(
        "SELECT email, nazov_firmy FROM b2b_zakaznici WHERE id = %s",
        (reg_id,), fetch='one'
    )
    if customer_info:
        try:
            notification_handler.send_approval_email(
                customer_info['email'],
                customer_info['nazov_firmy'],
                customer_id
            )
        except Exception:
            logger.debug(f"--- VAROVANIE: Registrácia pre {customer_info['nazov_firmy']} bola schválená, ale e-mail sa nepodarilo odoslať. ---")
            logger.debug(traceback.format_exc())

    return {"message": "Registrácia bola schválená a notifikácia odoslaná."}

def reject_b2b_registration(data: dict):
    rows_deleted = db_connector.execute_query(
        "DELETE FROM b2b_zakaznici WHERE id = %s AND je_schvaleny = 0",
        (data.get('id'),), fetch='none'
    )
    return {"message": "Registrácia bola odmietnutá."} if rows_deleted > 0 else {"error": "Registráciu sa nepodarilo nájsť."}

def get_customers_and_pricelists():
    customers_q = """
        SELECT z.id, z.zakaznik_id, z.nazov_firmy, z.email, z.telefon,
               z.adresa, z.adresa_dorucenia, GROUP_CONCAT(zc.cennik_id) AS cennik_ids
        FROM b2b_zakaznici z
        LEFT JOIN b2b_zakaznik_cennik zc ON z.id = zc.zakaznik_id
        WHERE z.je_admin = 0 AND z.typ = 'B2B'
        GROUP BY z.id
    """
    pricelists_q = "SELECT id, nazov_cennika FROM b2b_cenniky ORDER BY nazov_cennika"
    return {
        "customers": db_connector.execute_query(customers_q),
        "pricelists": db_connector.execute_query(pricelists_q)
    }

def update_customer_details(data: dict):
    customer_id = data.get('id')
    name = data.get('nazov_firmy')
    email = data.get('email')
    phone = data.get('telefon')
    pricelist_ids = data.get('pricelist_ids', [])
    address = data.get('adresa')
    delivery_address = data.get('adresa_dorucenia')
    
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE b2b_zakaznici
            SET nazov_firmy = %s, email = %s, telefon = %s, adresa = %s, adresa_dorucenia = %s
            WHERE id = %s
            """,
            (name, email, phone, address, delivery_address, customer_id)
        )
        cursor.execute("DELETE FROM b2b_zakaznik_cennik WHERE zakaznik_id = %s", (customer_id,))
        if pricelist_ids:
            new_assignments = [(customer_id, pid) for pid in pricelist_ids]
            cursor.executemany(
                "INSERT INTO b2b_zakaznik_cennik (zakaznik_id, cennik_id) VALUES (%s, %s)",
                new_assignments
            )
        conn.commit()
        return {"message": "Údaje zákazníka boli aktualizované."}
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

def get_pricelists_and_products():
    """Pre administráciu: cenníky a produkty (prepísané na nový model)."""
    pricelists = db_connector.execute_query("SELECT id, nazov_cennika FROM b2b_cenniky ORDER BY nazov_cennika")
    products = db_connector.execute_query(
        """
        SELECT 
            p.id AS produkt_id,
            p.nazov AS name,
            p.kategoria AS predajna_kategoria,
            p.dph,
            p.jednotka
        FROM produkty p
        WHERE p.typ IN ('vyrobok', 'externy')
        ORDER BY p.kategoria, p.nazov
        """
    )
    products_by_category = {}
    for p in products:
        category = p.get('predajna_kategoria') or 'Nezaradené'
        products_by_category.setdefault(category, []).append(p)
    return {"pricelists": pricelists, "productsByCategory": products_by_category}

def create_pricelist(data: dict):
    name = data.get('name')
    if not name:
        return {"error": "Názov cenníka je povinný."}
    try:
        new_id = db_connector.execute_query(
            "INSERT INTO b2b_cenniky (nazov_cennika) VALUES (%s)",
            (name,), fetch='lastrowid'
        )
        return {"message": f"Cenník '{name}' bol vytvorený.", "newPricelist": {"id": new_id, "nazov_cennika": name}}
    except Exception as e:
        if 'UNIQUE constraint' in str(e) or 'Duplicate entry' in str(e):
            return {"error": "Cenník s týmto názvom už existuje."}
        raise e

def get_pricelist_details(pricelist_id: int):
    """Detail cenníka: položky s produktmi (už na produkt_id)."""
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                pol.produkt_id,
                p.nazov,
                p.ean,
                pol.cena
            FROM b2b_cennik_polozky pol
            JOIN produkty p ON pol.produkt_id = p.id
            WHERE pol.cennik_id = %s
            ORDER BY p.nazov
        """, (pricelist_id,))
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        raise e
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

def update_pricelist(data: dict):
    pricelist_id = data.get('id')
    items = data.get('items', [])
    conn = db_connector.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM b2b_cennik_polozky WHERE cennik_id = %s", (pricelist_id,))
        if items:
            items_to_insert = [(pricelist_id, i['produkt_id'], i['price']) for i in items if i.get('price') is not None]
            if items_to_insert:
                cursor.executemany(
                    "INSERT INTO b2b_cennik_polozky (cennik_id, produkt_id, cena) VALUES (%s, %s, %s)",
                    items_to_insert
                )
        conn.commit()
        return {"message": "Cenník bol aktualizovaný."}
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn and getattr(conn, "is_connected", lambda: False)():
            conn.close()

def get_announcement():
    result = db_connector.execute_query("SELECT hodnota FROM b2b_nastavenia WHERE kluc = 'oznam'", fetch='one')
    return {"announcement": result['hodnota'] if result else ""}

def save_announcement(data: dict):
    announcement_text = data.get('announcement', '')
    query = """
        INSERT INTO b2b_nastavenia (kluc, hodnota)
        VALUES ('oznam', %s)
        ON DUPLICATE KEY UPDATE hodnota = VALUES(hodnota)
    """
    db_connector.execute_query(query, (announcement_text,), fetch='none')
    return {"message": "Oznam bol úspešne aktualizovaný."}

# =================================================================
# === HISTÓRIA OBJEDNÁVOK (frontend B2B) + PDF EXPORT ===
# =================================================================

def get_order_details(order_id: int):
    """Detail B2B objednávky vrátane položiek (prepísané na produkt_id)."""

    # Hlavička objednávky
    order = db_connector.execute_query(
        """
        SELECT 
            o.id,
            o.cislo_objednavky,
            o.pozadovany_datum_dodania,
            o.poznamka,
            o.datum_objednavky,
            COALESCE(o.stav, 'Prijatá') AS stav,
            z.nazov_firmy AS customer_name
        FROM b2b_objednavky o
        LEFT JOIN b2b_zakaznici z ON o.zakaznik_id = z.id
        WHERE o.id = %s
        """,
        (order_id,),
        fetch="one"
    )

    if not order:
        return None

    # Položky objednávky (produkt_id)
    items = db_connector.execute_query(
        """
        SELECT 
            pol.id,
            pol.produkt_id,
            p.nazov,
            p.jednotka,
            pol.mnozstvo,
            pol.cena,
            (pol.mnozstvo * pol.cena) AS total
        FROM b2b_objednavky_polozky pol
        JOIN produkty p ON pol.produkt_id = p.id
        WHERE pol.objednavka_id = %s
        """,
        (order_id,)
    )

    order["items"] = items
    return order

def get_order_history(user_id: int):
    """História objednávok daného B2B používateľa – prepísané na produkt_id."""
    if not user_id:
        return []

    # Hlavičky objednávok
    orders = db_connector.execute_query(
        """
        SELECT
            o.id,
            o.cislo_objednavky,
            o.pozadovany_datum_dodania,
            o.poznamka,
            o.datum_objednavky,
            o.celkova_suma_s_dph,
            o.celkova_suma_bez_dph,
            COALESCE(o.stav, 'Prijatá') AS stav
        FROM b2b_objednavky o
        WHERE o.zakaznik_id = %s
        ORDER BY o.datum_objednavky DESC, o.id DESC
        """,
        (user_id,)
    )

    # Normalizácia dátumov a súm + položky
    for o in orders:
        if isinstance(o.get('pozadovany_datum_dodania'), (datetime,)):
            o['pozadovany_datum_dodania'] = o['pozadovany_datum_dodania'].strftime('%Y-%m-%d')
        if isinstance(o.get('datum_objednavky'), (datetime,)):
            o['datum_objednavky'] = o['datum_objednavky'].strftime('%d.%m.%Y %H:%M')
        o['celkova_suma_s_dph'] = safe_get_float(o.get('celkova_suma_s_dph') or 0)
        o['celkova_suma_bez_dph'] = safe_get_float(o.get('celkova_suma_bez_dph') or 0)

        # Položky objednávky
        items = db_connector.execute_query(
            """
            SELECT 
                pol.id,
                pol.produkt_id,
                p.nazov,
                p.jednotka,
                pol.mnozstvo,
                pol.cena,
                (pol.mnozstvo * pol.cena) AS total
            FROM b2b_objednavky_polozky pol
            JOIN produkty p ON pol.produkt_id = p.id
            WHERE pol.objednavka_id = %s
            """,
            (o['id'],)
        )
        o['items'] = items

    return orders

def get_b2b_order_history_api(data: dict):
    """Handler pre /api/b2b/get-order-history – očakáva data['user_id'] (POZOR: user_id, nie userId)."""
    user_id = data.get('user_id')
    if not user_id:
        return {"error": "Chýba user_id."}
    return {"orders": get_order_history(user_id)}

def generate_order_history_pdf(user_id: int):
    """
    Vytvorí PDF so sumárom histórie objednávok daného B2B používateľa.
    Vráti (pdf_bytes, filename).
    """
    orders = get_order_history(user_id)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 20*mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, y, "História objednávok")
    y -= 8*mm
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, y, f"Dátum exportu: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    y -= 12*mm

    if not orders:
        c.drawString(20*mm, y, "Zatiaľ nemáte žiadne objednávky.")
        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer.getvalue(), "historia_objednavok.pdf"

    for o in orders:
        # zalomenie stránky
        if y < 30*mm:
            c.showPage()
            y = height - 20*mm

        cislo = o.get('cislo_objednavky', '')
        datum = o.get('datum_objednavky', '')
        stav = o.get('stav', '')
        suma = o.get('celkova_suma_s_dph', 0)
        poz = o.get('poznamka', '')
        dodanie = o.get('pozadovany_datum_dodania', '')

        c.setFont("Helvetica-Bold", 11)
        c.drawString(20*mm, y, f"Objednávka: {cislo}")
        y -= 6*mm
        c.setFont("Helvetica", 10)
        c.drawString(20*mm, y, f"Dátum: {datum}    Stav: {stav}    Dodanie: {dodanie}    Suma: {suma:.2f} €")
        y -= 6*mm

        if poz:
            c.setFont("Helvetica-Oblique", 9)
            maxw = width - 40*mm
            words = str(poz).split()
            line = ""
            for w in words:
                test = (line + " " + w).strip()
                if c.stringWidth(test, "Helvetica-Oblique", 9) > maxw:
                    c.drawString(20*mm, y, line)
                    y -= 5*mm
                    line = w
                else:
                    line = test
            if line:
                c.drawString(20*mm, y, line)
                y -= 5*mm

        # oddelovač
        c.setLineWidth(0.3)
        c.line(20*mm, y, width-20*mm, y)
        y -= 8*mm

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue(), "historia_objednavok.pdf"

# =================================================================
# === ADMIN: PREHĽAD A DETAIL OBJEDNÁVOK ===
# =================================================================

def get_all_b2b_orders(startDate=None, endDate=None, **kwargs):
    """Získa všetky B2B objednávky pre administrátorský prehľad, s možnosťou filtrovania."""
    start_date = startDate or '1970-01-01'
    end_date = endDate or '2999-12-31'

    query = """
        SELECT o.*, z.nazov_firmy 
        FROM b2b_objednavky o
        JOIN b2b_zakaznici z ON o.zakaznik_id = z.id
        WHERE DATE(o.pozadovany_datum_dodania) BETWEEN %s AND %s
        ORDER BY o.pozadovany_datum_dodania DESC, o.datum_objednavky DESC
    """
    orders = db_connector.execute_query(query, (start_date, end_date))
    return {"orders": orders}

def get_b2b_order_details(id: int, **kwargs):
    """Získa detail jednej konkrétnej objednávky pre zobrazenie v administrácii (prepísané na produkt_id)."""
    order_id = id
    if not order_id:
        return {"error": "Chýba ID objednávky."}
    
    order_q = """
        SELECT o.*, z.nazov_firmy, z.zakaznik_id as customerLoginId, z.adresa as customerAddress
        FROM b2b_objednavky o
        JOIN b2b_zakaznici z ON o.zakaznik_id = z.id
        WHERE o.id = %s
    """
    order = db_connector.execute_query(order_q, (order_id,), fetch='one')
    
    if not order:
        return {"error": "Objednávka nebola nájdená."}

    items_q = """
        SELECT 
            pol.produkt_id,
            p.nazov,
            p.jednotka,
            pol.mnozstvo,
            pol.cena
        FROM b2b_objednavky_polozky pol
        JOIN produkty p ON pol.produkt_id = p.id
        WHERE pol.objednavka_id = %s
        ORDER BY p.nazov
    """
    items = db_connector.execute_query(items_q, (order_id,))
    
    order_data = {
        'id': order['id'],
        'order_number': order['cislo_objednavky'],
        'deliveryDate': order['pozadovany_datum_dodania'].strftime('%Y-%m-%d') if isinstance(order['pozadovany_datum_dodania'], datetime) else str(order['pozadovany_datum_dodania']),
        'note': order['poznamka'],
        'customerName': order['nazov_firmy'],
        'customerLoginId': order['customerLoginId'],
        'customerAddress': order['customerAddress'],
        'order_date': order['datum_objednavky'].strftime('%d.%m.%Y') if isinstance(order['datum_objednavky'], datetime) else str(order['datum_objednavky']),
        'totalNet': safe_get_float(order.get('celkova_suma_bez_dph') or 0),
        'totalVat': safe_get_float(order.get('celkova_suma_s_dph') or 0),
        'items': [
            {
                'produkt_id': i['produkt_id'],
                'name': i['nazov'],
                'unit': i['jednotka'],
                'quantity': safe_get_float(i['mnozstvo']),
                'price': safe_get_float(i['cena']),
                'total': safe_get_float(i['mnozstvo']) * safe_get_float(i['cena'])
            } for i in items
        ]
    }
    return {"order": order_data}
