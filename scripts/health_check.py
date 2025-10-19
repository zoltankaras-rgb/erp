import sys
import os
import json
import traceback

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(THIS_DIR, '..'))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    import db_connector as db
except Exception as e:
    print("Nepodarilo sa importovať db_connector:", e)
    sys.exit(1)

def check():
    try:
        one = db.execute_query("SELECT 1 AS ok", fetch='one')
        print("DB OK:", one)
    except Exception as e:
        print("DB query FAILED:", e)
        traceback.print_exc()
        return

    try:
        rows = db.execute_query("SHOW TABLES", fetch='all')
        all_tabs = {list(r.values())[0] for r in rows}
        essential = {"produkty","sklad","sklad_polozky","recepty"}
        missing = essential - all_tabs
        print("Missing essential tables:", missing if missing else "None")
    except Exception as e:
        print("SHOW TABLES failed:", e)

if __name__ == "__main__":
    check()
