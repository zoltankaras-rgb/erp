import db_connector
cn = db_connector.get_connection()
cur = cn.cursor()
cur.execute("SELECT DATABASE()")
db = cur.fetchone()[0]
print("Connected DB:", db)

def has_col(name):
    cur.execute(
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='internal_users' AND COLUMN_NAME=%s",
        (name,)
    )
    return cur.fetchone() is not None

changed = False
if not has_col("email"):
    cur.execute("ALTER TABLE internal_users ADD COLUMN email VARCHAR(255) NULL AFTER full_name")
    changed = True
if not has_col("is_active"):
    cur.execute("ALTER TABLE internal_users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER email")
    changed = True

# Zosúladenie typu role (ak by nebol ENUM)
cur.execute("""
SELECT DATA_TYPE, COLUMN_TYPE FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='internal_users' AND COLUMN_NAME='role'
""")
row = cur.fetchone()
need_enum = (not row) or (row[0].lower() != "enum") or any(v not in row[1] for v in ("'admin'","'kancelaria'","'vyroba'","'expedicia'"))
if need_enum:
    cur.execute("ALTER TABLE internal_users MODIFY COLUMN role ENUM('admin','kancelaria','vyroba','expedicia') NOT NULL DEFAULT 'kancelaria'")
    changed = True

cn.commit()
print("Schema updated?" , changed)
print("email exists:", has_col("email"), " | is_active exists:", has_col("is_active"))
cur.close()
db_connector.release_connection(cn)
