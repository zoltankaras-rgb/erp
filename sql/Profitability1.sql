-- Uprav TABUĽKY modulu profit (ak existujú)
ALTER TABLE profit_calculations         CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE profit_calculation_items    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE profit_department_monthly   CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE profit_production_monthly   CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE profit_sales_monthly        CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Uprav EAN stĺpce na rovnakú koláciu (zvoľ správny názov tabuľky s produktmi)
-- Príklad pre 'produkty':
ALTER TABLE produkty MODIFY COLUMN ean VARCHAR(64)
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- A pre profit tabuľky s EAN:
ALTER TABLE profit_calculation_items  MODIFY COLUMN product_ean VARCHAR(64)
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE profit_sales_monthly      MODIFY COLUMN product_ean VARCHAR(64)
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE profit_production_monthly MODIFY COLUMN product_ean VARCHAR(64)
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
