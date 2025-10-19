import os, glob
import db_connector as db
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
def run():
    sql_dir = os.path.join(os.path.dirname(__file__), '..', 'sql', 'migrations')
    sql_dir = os.path.abspath(sql_dir)
    files = sorted(glob.glob(os.path.join(sql_dir, '*.sql')))
    print('[MIGRATE] Applying', len(files), 'SQL files from', sql_dir)
    conn = db.get_connection() if hasattr(db, 'get_connection') else None
    if conn is None:
        # fallback for older connector
        import mysql.connector, os
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST','localhost'),
            user=os.getenv('DB_USER','root'),
            password=os.getenv('DB_PASSWORD',''),
            database=os.getenv('DB_DATABASE','vyrobny_system')
        )
    cur = conn.cursor()
    try:
        for f in files:
            print('  ->', os.path.basename(f))
            with open(f, 'r', encoding='utf-8') as fh:
                sql = fh.read()
            for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
                cur.execute(stmt)
        conn.commit()
        print('[MIGRATE] Done.')
    finally:
        try: cur.close()
        except: pass
        try: conn.close()
        except: pass

if __name__ == '__main__':
    run()
