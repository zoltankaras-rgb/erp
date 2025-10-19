-- =====================================================================
-- ERP MIK • Modul Ziskovosť – schéma tabuliek (MySQL 8, utf8mb4)
-- Bezpečne spustiteľné viackrát (CREATE IF NOT EXISTS, ALTER podmienene)
-- =====================================================================

-- Odporúčané nastavenia
SET NAMES utf8mb4;
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

-- 1) Oddelenia – mesačné sumáre
CREATE TABLE IF NOT EXISTS profit_department_monthly (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  report_year       INT NOT NULL,
  report_month      TINYINT NOT NULL,
  -- expedícia
  exp_stock_prev    DECIMAL(16,2) NOT NULL DEFAULT 0,
  exp_from_butchering DECIMAL(16,2) NOT NULL DEFAULT 0,
  exp_from_prod     DECIMAL(16,2) NOT NULL DEFAULT 0,
  exp_external      DECIMAL(16,2) NOT NULL DEFAULT 0,
  exp_returns       DECIMAL(16,2) NOT NULL DEFAULT 0,
  exp_stock_current DECIMAL(16,2) NOT NULL DEFAULT 0,
  exp_revenue       DECIMAL(16,2) NOT NULL DEFAULT 0,
  -- bitúnok / rozrábka
  butcher_meat_value    DECIMAL(16,2) NOT NULL DEFAULT 0,
  butcher_paid_goods    DECIMAL(16,2) NOT NULL DEFAULT 0,
  butcher_process_value DECIMAL(16,2) NOT NULL DEFAULT 0,
  butcher_returns_value DECIMAL(16,2) NOT NULL DEFAULT 0,
  -- režijné
  general_costs     DECIMAL(16,2) NOT NULL DEFAULT 0,
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_pdm_period (report_year, report_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) Výroba – mesačné manuálne dáta k ziskovosti
CREATE TABLE IF NOT EXISTS profit_production_monthly (
  id                         BIGINT AUTO_INCREMENT PRIMARY KEY,
  report_year                INT NOT NULL,
  report_month               TINYINT NOT NULL,
  product_ean                VARCHAR(50) NOT NULL,
  expedition_sales_kg        DECIMAL(16,3) NOT NULL DEFAULT 0,
  transfer_price_per_unit    DECIMAL(16,4) NOT NULL DEFAULT 0,
  created_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ppm (report_year, report_month, product_ean),
  KEY idx_ppm_ean (product_ean)
  -- voliteľne (ak je v 'produkty.ean' UNIQUE a INDEXED):
  -- ,CONSTRAINT fk_ppm_product FOREIGN KEY (product_ean) REFERENCES produkty(ean) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3) Predajné kanály – mesačné dáta po produktoch
CREATE TABLE IF NOT EXISTS profit_sales_monthly (
  id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
  report_year          INT NOT NULL,
  report_month         TINYINT NOT NULL,
  sales_channel        VARCHAR(80) NOT NULL,
  product_ean          VARCHAR(50) NOT NULL,
  sales_kg             DECIMAL(16,3) NOT NULL DEFAULT 0,
  purchase_price_net   DECIMAL(16,4) NOT NULL DEFAULT 0,
  purchase_price_vat   DECIMAL(16,4) NOT NULL DEFAULT 0,
  sell_price_net       DECIMAL(16,4) NOT NULL DEFAULT 0,
  sell_price_vat       DECIMAL(16,4) NOT NULL DEFAULT 0,
  created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_psm (report_year, report_month, sales_channel, product_ean),
  KEY idx_psm_channel (sales_channel),
  KEY idx_psm_ean (product_ean)
  -- voliteľne FK na produkty:
  -- ,CONSTRAINT fk_psm_product FOREIGN KEY (product_ean) REFERENCES produkty(ean) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4) Kalkulácie / súťaže – hlavička
CREATE TABLE IF NOT EXISTS profit_calculations (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  report_year     INT NOT NULL,
  report_month    TINYINT NOT NULL,
  vehicle_id      BIGINT NULL,
  distance_km     DECIMAL(12,2) NOT NULL DEFAULT 0,
  transport_cost  DECIMAL(16,2) NOT NULL DEFAULT 0,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_pc_period (report_year, report_month),
  KEY idx_pc_vehicle (vehicle_id)
  -- voliteľne FK na flotilu (ak existuje):
  -- ,CONSTRAINT fk_pc_vehicle FOREIGN KEY (vehicle_id) REFERENCES fleet_vehicles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5) Kalkulácie – položky
CREATE TABLE IF NOT EXISTS profit_calculation_items (
  id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  calculation_id     BIGINT NOT NULL,
  product_ean        VARCHAR(50) NOT NULL,
  estimated_kg       DECIMAL(16,3) NOT NULL DEFAULT 0,
  purchase_price_net DECIMAL(16,4) NOT NULL DEFAULT 0,
  sell_price_net     DECIMAL(16,4) NOT NULL DEFAULT 0,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_pci_calc (calculation_id),
  KEY idx_pci_ean (product_ean),
  CONSTRAINT fk_pci_calc FOREIGN KEY (calculation_id)
    REFERENCES profit_calculations(id)
    ON DELETE CASCADE
  -- voliteľne FK na produkty:
  -- ,CONSTRAINT fk_pci_product FOREIGN KEY (product_ean) REFERENCES produkty(ean) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- (voliteľné) seed predajných kanálov – ak chceš pridať prázdne riadky pre mesiac
-- INSERT IGNORE do profit_sales_monthly sa aj tak postará o neduplikovanie
-- INSERT INTO profit_sales_monthly (report_year, report_month, sales_channel, product_ean)
-- SELECT 2025, 10, 'B2B', ean FROM produkty;

-- Hotovo.
