# Kancelária – sklad & katalóg (rýchla inštalácia)

## 0) Čo je v balíku
- `sql/erp_compat_views_v2.sql` – opravuje view `produkty`, aby obsahovalo stĺpec `kategoria`.
- `sql/erp_suppliers.sql` – tabuľky `suppliers` a `product_suppliers`.
- `sql/erp_sales_categories.sql` – predajné kategórie a mapovanie na produkty.
- `sql/erp_stock_features.sql` – tabuľka `writeoff_logs` a procedúra `sp_manual_writeoff`.
- `py/office_catalog_stock_handler.py` – hotové Python funkcie pre API.
- `scripts/install_kancelaria_patch.py` – automaticky doplní endpointy do `app.py`.

## 1) Spusti SQL skripty (Workbench)
1. `sql/erp_compat_views_v2.sql`
2. `sql/erp_suppliers.sql`
3. `sql/erp_sales_categories.sql`
4. `sql/erp_stock_features.sql`

## 2) Skopíruj Python modul
Skopíruj `py/office_catalog_stock_handler.py` do priečinka s `app.py`:
```
C:\Users\zolko\Desktop\Projekt\office_catalog_stock_handler.py
```

## 3) Aplikuj patch do app.py
```powershell
python scripts/install_kancelaria_patch.py
```

## 4) Reštartuj aplikáciu
```powershell
python app.py
```

## 5) Nové/doplenené API (Kancelária)
- `POST /api/kancelaria/stock/getProductionOverview`
- `POST /api/kancelaria/stock/receive`
- `POST /api/kancelaria/stock/writeoff`
- `GET  /api/kancelaria/getCatalogManagementData`
- `POST /api/kancelaria/catalog/saveProduct`
- `POST /api/kancelaria/catalog/saveCategory`
- `POST /api/kancelaria/catalog/saveSalesCategory`
- `POST /api/kancelaria/catalog/saveSupplier`

> Všetko funguje bez zásahu do HTML šablón – frontend už tieto endpointy používa, alebo ich vieš pohodlne volať z aktuálnych modulov.
