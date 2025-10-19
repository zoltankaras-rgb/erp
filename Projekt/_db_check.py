from dotenv import load_dotenv
load_dotenv()
import os, mysql.connector as mc

cfg = {k: os.getenv(k) for k in ("DB_HOST","DB_PORT","DB_USER","DB_PASSWORD","DB_NAME")}
print("CFG=", cfg)

cn = mc.connect(
    host=cfg["DB_HOST"],
    user=cfg["DB_USER"],
    password=cfg["DB_PASSWORD"],
    database=cfg["DB_NAME"],
    port=int(cfg["DB_PORT"] or 3306),
)
cur = cn.cursor()
cur.execute("SELECT DATABASE()")
print("Connected DB:", cur.fetchone()[0])
for col in ("email","is_active"):
    cur.execute(f"SHOW COLUMNS FROM internal_users LIKE '{col}'")
    print(f"{col} col:", cur.fetchone())
cur.close(); cn.close()
