import mysql.connector
from mysql.connector import pooling
import os
import traceback
from dotenv import load_dotenv
db_name = os.getenv("DB_NAME") or os.getenv("DB_DATABASE")
# Načíta premenné z .env súboru
load_dotenv()

# --- KONFIGURÁCIA DATABÁZY ---
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'karas'),
    'database': os.getenv('DB_DATABASE') or os.getenv('DB_NAME', 'vyrobny_system')
}

connection_pool = None
try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="vyroba_pool",
        pool_size=5,
        **DB_CONFIG
    )
    print(">>> MySQL Connection Pool bol úspešne vytvorený.")
except mysql.connector.Error as e:
    print(f"!!! KRITICKÁ CHYBA: Nepodarilo sa pripojiť k MySQL databáze: {e}")
    print("--- Skontrolujte, či je MySQL server spustený a konfiguračné premenné v .env súbore sú správne.")

def get_connection():
    """Získa jedno voľné pripojenie z pool-u."""
    if not connection_pool:
        raise Exception("Connection pool nie je k dispozícii. Aplikácia sa nemôže pripojiť k databáze.")
    return connection_pool.get_connection()

def execute_query(query, params=None, fetch='all', multi=False):
    """
    Centrálna a bezpečná funkcia na vykonávanie SQL príkazov.
    Využíva transakcie pre bezpečnosť dát.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        
        if multi:
            cursor.executemany(query, params)
        else:
            cursor.execute(query, params or ())
        
        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            return cursor.fetchall()
        else: # 'none', 'lastrowid' atď., kde sa vykonáva zápis
            conn.commit()
            if fetch == 'lastrowid':
                return cursor.lastrowid
            return cursor.rowcount
            
    except Exception as e:
        print(f"!!! DB CHYBA pri vykonávaní SQL príkazu: {query[:100]}...")
        # Vylepšené logovanie pre lepšiu diagnostiku
        print(traceback.format_exc())
        if conn:
            conn.rollback() # V prípade chyby vráti všetky zmeny späť
        raise e # Pošle chybu ďalej, aby ju zachytil handle_request v app.py
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
def release_connection(conn):
    try:
        conn.close()  # v pooli to znamená vrátiť spojenie
    except Exception:
        pass
# --- Convenience: vráť prvý riadok alebo None ---
def execute_one(query, params=None):
    """
    Vykoná SELECT a vráti prvý riadok (dict) alebo None.
    """
    rows = execute_query(query, params)
    if rows and isinstance(rows, list):
        return rows[0]
    return None

