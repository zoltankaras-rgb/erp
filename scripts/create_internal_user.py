import os, sys, secrets, hashlib, binascii, getpass
from dotenv import load_dotenv
import mysql.connector as mc

ITERATIONS = 250_000

def ensure_columns(cnx):
    cur = cnx.cursor()
    cur.execute("""
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'internal_users'
    """)
    cols = {r[0] for r in cur.fetchall()}
    if 'email' not in cols:
        cur.execute("ALTER TABLE internal_users ADD COLUMN email VARCHAR(255) NULL AFTER full_name")
    if 'is_active' not in cols:
        cur.execute("ALTER TABLE internal_users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER email")
    cur.execute("ALTER TABLE internal_users MODIFY COLUMN role ENUM('admin','kancelaria','vyroba','expedicia') NOT NULL DEFAULT 'kancelaria'")
    cnx.commit()
    cur.close()

def main():
    load_dotenv()
    cfg = dict(
        host=os.getenv('DB_HOST','localhost'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME') or os.getenv('DB_DATABASE'),
        port=int(os.getenv('DB_PORT') or 3306),
    )
    if not cfg['database']:
        print("Chýba DB_NAME v .env (alebo DB_DATABASE).")
        sys.exit(1)

    cnx = mc.connect(**cfg)
    ensure_columns(cnx)

    print("== Vytvorenie interného používateľa ==")
    username = input("Používateľské meno: ").strip()
    full_name = (input("Celé meno (nepovinné): ").strip() or None)
    email = (input("E-mail (nepovinné): ").strip() or None)
    role = (input("Rola [vyroba|expedicia|kancelaria|admin] (default kancelaria): ").strip() or "kancelaria")

    pwd1 = getpass.getpass("Heslo: ")
    pwd2 = getpass.getpass("Heslo znovu: ")
    if pwd1 != pwd2:
        print("Heslá nesedia."); sys.exit(1)

    salt = secrets.token_hex(16)
    hash_bytes = hashlib.pbkdf2_hmac('sha256', pwd1.encode('utf-8'), bytes.fromhex(salt), ITERATIONS)
    pwd_hash = binascii.hexlify(hash_bytes).decode()

    cur = cnx.cursor()
    cur.execute("""
        INSERT INTO internal_users (username, password_salt, password_hash, role, full_name, email, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, 1)
    """, (username, salt, pwd_hash, role, full_name, email))
    cnx.commit()
    print("✅ Používateľ vytvorený.")
    cur.close(); cnx.close()

if __name__ == "__main__":
    main()