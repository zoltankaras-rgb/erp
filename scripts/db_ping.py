from dotenv import load_dotenv
load_dotenv()
import db_connector

cn = db_connector.get_connection()
cur = cn.cursor()
cur.execute("SELECT DATABASE(), USER(), VERSION()")
print("Connected:", cur.fetchone())
for q in [
    "SELECT COUNT(*) FROM warehouses",
    "SELECT COUNT(*) FROM products",
    "SELECT COUNT(*) FROM sklad_polozky"
]:
    try:
        cur.execute(q); print(q, "=>", cur.fetchone()[0])
    except Exception as e:
        print("Query failed:", q, "->", e)
cur.close(); cn.close()
print("DB ping OK ✅")