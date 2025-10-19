from validators import validate_required_fields, safe_get_float, safe_get_int
from logger import logger
import hashlib
import os
from flask import session, jsonify, url_for
import db_connector

# =================================================================
# === BEZPEČNOSTNÉ FUNKCIE PRE PRÁCU S HESLAMI (INTERNÍ POUŽÍVATELIA) ===
# =================================================================

def generate_password_hash(password):
    """
    Vygeneruje bezpečnú "soľ" (salt) a hash pre zadané heslo.
    """
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        250000
    )
    return salt.hex(), key.hex()

def verify_password(password, salt_hex, hash_hex):
    """
    Overí, či sa zadané heslo zhoduje s uloženou soľou a hashom.
    """
    try:
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(hash_hex)
        new_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            250000
        )
        return new_key == stored_key
    except (ValueError, TypeError):
        return False

# =================================================================
# === FUNKCIE PRE SESSION MANAGEMENT INTERNÝCH POUŽÍVATEĽOV ===
# =================================================================

def internal_login(**kwargs):
    """Spracuje prihlásenie interného používateľa."""
    username = kwargs.get('username')
    password = kwargs.get('password')
    user = db_connector.execute_query(
       "SELECT * FROM internal_users WHERE (username = %s OR email = %s) AND is_active = 1",
       (username, username),
      fetch='one'
  )
    
    if user and verify_password(password, user['password_salt'], user['password_hash']):
        session.permanent = True
        session['user'] = { 'id': user['id'], 'username': user['username'], 'role': user['role'], 'full_name': user['full_name'] }
        return {'message': 'Prihlásenie úspešné.', 'user': session['user']}
    
    return {'error': 'Nesprávne meno alebo heslo.'}

def internal_logout(**kwargs):
    """Spracuje odhlásenie a vráti URL na presmerovanie."""
    role = session.pop('user', {}).get('role', 'vyroba')
    redirect_url = url_for('page_vyroba')
    if role == 'expedicia': redirect_url = url_for('page_expedicia')
    if role == 'kancelaria': redirect_url = url_for('page_kancelaria')
    return {'message': 'Boli ste úspešne odhlásený.', 'redirect_url': redirect_url}

def check_session(**kwargs):
    """Overí, či existuje aktívna session."""
    return {'loggedIn': 'user' in session, 'user': session.get('user')}

