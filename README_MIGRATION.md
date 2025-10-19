# ERP – prepojené na novú DB `erp_new`

## Kroky
1) V MySQL Workbench spusti súbor: `sql/erp_new_schema.sql` (vytvorí DB a seed dáta).
2) V `.env` nastav:
   ```
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=...
   DB_NAME=erp_new
   ```
3) Nainštaluj závislosti:
   ```bash
   pip install -r requirements.txt
   ```
4) Vytvor interného používateľa:
   ```bash
   python -m scripts.create_internal_user
   ```
5) Spusť aplikáciu:
   ```bash
   python app.py
   ```

## Kontrola spojenia
```bash
python scripts/db_ping.py
```

## Poznámka
- Kľúčové handler funkcie pre Výrobu a Inventúru sú zosúladené s tabuľkami `sklad_polozky`, `zaznamy_vyroba`, `products`.
- Pohľady `produkty`, `katalog_produktov`, `v_sklad_stav`, `v_inventory_ledger` sú súčasťou SQL.