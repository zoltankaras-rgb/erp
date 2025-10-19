# -*- coding: utf-8 -*-
import re
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
app_py = PROJECT_ROOT / "app.py"

if not app_py.exists():
    print("Nenašiel som app.py v", app_py)
    sys.exit(1)

txt = app_py.read_text(encoding="utf-8", errors="ignore")

# 1) Import handlera
if "import office_catalog_stock_handler" not in txt and "from office_catalog_stock_handler" not in txt:
    txt = re.sub(r"(import\s+office_handler[^\n]*\n)", r"\1import office_catalog_stock_handler\n", txt, count=1)

# 2) endpoint_map – doplnenie kľúčov
m = re.search(r"endpoint_map\s*=\s*\{", txt)
if not m:
    print("Nepodarilo sa nájsť endpoint_map v app.py")
    sys.exit(2)

insert_block = '''
        # --- PATCH: sklad & katalóg ---
        'stock/getProductionOverview': office_catalog_stock_handler.get_production_stock_overview,
        'stock/receive': office_catalog_stock_handler.receive_production_items,
        'stock/writeoff': office_catalog_stock_handler.manual_writeoff,
        'getCatalogManagementData': office_catalog_stock_handler.get_catalog_management_data,
        'catalog/saveProduct': office_catalog_stock_handler.save_catalog_product,
        'catalog/saveCategory': office_catalog_stock_handler.save_catalog_category,
        'catalog/saveSalesCategory': office_catalog_stock_handler.save_sales_category,
        'catalog/saveSupplier': office_catalog_stock_handler.save_supplier,
'''

pos = m.end()
txt = txt[:pos] + insert_block + txt[pos:]

app_py.write_text(txt, encoding="utf-8")
print("✅ Patch aplikovaný do app.py")
