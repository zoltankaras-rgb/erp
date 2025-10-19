-- ============================================
-- ERP_NEW – čistá kompatibilná schéma (MySQL 8)
-- ============================================

DROP DATABASE IF EXISTS `erp_new`;
CREATE DATABASE `erp_new` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `erp_new`;

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ------------ ZÁKLAD: Užívatelia (interní) ------------
CREATE TABLE internal_users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(50)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  password_salt VARCHAR(255) NOT NULL,
  role          ENUM('admin','kancelaria','vyroba','expedicia') NOT NULL DEFAULT 'kancelaria',
  full_name     VARCHAR(100) NULL,
  email         VARCHAR(255) NULL,
  is_active     TINYINT(1)   NOT NULL DEFAULT 1,
  created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------ Katalóg, produkty, dodávatelia ------------
CREATE TABLE product_categories (
  id   BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE products (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  ean           VARCHAR(32) UNIQUE,
  nazov         VARCHAR(200) NOT NULL,
  typ           TINYINT      NOT NULL,                        -- napr. 0=kg, 1=ks (alebo podľa tvojej mapy)
  jednotka      TINYINT      NOT NULL,                        -- 0=kg, 1=ks ...
  kategoria_id  BIGINT       NULL,
  min_zasoba    DECIMAL(18,3) NOT NULL DEFAULT 0.000,
  dph           DECIMAL(5,2)  NOT NULL DEFAULT 20.00,
  je_vyroba     TINYINT(1)    NOT NULL DEFAULT 0,
  parent_id     BIGINT        NULL,
  created_at    DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at    DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_products_category FOREIGN KEY (kategoria_id) REFERENCES product_categories(id) ON DELETE SET NULL,
  CONSTRAINT fk_products_parent   FOREIGN KEY (parent_id)    REFERENCES products(id)           ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE sales_categories (
  id   INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE product_sales_categories (
  product_id       BIGINT NOT NULL,
  sales_category_id INT  NOT NULL,
  PRIMARY KEY (product_id, sales_category_id),
  CONSTRAINT fk_psc_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT fk_psc_sales   FOREIGN KEY (sales_category_id) REFERENCES sales_categories(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE suppliers (
  id      BIGINT AUTO_INCREMENT PRIMARY KEY,
  name    VARCHAR(255) NOT NULL,
  ico     VARCHAR(20),
  dic     VARCHAR(20),
  ic_dph  VARCHAR(20),
  email   VARCHAR(255),
  phone   VARCHAR(50),
  address VARCHAR(255),
  note    TEXT
) ENGINE=InnoDB;

CREATE TABLE product_suppliers (
  product_id     BIGINT NOT NULL,
  supplier_id    BIGINT NOT NULL,
  supplier_code  VARCHAR(100),
  last_price     DECIMAL(18,4),
  preferred      TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (product_id, supplier_id),
  CONSTRAINT fk_ps_product  FOREIGN KEY (product_id)  REFERENCES products(id)  ON DELETE CASCADE,
  CONSTRAINT fk_ps_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------ Sklady, zásoby, pohyby ------------
CREATE TABLE warehouses (
  id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  nazov VARCHAR(100) NOT NULL UNIQUE,
  typ   TINYINT      NOT NULL
) ENGINE=InnoDB;

CREATE TABLE sklad_polozky (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  sklad_id       BIGINT NOT NULL,
  produkt_id     BIGINT NOT NULL,
  mnozstvo       DECIMAL(18,3) NOT NULL DEFAULT 0.000,
  priemerna_cena DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
  UNIQUE KEY uq_sklad_produkt (sklad_id, produkt_id),
  CONSTRAINT fk_sp_sklad   FOREIGN KEY (sklad_id)   REFERENCES warehouses(id) ON DELETE CASCADE,
  CONSTRAINT fk_sp_product FOREIGN KEY (produkt_id) REFERENCES products(id)   ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE inventory_movements (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  ts            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  sklad_id      BIGINT      NOT NULL,
  produkt_id    BIGINT      NOT NULL,
  qty_change    DECIMAL(18,3) NOT NULL,
  unit_cost     DECIMAL(18,4) NOT NULL,
  movement_type TINYINT       NOT NULL,  -- napr. 1=príjem,2=výdaj,3=odpis...
  ref_table     VARCHAR(50),
  ref_id        BIGINT,
  note          VARCHAR(255),
  KEY idx_mov_spt (sklad_id, produkt_id, ts),
  CONSTRAINT fk_mov_sklad   FOREIGN KEY (sklad_id)   REFERENCES warehouses(id),
  CONSTRAINT fk_mov_product FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE zaznamy_prijem (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  sklad_id   BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  datum      DATETIME(6) NOT NULL,
  mnozstvo   DECIMAL(18,3) NOT NULL,
  cena       DECIMAL(18,4) NOT NULL,
  dodavatel  VARCHAR(200),
  KEY idx_prijem_sp (sklad_id, produkt_id),
  CONSTRAINT fk_prijem_sklad   FOREIGN KEY (sklad_id)   REFERENCES warehouses(id),
  CONSTRAINT fk_prijem_product FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE writeoff_logs (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  ts             DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  sklad_id       BIGINT NOT NULL,
  produkt_id     BIGINT NOT NULL,
  qty            DECIMAL(18,3) NOT NULL,
  reason_code    TINYINT      NOT NULL,
  reason_text    VARCHAR(255),
  actor_user_id  BIGINT,
  signature_text VARCHAR(255),
  KEY idx_wo_sp (sklad_id, produkt_id),
  CONSTRAINT fk_wo_sklad   FOREIGN KEY (sklad_id)   REFERENCES warehouses(id),
  CONSTRAINT fk_wo_product FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE skody (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  sklad_id   BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  datum      DATETIME(6) NOT NULL,
  mnozstvo   DECIMAL(18,3) NOT NULL,
  dovod      VARCHAR(200),
  KEY idx_skody_sp (sklad_id, produkt_id),
  CONSTRAINT fk_skody_sklad   FOREIGN KEY (sklad_id)   REFERENCES warehouses(id),
  CONSTRAINT fk_skody_product FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

-- ------------ Recepty & Výroba ------------
CREATE TABLE recepty (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  vyrobok_id  BIGINT NOT NULL UNIQUE,  -- 1 recept na 1 výrobok
  nazov       VARCHAR(200) NOT NULL,
  CONSTRAINT fk_recipe_product FOREIGN KEY (vyrobok_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE recepty_polozky (
  id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
  recept_id             BIGINT NOT NULL,
  surovina_id           BIGINT NOT NULL,
  mnozstvo_na_davku     DECIMAL(18,3) NOT NULL,
  CONSTRAINT fk_rp_recipe  FOREIGN KEY (recept_id)  REFERENCES recepty(id)   ON DELETE CASCADE,
  CONSTRAINT fk_rp_product FOREIGN KEY (surovina_id) REFERENCES products(id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE zaznamy_vyroba (
  id                     BIGINT AUTO_INCREMENT PRIMARY KEY,
  vyrobok_id             BIGINT      NOT NULL,
  datum_vyroby           DATETIME(6) NOT NULL,
  planovane_mnozstvo     DECIMAL(18,3) NOT NULL,
  skutocne_vyrobene      DECIMAL(18,3),
  stav                   VARCHAR(50) NOT NULL DEFAULT 'Automaticky naplánované',
  celkova_cena_surovin   DECIMAL(18,4),
  KEY idx_zv_vyrobok (vyrobok_id, datum_vyroby),
  CONSTRAINT fk_zv_product FOREIGN KEY (vyrobok_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE slicing_logs (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  datum             DATETIME(6) NOT NULL,
  source_product_id BIGINT NOT NULL,
  sliced_product_id BIGINT NOT NULL,
  source_qty        DECIMAL(18,3) NOT NULL,
  sliced_qty        DECIMAL(18,3) NOT NULL,
  operator          VARCHAR(100),
  CONSTRAINT fk_sl_source FOREIGN KEY (source_product_id) REFERENCES products(id),
  CONSTRAINT fk_sl_sliced FOREIGN KEY (sliced_product_id) REFERENCES products(id)
) ENGINE=InnoDB;

-- ------------ Inventúry ------------
CREATE TABLE inventury (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  sklad_id    BIGINT NOT NULL,
  datum_start DATETIME(6) NOT NULL,
  datum_end   DATETIME(6),
  poznamka    VARCHAR(255),
  CONSTRAINT fk_inv_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id)
) ENGINE=InnoDB;

CREATE TABLE inventury_polozky (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  inventura_id   BIGINT NOT NULL,
  produkt_id     BIGINT NOT NULL,
  systemovy_stav DECIMAL(18,3) NOT NULL,
  realny_stav    DECIMAL(18,3) NOT NULL,
  rozdiel        DECIMAL(18,3) NOT NULL,
  CONSTRAINT fk_invp_inv     FOREIGN KEY (inventura_id) REFERENCES inventury(id) ON DELETE CASCADE,
  CONSTRAINT fk_invp_product FOREIGN KEY (produkt_id)   REFERENCES products(id)
) ENGINE=InnoDB;

-- Pre staršie volania v kóde (log rozdielov podľa názvu):
CREATE TABLE inventurne_rozdiely (
  id                    INT AUTO_INCREMENT PRIMARY KEY,
  datum                 DATETIME NOT NULL,
  nazov_suroviny        VARCHAR(200) NOT NULL,
  typ_suroviny          VARCHAR(100),
  systemovy_stav_kg     DECIMAL(10,3) NOT NULL,
  realny_stav_kg        DECIMAL(10,3) NOT NULL,
  rozdiel_kg            DECIMAL(10,3) NOT NULL,
  hodnota_rozdielu_eur  DECIMAL(10,2) NOT NULL,
  pracovnik             VARCHAR(100)
) ENGINE=InnoDB;

-- ------------ B2C ------------
CREATE TABLE b2c_cennik_polozky (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  ean_produktu        VARCHAR(45) NOT NULL UNIQUE,
  cena_bez_dph        DECIMAL(10,4) NOT NULL,
  je_v_akcii          TINYINT(1)   NOT NULL DEFAULT 0,
  akciova_cena_bez_dph DECIMAL(10,4)
) ENGINE=InnoDB;

CREATE TABLE b2c_objednavky (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  datum         DATETIME(6) NOT NULL,
  body          INT NOT NULL DEFAULT 0,
  celkom_s_dph  DECIMAL(18,4) NOT NULL DEFAULT 0.0000
) ENGINE=InnoDB;

CREATE TABLE b2c_objednavky_polozky (
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  objednavka_id    BIGINT NOT NULL,
  produkt_id       BIGINT NOT NULL,
  mnozstvo         DECIMAL(18,3) NOT NULL,
  cena_za_jednotku DECIMAL(18,4) NOT NULL,
  dph_percent      DECIMAL(5,2) NOT NULL,
  CONSTRAINT fk_b2c_pol_obj FOREIGN KEY (objednavka_id) REFERENCES b2c_objednavky(id) ON DELETE CASCADE,
  CONSTRAINT fk_b2c_pol_prd FOREIGN KEY (produkt_id)    REFERENCES products(id)
) ENGINE=InnoDB;

-- ------------ B2B ------------
CREATE TABLE b2b_cenniky (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  nazov_cennika  VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE b2b_cennik_polozky (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  cennik_id    INT NOT NULL,
  ean_produktu VARCHAR(100) NOT NULL,
  cena         DECIMAL(10,2) NOT NULL,
  UNIQUE KEY uq_b2b_cennik_ean (cennik_id, ean_produktu),
  CONSTRAINT fk_b2b_cennik_pol FOREIGN KEY (cennik_id) REFERENCES b2b_cenniky(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE b2b_zakaznici (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  zakaznik_id         VARCHAR(50)  NOT NULL UNIQUE,
  nazov_firmy         VARCHAR(255) NOT NULL,
  adresa              VARCHAR(255),
  email               VARCHAR(255) NOT NULL UNIQUE,
  telefon             VARCHAR(50),
  heslo_hash          VARCHAR(255) NOT NULL,
  heslo_salt          VARCHAR(255) NOT NULL,
  je_schvaleny        TINYINT(1) NOT NULL DEFAULT 0,
  je_admin            TINYINT(1) NOT NULL DEFAULT 0,
  datum_registracie   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reset_token         VARCHAR(255),
  reset_token_expiry  DATETIME
) ENGINE=InnoDB;

CREATE TABLE b2b_objednavky (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  zakaznik_id          INT NOT NULL,
  cislo_objednavky     VARCHAR(100) NOT NULL UNIQUE,
  datum_objednavky     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  pozadovany_datum_dodania DATE,
  poznamka             TEXT,
  celkova_suma         DECIMAL(10,2) NOT NULL,
  status               VARCHAR(50) NOT NULL DEFAULT 'Prijatá',
  CONSTRAINT fk_b2b_obj_zak FOREIGN KEY (zakaznik_id) REFERENCES b2b_zakaznici(id)
) ENGINE=InnoDB;

CREATE TABLE b2b_objednavky_polozky (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  objednavka_id     INT NOT NULL,
  ean_produktu      VARCHAR(100) NOT NULL,
  nazov_produktu    VARCHAR(255) NOT NULL,
  mnozstvo          DECIMAL(10,2) NOT NULL,
  cena_za_jednotku  DECIMAL(10,2) NOT NULL,
  CONSTRAINT fk_b2b_pol_obj FOREIGN KEY (objednavka_id) REFERENCES b2b_objednavky(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE b2b_promotions (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  chain_id             INT NOT NULL,
  ean                  VARCHAR(255) NOT NULL,
  product_name         VARCHAR(255) NOT NULL,
  start_date           DATE NOT NULL,
  end_date             DATE NOT NULL,
  delivery_start_date  DATE,
  sale_price_net       DECIMAL(10,4) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE b2b_retail_chains (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE b2b_zakaznik_cennik (
  zakaznik_id INT NOT NULL,
  cennik_id   INT NOT NULL,
  PRIMARY KEY (zakaznik_id, cennik_id),
  CONSTRAINT fk_b2b_zc_z  FOREIGN KEY (zakaznik_id) REFERENCES b2b_zakaznici(id) ON DELETE CASCADE,
  CONSTRAINT fk_b2b_zc_c  FOREIGN KEY (cennik_id)   REFERENCES b2b_cenniky(id)  ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------ Hygiena / HACCP / Flotila / Náklady ------------
CREATE TABLE hygiene_tasks (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  nazov     VARCHAR(200) NOT NULL,
  plan_datum DATE NOT NULL,
  stav      TINYINT NOT NULL DEFAULT 0,
  poznamka  VARCHAR(255)
) ENGINE=InnoDB;

CREATE TABLE hygiene_agents (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  agent_name VARCHAR(255) NOT NULL UNIQUE,
  is_active  TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE hygiene_plan (
  id                    INT AUTO_INCREMENT PRIMARY KEY,
  plan_date             DATE NOT NULL,
  task_name             VARCHAR(255) NOT NULL,
  location              VARCHAR(255) NOT NULL,
  agent_name            VARCHAR(255),
  concentration         VARCHAR(50),
  exposure_time         VARCHAR(50),
  user_fullname         VARCHAR(255),
  completion_date       DATETIME,
  checked_by_fullname   VARCHAR(255),
  checked_at            DATETIME
) ENGINE=InnoDB;

CREATE TABLE haccp_dokumenty (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  typ        VARCHAR(100) NOT NULL,
  verzia     VARCHAR(50)  NOT NULL,
  file_path  VARCHAR(255) NOT NULL,
  created_at DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

CREATE TABLE fleet_vehicles (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  znacka     VARCHAR(100) NOT NULL,
  model      VARCHAR(100),
  vin        VARCHAR(100),
  stav_km    INT NOT NULL DEFAULT 0,
  servis_info VARCHAR(255)
) ENGINE=InnoDB;

CREATE TABLE costs_categories (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  name      VARCHAR(100) NOT NULL UNIQUE,
  is_active TINYINT(1)   NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE costs_items (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  entry_date   DATE NOT NULL,
  category_id  INT  NOT NULL,
  name         VARCHAR(255) NOT NULL,
  description  TEXT,
  amount_net   DECIMAL(12,2) NOT NULL,
  is_recurring TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_costs_cat FOREIGN KEY (category_id) REFERENCES costs_categories(id)
) ENGINE=InnoDB;

CREATE TABLE costs_energy_electricity (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  record_year        INT NOT NULL,
  record_month       INT NOT NULL,
  odpis_vse          DECIMAL(10,2),
  fakturacia_vse     DECIMAL(10,2),
  rozdiel_vse        DECIMAL(10,2),
  odpis_vse_nt       DECIMAL(10,2),
  fakturacia_vse_nt  DECIMAL(10,2),
  rozdiel_vse_nt     DECIMAL(10,2),
  faktura_s_dph      DECIMAL(10,2),
  final_cost         DECIMAL(10,2),   -- komentár: FA s DPH / 4,68
  KEY idx_el_year (record_year)
) ENGINE=InnoDB;

CREATE TABLE costs_energy_gas (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  record_year        INT NOT NULL,
  record_month       INT NOT NULL,
  stav_odpisany      DECIMAL(10,3),
  stav_fakturovany   DECIMAL(10,3),
  rozdiel_m3         DECIMAL(10,3),
  spal_teplo         DECIMAL(10,4),
  obj_koeficient     DECIMAL(10,4),
  spotreba_kwh       DECIMAL(10,3),
  nakup_plynu_eur    DECIMAL(10,2),
  distribucia_eur    DECIMAL(10,2),
  straty_eur         DECIMAL(10,2),
  poplatok_okte_eur  DECIMAL(10,2),
  spolu_bez_dph      DECIMAL(10,2),
  dph                DECIMAL(10,2),
  spolu_s_dph        DECIMAL(10,2),
  KEY idx_gas_year (record_year)
) ENGINE=InnoDB;

CREATE TABLE costs_hr (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  record_year   INT NOT NULL,
  record_month  INT NOT NULL,
  total_salaries DECIMAL(12,2),
  total_levies   DECIMAL(12,2),
  KEY idx_hr_year (record_year)
) ENGINE=InnoDB;

-- ------------ Pohľady (views) ------------
-- 1) produkty – „peknejšia“ projekcia product + kategória
CREATE OR REPLACE VIEW produkty AS
SELECT
  p.id,
  p.ean,
  p.nazov,
  p.typ,
  COALESCE(pc.name, '') AS kategoria,
  p.jednotka,
  p.min_zasoba,
  p.dph,
  p.je_vyroba,
  p.parent_id,
  p.kategoria_id
FROM products p
LEFT JOIN product_categories pc ON pc.id = p.kategoria_id;

-- 2) alias pre staršie volania
CREATE OR REPLACE VIEW katalog_produktov AS
SELECT * FROM produkty;

-- 3) stav skladu (zjednodušený pohľad)
CREATE OR REPLACE VIEW v_sklad_stav AS
SELECT
  sp.sklad_id,
  w.nazov AS sklad,
  sp.produkt_id,
  p.nazov AS produkt,
  sp.mnozstvo,
  sp.priemerna_cena
FROM sklad_polozky sp
JOIN warehouses w ON w.id=sp.sklad_id
JOIN products   p ON p.id=sp.produkt_id;

-- 4) inventory ledger (denormalizovaný výpis pohybov)
CREATE OR REPLACE VIEW v_inventory_ledger AS
SELECT
  im.id,
  im.ts,
  im.sklad_id,
  im.produkt_id,
  im.qty_change,
  im.unit_cost,
  im.movement_type,
  im.ref_table,
  im.ref_id,
  im.note,
  w.nazov AS sklad,
  p.nazov AS produkt
FROM inventory_movements im
JOIN warehouses w ON w.id=im.sklad_id
JOIN products   p ON p.id=im.produkt_id;

-- ------------ SEED (minimálna dátová sada) ------------
INSERT INTO warehouses (nazov, typ) VALUES
('Výroba', 1), ('Expedícia', 2);

INSERT INTO product_categories (name) VALUES ('Základné produkty');

INSERT INTO products (ean, nazov, typ, jednotka, kategoria_id, min_zasoba, dph, je_vyroba)
VALUES ('1234567890123','Test výrobok 1 kg',1,0,(SELECT id FROM product_categories LIMIT 1),5.000,20.00,1);

-- počiatočný stav na sklade Výroba
INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena)
SELECT w.id, p.id, 10.000, 5.0000
FROM warehouses w, products p
WHERE w.nazov='Výroba' AND p.ean='1234567890123';

-- B2C cenník
INSERT INTO b2c_cennik_polozky (ean_produktu, cena_bez_dph, je_v_akcii, akciova_cena_bez_dph)
VALUES ('1234567890123', 6.0000, 0, NULL);

-- B2B cenník + položka
INSERT INTO b2b_cenniky (nazov_cennika) VALUES ('B2B Štandard');
INSERT INTO b2b_cennik_polozky (cennik_id, ean_produktu, cena)
SELECT c.id, '1234567890123', 5.500 FROM b2b_cenniky c WHERE c.nazov_cennika='B2B Štandard';

-- ukážková výrobná dávka (aby menu výroby niečo videlo)
INSERT INTO zaznamy_vyroba (vyrobok_id, datum_vyroby, planovane_mnozstvo, skutocne_vyrobene, stav)
SELECT p.id, NOW(6), 100.000, 0.000, 'Automaticky naplánované'
FROM products p WHERE p.ean='1234567890123' LIMIT 1;
