import db_connector
cn = db_connector.get_connection()
cur = cn.cursor()
cur.execute("SELECT DATABASE()")
print("Connected DB:", cur.fetchone()[0])
cur.close()
db_connector.release_connection(cn)
