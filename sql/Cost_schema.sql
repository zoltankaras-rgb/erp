-- ===== Kategórie nákladov =====
CREATE TABLE IF NOT EXISTS costs_categories (
  id INT AUTO_INCREMENT PRIMARY KEY,
  parent_id INT NULL,
  name VARCHAR(100) NOT NULL UNIQUE,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_cost_cat_parent FOREIGN KEY (parent_id) REFERENCES costs_categories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Operatívne položky (bežné náklady) =====
CREATE TABLE IF NOT EXISTS costs_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  entry_date DATE NOT NULL,
  category_id INT NOT NULL,
  name VARCHAR(200) NOT NULL,
  description TEXT,
  amount_net DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  vat_rate DECIMAL(5,2) DEFAULT NULL,
  amount_vat DECIMAL(12,2) DEFAULT NULL,
  amount_gross DECIMAL(12,2) DEFAULT NULL,
  vendor_name VARCHAR(200),
  invoice_no VARCHAR(64),
  cost_center VARCHAR(64) DEFAULT 'company', -- napr. company / expedition / butchering / production / sales / admin
  is_recurring TINYINT(1) DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_ci_date (entry_date),
  INDEX idx_ci_cat (category_id),
  CONSTRAINT fk_ci_cat FOREIGN KEY (category_id) REFERENCES costs_categories(id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Energia: Elektrina =====
CREATE TABLE IF NOT EXISTS costs_energy_electricity (
  record_year  INT NOT NULL,
  record_month TINYINT NOT NULL,
  odpis_vse DECIMAL(12,3) DEFAULT NULL,
  fakturacia_vse DECIMAL(12,3) DEFAULT NULL,
  rozdiel_vse DECIMAL(12,3) DEFAULT NULL,
  odpis_vse_nt DECIMAL(12,3) DEFAULT NULL,
  fakturacia_vse_nt DECIMAL(12,3) DEFAULT NULL,
  rozdiel_vse_nt DECIMAL(12,3) DEFAULT NULL,
  faktura_s_dph DECIMAL(12,2) DEFAULT NULL,
  final_cost DECIMAL(12,2) DEFAULT NULL, -- vyčíslený čistý náklad (v tvojom handleri)
  PRIMARY KEY (record_year, record_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Energia: Plyn =====
CREATE TABLE IF NOT EXISTS costs_energy_gas (
  record_year  INT NOT NULL,
  record_month TINYINT NOT NULL,
  stav_odpisany DECIMAL(12,3) DEFAULT NULL,
  stav_fakturovany DECIMAL(12,3) DEFAULT NULL,
  rozdiel_m3 DECIMAL(12,3) DEFAULT NULL,
  spal_teplo DECIMAL(12,3) DEFAULT NULL,
  obj_koeficient DECIMAL(12,3) DEFAULT NULL,
  spotreba_kwh DECIMAL(12,3) DEFAULT NULL,
  nakup_plynu_eur DECIMAL(12,2) DEFAULT NULL,
  distribucia_eur DECIMAL(12,2) DEFAULT NULL,
  straty_eur DECIMAL(12,2) DEFAULT NULL,
  poplatok_okte_eur DECIMAL(12,2) DEFAULT NULL,
  spolu_bez_dph DECIMAL(12,2) DEFAULT NULL,
  dph DECIMAL(12,2) DEFAULT NULL,
  spolu_s_dph DECIMAL(12,2) DEFAULT NULL,
  PRIMARY KEY (record_year, record_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Energia: Voda =====
CREATE TABLE IF NOT EXISTS costs_energy_water (
  record_year  INT NOT NULL,
  record_month TINYINT NOT NULL,
  meter_prev DECIMAL(12,3) DEFAULT NULL,
  meter_curr DECIMAL(12,3) DEFAULT NULL,
  delta_m3 DECIMAL(12,3) DEFAULT NULL,
  unit_price DECIMAL(12,4) DEFAULT NULL,
  total_bez_dph DECIMAL(12,2) DEFAULT NULL,
  dph DECIMAL(12,2) DEFAULT NULL,
  total_s_dph DECIMAL(12,2) DEFAULT NULL,
  PRIMARY KEY (record_year, record_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== HR (mzdy + odvody za firmu) =====
CREATE TABLE IF NOT EXISTS costs_hr (
  record_year  INT NOT NULL,
  record_month TINYINT NOT NULL,
  total_salaries DECIMAL(12,2) DEFAULT 0.00,
  total_levies   DECIMAL(12,2) DEFAULT 0.00,
  PRIMARY KEY (record_year, record_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== Základné kategórie (seed) =====
INSERT IGNORE INTO costs_categories (name) VALUES
('Energia – elektrina'),
('Energia – plyn'),
('Energia – voda'),
('Telekom – mobil'),
('Telekom – internet'),
('Čistenie a hygiena'),
('Opravy – stroje'),
('Opravy – autá'),
('Opravy – budovy'),
('Poistenie'),
('Nájom'),
('PHM / palivo'),
('Služby externé'),
('Softvér / licencie'),
('Účtovníctvo / audítor'),
('Bankové poplatky'),
('Kancelársky materiál'),
('Marketing / reklama'),
('Cestovné / diéty'),
('Školenia'),
('Dane a poplatky'),
('Ostatné');
