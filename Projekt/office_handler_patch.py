import traceback            # lebo traceback sa používa v except
import db_connector         # v kóde voláš db_connector.*, ale modul nebol importovaný
from logger import logger   # používaš logger

def get_slicing_management_data():
    try:
        source_products = db_connector.execute_query(
            "SELECT ean, nazov FROM produkty WHERE TRIM(UPPER(typ)) IN ('VÝROBOK', 'VYROBOK') ORDER BY nazov"
        )
        unlinked_sliced = db_connector.execute_query(
            "SELECT ean, nazov FROM produkty WHERE typ = 'krajaný' AND (zdrojovy_ean IS NULL OR zdrojovy_ean = '')"
        )
        return {"sourceProducts": source_products, "unlinkedSlicedProducts": unlinked_sliced}
    except Exception as e:
        logger.error("Chyba v get_slicing_management_data: " + traceback.format_exc())
        return {"error": "Interná chyba pri načítaní dát pre správu krájaných produktov."}
