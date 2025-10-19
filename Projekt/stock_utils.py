# stock_utils.py — robust version compatible with priemerna_cena / nakupna_cena
from typing import Optional
import db_connector

PRICE_COLUMNS = ("priemerna_cena", "nakupna_cena")

def _detect_price_column(conn) -> str:
    cur = conn.cursor()
    cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sklad_polozky'")
    cols = {r[0] for r in cur.fetchall()}
    for c in PRICE_COLUMNS:
        if c in cols:
            return c
    # fallback default
    return "priemerna_cena"

def update_stock(product_id: int, sklad_id: int, delta: float, cena: Optional[float] = None, conn=None):
    """
    Upraví stav skladu o delta množstvo pre daný produkt a sklad.
    Ak produkt neexistuje v sklade, vloží nový záznam.
    Ak je zadaná cena (pri príjme), vypočíta novú priemernú cenu (WMA).
    """
    close_conn = False
    if conn is None:
        conn = db_connector.get_connection()
        close_conn = True

    try:
        price_col = _detect_price_column(conn)
        cur = conn.cursor(dictionary=True)

        # Zisti existujúci záznam
        cur.execute(
            f"SELECT id, mnozstvo, {price_col} AS price FROM sklad_polozky WHERE produkt_id=%s AND sklad_id=%s",
            (product_id, sklad_id)
        )
        item = cur.fetchone()

        if item:
            new_qty = float(item["mnozstvo"]) + float(delta)
            if new_qty < -1e-9:
                raise ValueError(f"Nedostatočná zásoba pre produkt {product_id} (sklad {sklad_id})")
            # Pri príjme s cenou: prepočet WMA
            if cena is not None and delta > 0:
                old_total = float(item["mnozstvo"]) * float(item["price"])
                new_total = old_total + float(delta) * float(cena)
                new_price = (new_total / new_qty) if new_qty > 0 else float(cena)
            else:
                new_price = float(item["price"])

            cur.execute(
                f"UPDATE sklad_polozky SET mnozstvo=%s, {price_col}=%s WHERE id=%s",
                (new_qty, new_price, item["id"])
            )
        else:
            insert_price = float(cena) if cena is not None else 0.0
            cur.execute(
                f"INSERT INTO sklad_polozky (produkt_id, sklad_id, mnozstvo, {price_col}) VALUES (%s,%s,%s,%s)",
                (product_id, sklad_id, delta, insert_price)
            )

        if close_conn:
            conn.commit()
            conn.close()
    except Exception:
        if close_conn and conn and getattr(conn, "is_connected", lambda: False)():
            conn.rollback()
            conn.close()
        raise
