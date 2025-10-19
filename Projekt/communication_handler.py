# communication_handler.py — Komunikácia (e‑maily) PRO+
# Funkcie: IMAP sync (text + HTML + prílohy), SMTP send (HTML), list s filtrami,
# delete/spam, počty neprečítaných, probe endpointy, podpisy a preferencie editora.

import os, re, ssl, imaplib, smtplib, email
from datetime import datetime
from flask import request
from email.utils import parseaddr, formataddr
from email.header import decode_header, make_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
import mimetypes
from flask import send_file

import db_connector

ATTACH_DIR = os.environ.get('COMM_ATTACH_DIR', 'uploads/attachments')

# ----------------------- DB helpers / bootstrap -------------------------------
def _ensure_tables():
    db_connector.execute_query("""
        CREATE TABLE IF NOT EXISTS comm_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            uid VARCHAR(128) UNIQUE,
            direction ENUM('in','out') NOT NULL,
            sender_email VARCHAR(255),
            sender_name  VARCHAR(255),
            to_email     TEXT,
            subject      TEXT,
            body_preview TEXT,
            body_html    MEDIUMTEXT,
            date DATETIME,
            has_attachments TINYINT DEFAULT 0,
            customer_type ENUM('B2B','B2C','LEAD','UNKNOWN') DEFAULT 'UNKNOWN',
            customer_id INT NULL,
            is_read TINYINT DEFAULT 0,
            is_deleted TINYINT DEFAULT 0,
            is_spam TINYINT DEFAULT 0,
            message_id VARCHAR(255),
            raw_folder VARCHAR(128),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch='none')
    db_connector.execute_query("""
        CREATE TABLE IF NOT EXISTS comm_attachments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            message_uid VARCHAR(128),
            filename TEXT,
            path TEXT,
            size INT
        )
    """, fetch='none')
    db_connector.execute_query("""
        CREATE TABLE IF NOT EXISTS comm_signatures (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_email VARCHAR(255) NOT NULL,
            display_name VARCHAR(255),
            signature_html MEDIUMTEXT,
            is_default TINYINT DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch='none')
    db_connector.execute_query("""
        CREATE TABLE IF NOT EXISTS comm_prefs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_email VARCHAR(255) NOT NULL,
            font_family VARCHAR(128) DEFAULT 'Inter, Arial, sans-serif',
            font_size VARCHAR(8) DEFAULT '14px',
            font_color VARCHAR(16) DEFAULT '#111111',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """, fetch='none')

    # Tichý auto-upgrade bez duplicitných ALTER hlášok
    _add_column_if_missing('comm_messages', 'body_html',  'MEDIUMTEXT')
    _add_column_if_missing('comm_messages', 'is_deleted', 'TINYINT DEFAULT 0')
    _add_column_if_missing('comm_messages', 'is_spam',    'TINYINT DEFAULT 0')
    _add_column_if_missing('comm_messages', 'message_id', 'VARCHAR(255)')


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
def _get_column_info(table: str, column: str):
    return db_connector.execute_query(
        """
        SELECT DATA_TYPE AS data_type, CHARACTER_MAXIMUM_LENGTH AS char_len
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
        LIMIT 1
        """,
        (table, column), 'one'
    ) or {}

def _ensure_signature_schema():
    """Tichý upgrade schémy podpisov (šírka display_name a typ signature_html)."""
    info = _get_column_info('comm_signatures', 'display_name')
    if not info or info.get('data_type') != 'varchar' or (info.get('char_len') or 0) < 255:
        db_connector.execute_query(
            "ALTER TABLE comm_signatures "
            "MODIFY COLUMN display_name VARCHAR(255) "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
            fetch='none'
        )
    info2 = _get_column_info('comm_signatures', 'signature_html')
    if not info2 or info2.get('data_type') not in ('mediumtext', 'longtext'):
        db_connector.execute_query(
            "ALTER TABLE comm_signatures "
            "MODIFY COLUMN signature_html MEDIUMTEXT "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
            fetch='none'
        )


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    """Add column if it doesn't exist (avoid duplicate ALTER errors)."""
    try:
        exists = _has_column(table, column)
    except Exception:
        exists = True
    if not exists:
        db_connector.execute_query(f"ALTER TABLE {table} ADD COLUMN {ddl}", fetch='none')


def _decode(s):
    if not s:
        return ''
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s


def _sanitize_html(html: str) -> str:
    if not html:
        return ''
    html = re.sub(r'(?is)<script.*?>.*?</script>', '', html)
    html = re.sub(r'(?is)<style.*?>.*?</style>', '', html)
    html = re.sub(r'\son\w+="[^"]*"', '', html)
    html = re.sub(r"\son\w+='[^']*'", '', html)
    html = re.sub(r'(?i)href\s*=\s*["\']\s*javascript:[^"\']*["\']', 'href="#"', html)
    html = re.sub(r'(?i)src\s*=\s*["\']\s*javascript:[^"\']*["\']', '', html)
    return html


def _textify(html: str) -> str:
    if not html:
        return ''
    txt = re.sub(r'(?is)<(br|/p|/div)>', '\n', html)
    txt = re.sub(r'(?is)<[^>]+>', '', txt)
    return re.sub(r'\n{3,}', '\n\n', txt).strip()


def _hash_uid(folder, uid, from_addr, subject, date_str):
    import hashlib
    base = f"{folder}|{uid}|{from_addr}|{subject}|{date_str}"
    return hashlib.sha256(base.encode('utf-8')).hexdigest()

# ----------------------- SMTP / IMAP connect ---------------------------------
def _smtp_open():
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    pwd  = os.environ.get('SMTP_PASS')
    use_ssl = os.environ.get('SMTP_SSL', '0') == '1' or port == 465
    use_tls = (os.environ.get('SMTP_TLS', '1') != '0') if not use_ssl else False
    timeout = int(os.environ.get('SMTP_TIMEOUT', '25'))
    from_addr = os.environ.get('SMTP_FROM', user or 'noreply@example.com')
    from_name = os.environ.get('SMTP_FROM_NAME', 'ERP MIK')
    if not host or not port:
        raise RuntimeError("Chýba SMTP_HOST/SMTP_PORT v .env.")
    if use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
        server.ehlo()
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
        server.ehlo()
        if use_tls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
    if os.environ.get('SMTP_DEBUG', '0') == '1':
        server.set_debuglevel(1)
    return server, user, pwd, from_addr, from_name


def _imap_open():
    host = os.environ.get('IMAP_HOST')
    user = os.environ.get('IMAP_USER')
    pwd  = os.environ.get('IMAP_PASS')
    port = int(os.environ.get('IMAP_PORT', '993'))
    use_ssl = os.environ.get('IMAP_SSL', '1') == '1' or port == 993
    use_tls = os.environ.get('IMAP_TLS', '0') == '1'
    if not (host and user and pwd):
        raise RuntimeError("Chýba IMAP_HOST/IMAP_USER/IMAP_PASS v .env.")
    try:
        if use_ssl:
            imap = imaplib.IMAP4_SSL(host, port)
        else:
            imap = imaplib.IMAP4(host, port)
            if use_tls and hasattr(imap, 'starttls'):
                imap.starttls(ssl_context=ssl.create_default_context())
    except Exception as e:
        raise RuntimeError(f"IMAP pripojenie zlyhalo: {e}")
    try:
        imap.login(user, pwd)
    except Exception as e:
        try:
            imap.logout()
        except Exception:
            pass
        raise RuntimeError(f"IMAP prihlásenie zlyhalo: {e}")
    return imap

# ----------------------- Kategorizácia odosielateľa ---------------------------
def _classify_customer(email_addr: str):
    try:
        if not email_addr:
            return ('UNKNOWN', None)
        e = email_addr.strip().lower()
        if _has_table('b2b_zakaznici') and _has_column('b2b_zakaznici', 'email'):
            if _has_column('b2b_zakaznici', 'typ'):
                row = db_connector.execute_query("SELECT id, typ FROM b2b_zakaznici WHERE LOWER(email)=%s LIMIT 1", (e,), 'one')
                if row:
                    return (('B2C', row['id']) if (row.get('typ') or '').upper() == 'B2C' else ('B2B', row['id']))
            else:
                row = db_connector.execute_query("SELECT id FROM b2b_zakaznici WHERE LOWER(email)=%s LIMIT 1", (e,), 'one')
                if row:
                    return ('B2B', row['id'])
        for cand in ('b2c_zakaznici', 'b2c_users', 'b2c_customers'):
            if _has_table(cand):
                col = 'email' if _has_column(cand, 'email') else ('mail' if _has_column(cand, 'mail') else None)
                if not col:
                    continue
                row = db_connector.execute_query(f"SELECT id FROM {cand} WHERE LOWER({col})=%s LIMIT 1", (e,), 'one')
                if row:
                    return ('B2C', row['id'])
        return ('LEAD', None)
    except Exception:
        return ('LEAD', None)

# ----------------------- IMAP: SYNC -------------------------------------------
def comm_sync_inbox(limit: int = 200, folder: str = None):
    _ensure_tables()
    try:
        imap = _imap_open()
    except Exception as e:
        return {"error": str(e)}
    folder = folder or os.environ.get('IMAP_FOLDER', 'INBOX')
    try:
        imap.select(folder)
        typ, data = imap.search(None, 'ALL')
        if typ != 'OK':
            try:
                imap.logout()
            except Exception:
                pass
            return {"error": "IMAP search failed."}
        ids = data[0].split()
        ids = ids[-limit:] if limit and len(ids) > limit else ids
        imported = 0
        os.makedirs(ATTACH_DIR, exist_ok=True)

        for msg_id in ids:
            typ, msg_data = imap.fetch(msg_id, '(RFC822)')
            if typ != 'OK' or not msg_data:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _decode(msg.get('Subject', ''))
            from_name, from_addr = parseaddr(msg.get('From', ''))
            to_addrs = msg.get('To', '')
            date_hdr = msg.get('Date', '')
            try:
                date = email.utils.parsedate_to_datetime(date_hdr)
            except Exception:
                date = datetime.utcnow()
            message_id = msg.get('Message-ID') or msg.get('Message-Id') or ''
            uid = _hash_uid(folder, msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id), from_addr, subject, str(date))
            if db_connector.execute_query("SELECT id FROM comm_messages WHERE uid=%s", (uid,), 'one'):
                continue

            body_text, body_html, has_att = "", "", 0
            if msg.is_multipart():
                for part in msg.walk():
                    cdisp = part.get('Content-Disposition', '') or ''
                    ctype = part.get_content_type()
                    if ctype == 'text/plain' and 'attachment' not in cdisp.lower():
                        try:
                            body_text = (part.get_payload(decode=True) or b'').decode(part.get_content_charset() or 'utf-8', errors='ignore')
                        except Exception:
                            pass
                    elif ctype == 'text/html' and 'attachment' not in cdisp.lower():
                        try:
                            body_html = _sanitize_html((part.get_payload(decode=True) or b'').decode(part.get_content_charset() or 'utf-8', errors='ignore'))
                        except Exception:
                            pass
                    elif 'attachment' in cdisp.lower():
                        has_att = 1
                        fname = _decode(part.get_filename() or 'priloha')
                        payload = part.get_payload(decode=True) or b''
                        path = os.path.join(ATTACH_DIR, f"{uid}_{fname}")
                        try:
                            with open(path, 'wb') as f:
                                f.write(payload)
                            db_connector.execute_query(
                                "INSERT INTO comm_attachments (message_uid, filename, path, size) VALUES (%s,%s,%s,%s)",
                                (uid, fname, path, len(payload)), 'none'
                            )
                        except Exception:
                            pass
            else:
                try:
                    payload = (msg.get_payload(decode=True) or b'').decode(msg.get_content_charset() or 'utf-8', errors='ignore')
                    if msg.get_content_type() == 'text/html':
                        body_html = _sanitize_html(payload)
                    else:
                        body_text = payload
                except Exception:
                    pass

            ctype, cid = _classify_customer(from_addr)
            db_connector.execute_query(
                """INSERT INTO comm_messages
                   (uid, direction, sender_email, sender_name, to_email, subject, body_preview, body_html, date, has_attachments,
                    customer_type, customer_id, is_read, is_deleted, is_spam, message_id, raw_folder)
                   VALUES (%s,'in',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,0,%s,%s)""",
                (uid, from_addr, from_name, to_addrs, subject, (body_text or '')[:1000], (body_html or '')[:20000],
                 date, has_att, ctype, cid, message_id, folder),
                'none'
            )
            imported += 1
        try:
            imap.logout()
        except Exception:
            pass
        return {"imported": imported}
    except Exception as e:
        try:
            imap.logout()
        except Exception:
            pass
        return {"error": f"IMAP chyba: {e}"}

# ----------------------- Listing / detail -------------------------------------
def comm_list(filters: dict):
    _ensure_tables()
    ftype = (filters or {}).get('type', 'ALL').upper()
    where = "1=1"
    params = []
    if ftype == 'UNREAD':
        where += " AND is_read=0 AND is_deleted=0"
    elif ftype == 'SPAM':
        where += " AND is_spam=1 AND is_deleted=0"
    elif ftype == 'TRASH':
        where += " AND is_deleted=1"
    elif ftype in ('B2B', 'B2C', 'LEAD', 'UNKNOWN'):
        where += " AND customer_type=%s AND is_deleted=0"
        params.append(ftype)
    else:
        where += " AND is_deleted=0"

    rows = db_connector.execute_query(
        f"""SELECT id, uid, direction, sender_name, sender_email, to_email, subject, body_preview,
                    DATE_FORMAT(date,'%%d.%%m.%%Y %%H:%%i') AS date, has_attachments,
                    customer_type, customer_id, is_read, is_deleted, is_spam
             FROM comm_messages
             WHERE {where}
             ORDER BY date DESC
             LIMIT 1000""",
        tuple(params) if params else None
    ) or []

    for r in rows:
        r['subject'] = _decode(r.get('subject'))
        r['sender_name'] = _decode(r.get('sender_name'))
    return {"items": rows}

def comm_list_signatures(owner_email: str | None = None):
    _ensure_tables()
    owner = (owner_email or os.environ.get('SMTP_FROM') or '').strip().lower()
    rows = db_connector.execute_query(
        """
        SELECT id, display_name, signature_html, is_default, updated_at
        FROM comm_signatures
        WHERE owner_email=%s
        ORDER BY is_default DESC, updated_at DESC
        """, (owner,)
    ) or []
    return {"items": rows}

def comm_set_default_signature(id=None, owner_email: str | None = None):
    _ensure_tables()
    if not id:
        return {"error": "Missing id."}
    owner = (owner_email or os.environ.get('SMTP_FROM') or '').strip().lower()
    db_connector.execute_query("UPDATE comm_signatures SET is_default=0 WHERE owner_email=%s", (owner,), 'none')
    db_connector.execute_query("UPDATE comm_signatures SET is_default=1 WHERE id=%s AND owner_email=%s", (id, owner), 'none')
    return {"message": "Predvolený podpis nastavený."}

def comm_delete_signature(id=None, owner_email: str | None = None):
    _ensure_tables()
    if not id:
        return {"error": "Missing id."}
    owner = (owner_email or os.environ.get('SMTP_FROM') or '').strip().lower()
    db_connector.execute_query("DELETE FROM comm_signatures WHERE id=%s AND owner_email=%s", (id, owner), 'none')
    return {"message": "Podpis zmazaný."}

def comm_get(id: int):
    _ensure_tables()
    row = db_connector.execute_query("SELECT * FROM comm_messages WHERE id=%s", (id,), 'one')
    if not row:
        return {"error": "Správa neexistuje."}
    atts = db_connector.execute_query("SELECT id, filename, path, size FROM comm_attachments WHERE message_uid=%s", (row['uid'],)) or []
    return {"message": row, "attachments": atts}
def comm_get_attachment_stream(att_id: int):
    _ensure_tables()
    row = db_connector.execute_query(
        "SELECT filename, path FROM comm_attachments WHERE id=%s",
        (att_id,), 'one'
    )
    if not row:
        return {"error": "Príloha neexistuje."}

    path = row['path'] or ''
    filename = (row.get('filename') or os.path.basename(path) or 'attachment.bin')

    # ak je uložená relatívna cesta, skús ju nájsť pod ATTACH_DIR
    if not os.path.isabs(path) and not os.path.exists(path):
        candidate = os.path.join(ATTACH_DIR, path)
        if os.path.exists(candidate):
            path = candidate

    if not os.path.exists(path):
        return {"error": "Súbor sa nenašiel na serveri."}

    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return send_file(path, mimetype=mime, as_attachment=True, download_name=filename)


def comm_unread_count():
    _ensure_tables()
    row = db_connector.execute_query(
        "SELECT COUNT(*) AS c FROM comm_messages WHERE is_read=0 AND is_deleted=0 AND direction='in'",
        fetch='one'
    )
    return int(row['c']) if row else 0


def comm_mark_read(id: int, read: bool = True):
    _ensure_tables()
    db_connector.execute_query("UPDATE comm_messages SET is_read=%s WHERE id=%s", (1 if read else 0, id), 'none')
    return {"ok": True}

# ----------------------- Editor config / signatures / prefs -------------------
def comm_editor_config(owner_email: str | None = None):
    """
    Vráti:
      - signatures: zoznam podpisov {id, display_name, signature_html, is_default}
      - signature_html: HTML predvoleného (pre spätnú kompatibilitu)
      - prefs: preferencie editora (font, size, color)
      - owner_email: pre koho sa načítava
    """
    _ensure_tables()
    owner = (owner_email or os.environ.get('SMTP_FROM') or '').strip().lower()

    sigs = db_connector.execute_query(
        """
        SELECT id, display_name, signature_html, is_default, updated_at
        FROM comm_signatures
        WHERE owner_email=%s
        ORDER BY is_default DESC, updated_at DESC
        """,
        (owner,)
    ) or []

    default_html = ""
    if sigs:
        default = next((s for s in sigs if s.get('is_default')), None) or sigs[0]
        default_html = default.get('signature_html') or ""

    prefs = db_connector.execute_query(
        "SELECT font_family, font_size, font_color FROM comm_prefs WHERE owner_email=%s LIMIT 1",
        (owner,), 'one'
    ) or {"font_family": "Inter, Arial, sans-serif", "font_size": "14px", "font_color": "#111111"}

    return {"signatures": sigs, "signature_html": default_html, "prefs": prefs, "owner_email": owner}
def comm_save_signature(owner_email: str, display_name: str, signature_html: str, make_default: bool = True):
    _ensure_tables()
    owner = (owner_email or os.environ.get('SMTP_FROM') or '').strip().lower()
    if not owner:
        return {"error": "Owner email missing."}

    # fix: DB istota (255 znakov max) + sane defaulty
    dn = (display_name or '').strip()
    if len(dn) > 255:
        dn = dn[:255]
    sig_html = signature_html or ''

    if make_default:
        db_connector.execute_query("UPDATE comm_signatures SET is_default=0 WHERE owner_email=%s", (owner,), 'none')

    db_connector.execute_query(
        "INSERT INTO comm_signatures (owner_email, display_name, signature_html, is_default) VALUES (%s,%s,%s,%s)",
        (owner, dn, sig_html, 1 if make_default else 0),
        'none'
    )
    return {"message": "Podpis uložený."}


def comm_save_prefs(owner_email: str, font_family: str, font_size: str, font_color: str):
    _ensure_tables()
    owner = (owner_email or os.environ.get('SMTP_FROM') or '').strip().lower()
    if not owner:
        return {"error": "Owner email missing."}
    exists = db_connector.execute_query("SELECT id FROM comm_prefs WHERE owner_email=%s", (owner,), 'one')
    if exists:
        db_connector.execute_query(
            "UPDATE comm_prefs SET font_family=%s, font_size=%s, font_color=%s WHERE owner_email=%s",
            (font_family, font_size, font_color, owner),
            'none'
        )
    else:
        db_connector.execute_query(
            "INSERT INTO comm_prefs (owner_email, font_family, font_size, font_color) VALUES (%s,%s,%s,%s)",
            (owner, font_family, font_size, font_color),
            'none'
        )
    return {"message": "Preferencie uložené."}

# ----------------------- SMTP SEND (HTML podporované) -------------------------
def comm_send_mime():
    """
    multipart/form-data: to, cc, bcc, subject, body (plain), body_html (HTML), files[]
    HTML aj TEXT sa posielajú ako multipart/alternative, hlavičky idú v UTF-8 (Header),
    a odosielame BAJTY (msg_root.as_bytes()), takže nehrozí ASCII chyba na NBSP/diakritike.
    """
    _ensure_tables()

    to_addr  = (request.form.get('to')  or '').strip()
    cc_addr  = (request.form.get('cc')  or '').strip()
    bcc_addr = (request.form.get('bcc') or '').strip()
    subject  = (request.form.get('subject') or '').strip()
    body_txt = (request.form.get('body') or '').strip()
    body_htm = (request.form.get('body_html') or '').strip()

    if not (to_addr and subject and (body_txt or body_htm)):
        return {"error": "Chýba adresát, predmet alebo text."}

    try:
        server, user, pwd, from_addr, from_name = _smtp_open()
    except Exception as e:
        return {"error": f"SMTP konfigurácia/pripojenie zlyhalo: {e}"}

    # MIME kontajner
    msg_root = MIMEMultipart()
    # UTF-8 hlavičky (From meno a Subject)
    from_name_utf = str(Header(from_name or '', 'utf-8'))
    msg_root['From'] = formataddr((from_name_utf, from_addr))
    msg_root['To']   = to_addr
    if cc_addr:
        msg_root['Cc'] = cc_addr
    msg_root['Subject'] = Header(subject or '', 'utf-8')

    # alternative: plain + html
    alt = MIMEMultipart('alternative')
    if body_txt:
        alt.attach(MIMEText(body_txt, 'plain', 'utf-8'))
    if body_htm:
        alt.attach(MIMEText(body_htm, 'html', 'utf-8'))
    msg_root.attach(alt)

    # prílohy
    files = request.files.getlist('files')
    uid = _hash_uid('OUT', datetime.utcnow().isoformat(), from_addr, subject, '')
    saved_paths = []
    os.makedirs(ATTACH_DIR, exist_ok=True)
    for f in files or []:
        if not f.filename:
            continue
        path = os.path.join(ATTACH_DIR, f"{uid}_{f.filename}")
        f.save(path)
        saved_paths.append(path)

        part = MIMEBase('application', 'octet-stream')
        with open(path, 'rb') as fp:
            part.set_payload(fp.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{f.filename}"')
        msg_root.attach(part)

    # odoslanie — POZOR: posielame BAJTY, nie string
    try:
        recipients = [a.strip() for a in (to_addr.split(',') + cc_addr.split(',') + bcc_addr.split(',')) if a.strip()]
        if user and pwd:
            server.login(user, pwd)
        server.sendmail(from_addr, recipients, msg_root.as_bytes())
    except Exception as e:
        try:
            server.quit()
        except Exception:
            pass
        return {"error": f"SMTP chyba pri odosielaní: {e}"}
    try:
        server.quit()
    except Exception:
        pass

    # uloženie OUTBOX záznamu
    store_html = body_htm or None
    # ak neprišiel text, urobíme text z HTML (jednoduchý strip tagov)
    store_text = body_txt or _textify(body_htm)

    db_connector.execute_query(
        """INSERT INTO comm_messages
           (uid, direction, sender_email, sender_name, to_email, subject, body_preview, body_html, date, has_attachments,
            customer_type, customer_id, is_read, is_deleted, is_spam, message_id, raw_folder)
           VALUES (%s,'out',%s,%s,%s,%s,%s,%s,NOW(),%s,'UNKNOWN',NULL,1,0,0,NULL,'OUTBOX')""",
        (uid, from_addr, from_name, to_addr, subject, (store_text or '')[:1000], (store_html or '')[:20000], 1 if saved_paths else 0),
        'none'
    )
    for pth in saved_paths:
        try:
            db_connector.execute_query(
                "INSERT INTO comm_attachments (message_uid, filename, path, size) VALUES (%s,%s,%s,%s)",
                (uid, os.path.basename(pth).split('_',1)[-1], pth, os.path.getsize(pth)),
                'none'
            )
        except Exception:
            pass

    return {"message": "E-mail odoslaný."}

# ----------------------- Delete / Spam ----------------------------------------
def comm_delete(payload=None, purge: bool = False):
    _ensure_tables()
    ids = []
    if isinstance(payload, dict):
        ids = payload.get('ids') or []
    elif isinstance(payload, (list, tuple)):
        ids = payload
    if not ids:
        return {"error": "No ids."}
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return {"error": "No valid ids."}

    if purge:
        try:
            for mid in ids:
                row = db_connector.execute_query("SELECT uid FROM comm_messages WHERE id=%s", (mid,), 'one')
                if not row:
                    continue
                uid = row['uid']
                atts = db_connector.execute_query("SELECT path FROM comm_attachments WHERE message_uid=%s", (uid,)) or []
                for a in atts:
                    try:
                        os.remove(a['path'])
                    except Exception:
                        pass
                db_connector.execute_query("DELETE FROM comm_attachments WHERE message_uid=%s", (uid,), 'none')
            db_connector.execute_query("DELETE FROM comm_messages WHERE id IN (" + ",".join(["%s"] * len(ids)) + ")", tuple(ids), 'none')
        except Exception as e:
            return {"error": f"Purge failed: {e}"}
        return {"message": "Správy boli natrvalo vymazané."}
    else:
        db_connector.execute_query("UPDATE comm_messages SET is_deleted=1 WHERE id IN (" + ",".join(["%s"] * len(ids)) + ")", tuple(ids), 'none')
        return {"message": "Správy boli presunuté do Koša."}


def comm_mark_spam(payload=None):
    _ensure_tables()
    ids = []
    if isinstance(payload, dict):
        ids = payload.get('ids') or []
    elif isinstance(payload, (list, tuple)):
        ids = payload
    if not ids:
        return {"error": "No ids."}
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return {"error": "No valid ids."}
    db_connector.execute_query("UPDATE comm_messages SET is_spam=1, is_read=1 WHERE id IN (" + ",".join(["%s"] * len(ids)) + ")", tuple(ids), 'none')
    return {"message": "Označené ako spam."}

# ----------------------- Probes -----------------------------------------------
def comm_smtp_probe():
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587'))
    use_ssl = os.environ.get('SMTP_SSL', '0') == '1' or port == 465
    use_tls = (os.environ.get('SMTP_TLS', '1') != '0') if not use_ssl else False
    try:
        server, user, pwd, from_addr, from_name = _smtp_open()
        connected = True
        login_ok = False
        try:
            if user and pwd:
                server.login(user, pwd)
                login_ok = True
        except Exception as e:
            try:
                server.quit()
            except Exception:
                pass
            return {"ok": False, "connected": True, "login": False, "host": host, "port": port, "ssl": bool(use_ssl), "tls": bool(use_tls), "from": from_addr, "error": f"Login failed: {e}"}
        try:
            server.quit()
        except Exception:
            pass
        return {"ok": True, "connected": connected, "login": login_ok, "host": host, "port": port, "ssl": bool(use_ssl), "tls": bool(use_tls), "from": from_addr}
    except Exception as e:
        return {"ok": False, "connected": False, "login": False, "host": host, "port": port, "ssl": bool(use_ssl), "tls": bool(use_tls), "error": str(e)}


def comm_imap_probe():
    host = os.environ.get('IMAP_HOST')
    port = int(os.environ.get('IMAP_PORT', '993'))
    use_ssl = os.environ.get('IMAP_SSL', '1') == '1' or port == 993
    use_tls = os.environ.get('IMAP_TLS', '0') == '1'
    try:
        imap = _imap_open()
        try:
            imap.logout()
        except Exception:
            pass
        return {"ok": True, "host": host, "port": port, "ssl": bool(use_ssl), "tls": bool(use_tls)}
    except Exception as e:
        return {"ok": False, "host": host, "port": port, "ssl": bool(use_ssl), "tls": bool(use_tls), "error": str(e)}