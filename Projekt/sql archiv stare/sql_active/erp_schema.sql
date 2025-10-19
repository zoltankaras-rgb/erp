-- =====================================================================
-- ERP DDL + RBAC + Procedúry (MySQL 8.0+)
-- =====================================================================

DROP DATABASE IF EXISTS erp;
CREATE DATABASE erp CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE erp;

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- =========================
-- 0) KONŠTANTY / ENUM mapy
-- =========================
-- movement_type:
-- 0=RECEIPT,1=CONSUMPTION,2=PRODUCTION_IN,3=TRANSFER_IN,4=TRANSFER_OUT,
-- 5=DAMAGE,6=INV_ADJUST,7=ORDER_OUT,8=SLICING_IN,9=SLICING_OUT
-- warehouses.typ: 0=vyrobny, 1=centralny
-- products.typ: 0=surovina,1=vyrobok,2=krajeny,3=externy
-- units: 0=kg,1=ks,2=l
-- production.stav: 0=VoVyrobe,1=Ukoncene,2=PrijateCakaNaTlac

-- =========================
-- 1) CORE TABUĽKY
-- =========================
CREATE TABLE product_categories (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  UNIQUE KEY uq_product_categories_name (name)
) ENGINE=InnoDB;

CREATE TABLE products (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  ean VARCHAR(32) NULL,
  nazov VARCHAR(200) NOT NULL,
  typ TINYINT NOT NULL,               -- 0=surovina,1=vyrobok,2=krajeny,3=externy
  jednotka TINYINT NOT NULL,          -- 0=kg,1=ks,2=l
  kategoria_id BIGINT NULL,
  min_zasoba DECIMAL(18,3) NOT NULL DEFAULT 0,
  dph DECIMAL(5,2) NOT NULL DEFAULT 20.00,
  je_vyroba BOOLEAN NOT NULL DEFAULT FALSE,
  parent_id BIGINT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_products_ean (ean),
  INDEX ix_products_kategoria (kategoria_id),
  INDEX ix_products_parent (parent_id),
  CONSTRAINT fk_products_category FOREIGN KEY (kategoria_id) REFERENCES product_categories(id),
  CONSTRAINT fk_products_parent FOREIGN KEY (parent_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE warehouses (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  nazov VARCHAR(100) NOT NULL,
  typ TINYINT NOT NULL,    -- 0=vyrobny,1=centralny
  UNIQUE KEY uq_warehouses_nazov (nazov)
) ENGINE=InnoDB;

CREATE TABLE sklad_polozky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  sklad_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  mnozstvo DECIMAL(18,3) NOT NULL DEFAULT 0,
  priemerna_cena DECIMAL(18,4) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_sklad_produkt (sklad_id, produkt_id),
  INDEX ix_sklad_polozky_produkt (produkt_id),
  CONSTRAINT fk_sklad_polozky_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id),
  CONSTRAINT fk_sklad_polozky_produkt FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE inventory_movements (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  ts DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  sklad_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  qty_change DECIMAL(18,3) NOT NULL,
  unit_cost DECIMAL(18,4) NOT NULL,
  movement_type TINYINT NOT NULL,
  ref_table VARCHAR(50) NULL,
  ref_id BIGINT NULL,
  note VARCHAR(255) NULL,
  INDEX ix_movements_product (produkt_id, ts),
  INDEX ix_movements_sklad (sklad_id, ts),
  CONSTRAINT fk_movements_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id),
  CONSTRAINT fk_movements_produkt FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE zaznamy_prijem (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  sklad_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  datum DATETIME(6) NOT NULL,
  mnozstvo DECIMAL(18,3) NOT NULL,
  cena DECIMAL(18,4) NOT NULL,
  dodavatel VARCHAR(200) NULL,
  CONSTRAINT fk_prijem_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id),
  CONSTRAINT fk_prijem_produkt FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE recepty (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  vyrobok_id BIGINT NOT NULL,
  nazov VARCHAR(200) NOT NULL,
  UNIQUE KEY uq_recepty_vyrobok (vyrobok_id),
  CONSTRAINT fk_recepty_vyrobok FOREIGN KEY (vyrobok_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE recepty_polozky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  recept_id BIGINT NOT NULL,
  surovina_id BIGINT NOT NULL,
  mnozstvo_na_davku DECIMAL(18,3) NOT NULL,
  INDEX ix_recept_surovina (surovina_id),
  CONSTRAINT fk_recepty_polozky_recept FOREIGN KEY (recept_id) REFERENCES recepty(id),
  CONSTRAINT fk_recepty_polozky_surovina FOREIGN KEY (surovina_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE zaznamy_vyroba (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  vyrobok_id BIGINT NOT NULL,
  datum_vyroby DATETIME(6) NOT NULL,
  planovane_mnozstvo DECIMAL(18,3) NOT NULL,
  skutocne_vyrobene DECIMAL(18,3) NULL,
  stav TINYINT NOT NULL,  -- 0=VoVyrobe,1=Ukoncene,2=PrijateCakaNaTlac
  celkova_cena_surovin DECIMAL(18,4) NULL,
  CONSTRAINT fk_vyroba_vyrobok FOREIGN KEY (vyrobok_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE zaznamy_vyroba_suroviny (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  vyroba_id BIGINT NOT NULL,
  surovina_id BIGINT NOT NULL,
  mnozstvo DECIMAL(18,3) NOT NULL,
  jednotkova_cena DECIMAL(18,4) NOT NULL,
  CONSTRAINT fk_vyroba_surovina_vyroba FOREIGN KEY (vyroba_id) REFERENCES zaznamy_vyroba(id),
  CONSTRAINT fk_vyroba_surovina_produkt FOREIGN KEY (surovina_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE slicing_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  datum DATETIME(6) NOT NULL,
  source_product_id BIGINT NOT NULL,
  sliced_product_id BIGINT NOT NULL,
  source_qty DECIMAL(18,3) NOT NULL,
  sliced_qty DECIMAL(18,3) NOT NULL,
  operator VARCHAR(100) NULL,
  CONSTRAINT fk_slicing_source FOREIGN KEY (source_product_id) REFERENCES products(id),
  CONSTRAINT fk_slicing_target FOREIGN KEY (sliced_product_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE b2b_zakaznici (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  nazov_firmy VARCHAR(200) NOT NULL,
  kontakt VARCHAR(200) NULL,
  je_schvaleny BOOLEAN NOT NULL DEFAULT FALSE,
  je_admin BOOLEAN NOT NULL DEFAULT FALSE
) ENGINE=InnoDB;

CREATE TABLE b2b_cenniky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  zakaznik_id BIGINT NOT NULL,
  nazov VARCHAR(200) NOT NULL,
  platny_od DATE NOT NULL,
  platny_do DATE NULL,
  CONSTRAINT fk_cennik_zakaznik FOREIGN KEY (zakaznik_id) REFERENCES b2b_zakaznici(id)
) ENGINE=InnoDB;

CREATE TABLE b2b_cennik_polozky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  cennik_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  cena DECIMAL(18,4) NOT NULL,
  UNIQUE KEY uq_cennik_produkt (cennik_id, produkt_id),
  CONSTRAINT fk_cennik_item_cennik FOREIGN KEY (cennik_id) REFERENCES b2b_cenniky(id),
  CONSTRAINT fk_cennik_item_produkt FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE b2b_objednavky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  zakaznik_id BIGINT NOT NULL,
  datum DATETIME(6) NOT NULL,
  stav TINYINT NOT NULL, -- 0=Nova,1=Potvrdena,2=Vybavena,3=Zrusena
  celkom_bez_dph DECIMAL(18,4) NOT NULL DEFAULT 0,
  celkom_dph DECIMAL(18,4) NOT NULL DEFAULT 0,
  celkom_s_dph DECIMAL(18,4) NOT NULL DEFAULT 0,
  CONSTRAINT fk_b2bobj_zakaznik FOREIGN KEY (zakaznik_id) REFERENCES b2b_zakaznici(id)
) ENGINE=InnoDB;

CREATE TABLE b2b_objednavky_polozky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  objednavka_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  mnozstvo DECIMAL(18,3) NOT NULL,
  cena_za_jednotku DECIMAL(18,4) NOT NULL,
  dph_percent DECIMAL(5,2) NOT NULL,
  CONSTRAINT fk_b2b_items_order FOREIGN KEY (objednavka_id) REFERENCES b2b_objednavky(id),
  CONSTRAINT fk_b2b_items_product FOREIGN KEY (produkt_id) REFERENCES products(id),
  INDEX ix_b2b_items_product (produkt_id)
) ENGINE=InnoDB;

CREATE TABLE b2c_objednavky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  datum DATETIME(6) NOT NULL,
  body INT NOT NULL DEFAULT 0,
  celkom_s_dph DECIMAL(18,4) NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE b2c_objednavky_polozky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  objednavka_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  mnozstvo DECIMAL(18,3) NOT NULL,
  cena_za_jednotku DECIMAL(18,4) NOT NULL,
  dph_percent DECIMAL(5,2) NOT NULL,
  CONSTRAINT fk_b2c_items_order FOREIGN KEY (objednavka_id) REFERENCES b2c_objednavky(id),
  CONSTRAINT fk_b2c_items_product FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE inventury (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  sklad_id BIGINT NOT NULL,
  datum_start DATETIME(6) NOT NULL,
  datum_end DATETIME(6) NULL,
  poznamka VARCHAR(255) NULL,
  CONSTRAINT fk_inventury_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id)
) ENGINE=InnoDB;

CREATE TABLE inventury_polozky (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  inventura_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  systemovy_stav DECIMAL(18,3) NOT NULL,
  realny_stav DECIMAL(18,3) NOT NULL,
  rozdiel DECIMAL(18,3) NOT NULL,
  CONSTRAINT fk_inv_items_inv FOREIGN KEY (inventura_id) REFERENCES inventury(id),
  CONSTRAINT fk_inv_items_prod FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE skody (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  sklad_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  datum DATETIME(6) NOT NULL,
  mnozstvo DECIMAL(18,3) NOT NULL,
  dovod VARCHAR(200) NULL,
  CONSTRAINT fk_skody_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id),
  CONSTRAINT fk_skody_produkt FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

CREATE TABLE haccp_dokumenty (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  typ VARCHAR(100) NOT NULL,
  verzia VARCHAR(50) NOT NULL,
  file_path VARCHAR(255) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

CREATE TABLE fleet_vehicles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  znacka VARCHAR(100) NOT NULL,
  model VARCHAR(100) NULL,
  vin VARCHAR(100) NULL,
  stav_km INT NOT NULL DEFAULT 0,
  servis_info VARCHAR(255) NULL
) ENGINE=InnoDB;

CREATE TABLE hygiene_tasks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  nazov VARCHAR(200) NOT NULL,
  plan_datum DATE NOT NULL,
  stav TINYINT NOT NULL DEFAULT 0,
  poznamka VARCHAR(255) NULL
) ENGINE=InnoDB;

-- =========================
-- 2) RBAC (užívatelia/roly/permissions)
-- =========================
CREATE TABLE app_users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  email VARCHAR(200) NOT NULL,
  full_name VARCHAR(200) NOT NULL,
  pwd_hash VARCHAR(255) NULL,       -- spravuje aplikácia
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE app_roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(50) NOT NULL,
  name VARCHAR(100) NOT NULL,
  UNIQUE KEY uq_roles_code (code)
) ENGINE=InnoDB;

CREATE TABLE app_permissions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(100) NOT NULL,
  description VARCHAR(255) NULL,
  UNIQUE KEY uq_perm_code (code)
) ENGINE=InnoDB;

CREATE TABLE app_user_roles (
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  PRIMARY KEY (user_id, role_id),
  CONSTRAINT fk_ur_user FOREIGN KEY (user_id) REFERENCES app_users(id),
  CONSTRAINT fk_ur_role FOREIGN KEY (role_id) REFERENCES app_roles(id)
) ENGINE=InnoDB;

CREATE TABLE app_role_permissions (
  role_id BIGINT NOT NULL,
  permission_id BIGINT NOT NULL,
  PRIMARY KEY (role_id, permission_id),
  CONSTRAINT fk_rp_role FOREIGN KEY (role_id) REFERENCES app_roles(id),
  CONSTRAINT fk_rp_perm FOREIGN KEY (permission_id) REFERENCES app_permissions(id)
) ENGINE=InnoDB;

-- Seed: sklady
INSERT INTO warehouses(nazov, typ) VALUES ('Vyrobný', 0), ('Centrálny', 1);

-- Seed: kategórie (príklad)
INSERT INTO product_categories(name) VALUES ('Mäso'), ('Mliečne'), ('Pečivo'), ('Ovocie');

-- Seed: roly
INSERT INTO app_roles(code, name) VALUES
  ('ADMIN','Administrátor'),
  ('KANCELARIA','Kancelária'),
  ('VYROBA','Výroba'),
  ('EXPEDICIA','Expedícia'),
  ('OBCHOD','Obchod');

-- Seed: permissions
INSERT INTO app_permissions(code, description) VALUES
  ('admin','Full access'),

  -- Kancelária
  ('pricelist.b2b.manage','Správa cenníkov B2B'),
  ('pricelist.b2c.manage','Správa cenníkov B2C'),
  ('inventory.production.receipt','Príjem na výrobný sklad'),

  -- Výroba
  ('inventory.production.read','Čítanie stavu výrobného skladu'),
  ('inventory.production.consume','Manuálny výdaj surovín (výrobný)'),
  ('inventory.production.adjust','Inventúra výrobného skladu'),
  ('production.start','Začatie výroby'),

  -- Expedícia
  ('inventory.central.read','Čítanie stavu centrálneho skladu'),
  ('inventory.central.receipt','Príjem do centrálneho skladu (z výroby / manuálny)'),
  ('inventory.central.adjust','Inventúra centrálneho skladu'),
  ('slicing.create','Vytváranie príkazov na krájanie'),
  ('production.finalize_day','Finalizácia výrobných dávok (príjem do centrálneho)'),

  -- Obchod
  ('orders.b2b.manage','B2B objednávky'),
  ('orders.b2c.manage','B2C objednávky');

-- Mapovanie role -> permissions
-- ADMIN
INSERT INTO app_role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM app_roles r CROSS JOIN app_permissions p WHERE r.code='ADMIN';

-- KANCELARIA
INSERT INTO app_role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM app_roles r JOIN app_permissions p
  ON p.code IN ('pricelist.b2b.manage','pricelist.b2c.manage','inventory.production.receipt')
WHERE r.code='KANCELARIA';

-- VYROBA
INSERT INTO app_role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM app_roles r JOIN app_permissions p
  ON p.code IN ('inventory.production.read','inventory.production.consume','inventory.production.adjust','production.start')
WHERE r.code='VYROBA';

-- EXPEDICIA
INSERT INTO app_role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM app_roles r JOIN app_permissions p
  ON p.code IN ('inventory.central.read','inventory.central.receipt','inventory.central.adjust','slicing.create','production.finalize_day')
WHERE r.code='EXPEDICIA';

-- OBCHOD
INSERT INTO app_role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM app_roles r JOIN app_permissions p
  ON p.code IN ('orders.b2b.manage','orders.b2c.manage')
WHERE r.code='OBCHOD';

-- Demo users (voliteľné, zmeň emaily)
INSERT INTO app_users(email, full_name) VALUES
('admin@erp.local','Admin'),
('kancelaria@erp.local','Kancelária User'),
('vyroba@erp.local','Výroba User'),
('expedicia@erp.local','Expedícia User'),
('obchod@erp.local','Obchod User');

INSERT INTO app_user_roles(user_id, role_id)
SELECT u.id, r.id FROM app_users u JOIN app_roles r ON r.code='ADMIN' WHERE u.email='admin@erp.local';
INSERT INTO app_user_roles(user_id, role_id)
SELECT u.id, r.id FROM app_users u JOIN app_roles r ON r.code='KANCELARIA' WHERE u.email='kancelaria@erp.local';
INSERT INTO app_user_roles(user_id, role_id)
SELECT u.id, r.id FROM app_users u JOIN app_roles r ON r.code='VYROBA' WHERE u.email='vyroba@erp.local';
INSERT INTO app_user_roles(user_id, role_id)
SELECT u.id, r.id FROM app_users u JOIN app_roles r ON r.code='EXPEDICIA' WHERE u.email='expedicia@erp.local';
INSERT INTO app_user_roles(user_id, role_id)
SELECT u.id, r.id FROM app_users u JOIN app_roles r ON r.code='OBCHOD' WHERE u.email='obchod@erp.local';

-- =========================
-- 3) HELPER FUNKCIA: has_permission(user, code)
-- =========================
DELIMITER //
CREATE FUNCTION fn_user_has_permission(p_user_id BIGINT, p_perm_code VARCHAR(100))
RETURNS TINYINT(1)
READS SQL DATA
BEGIN
  DECLARE cnt INT DEFAULT 0;
  SELECT COUNT(*) INTO cnt
  FROM app_user_roles ur
  JOIN app_role_permissions rp ON rp.role_id = ur.role_id
  JOIN app_permissions pm ON pm.id = rp.permission_id
  WHERE ur.user_id = p_user_id
    AND (pm.code = p_perm_code OR pm.code = 'admin');
  RETURN (cnt > 0);
END//
DELIMITER ;

-- =========================
-- 4) PROCEDÚRY: INVENTORY
-- =========================

-- Príjem na sklad (výrobný: KANCELARIA; centrálny: EXPEDICIA)
DELIMITER //
CREATE PROCEDURE sp_inventory_receipt(
    IN p_actor_user_id BIGINT,
    IN p_sklad_id BIGINT,
    IN p_produkt_id BIGINT,
    IN p_qty DECIMAL(18,3),
    IN p_unit_cost DECIMAL(18,4),
    IN p_note VARCHAR(255)
)
BEGIN
  DECLARE v_typ TINYINT;
  DECLARE v_allowed TINYINT(1);

  IF p_qty <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Qty must be > 0';
  END IF;

  SELECT typ INTO v_typ FROM warehouses WHERE id = p_sklad_id;
  IF v_typ IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Warehouse not found'; END IF;

  IF v_typ = 0 THEN
    SET v_allowed = fn_user_has_permission(p_actor_user_id, 'inventory.production.receipt');
  ELSE
    SET v_allowed = fn_user_has_permission(p_actor_user_id, 'inventory.central.receipt');
  END IF;

  IF v_allowed = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Permission denied (receipt)';
  END IF;

  START TRANSACTION;
    -- upsert snapshot s váženým priemerom
    INSERT INTO sklad_polozky (sklad_id, produkt_id, mnozstvo, priemerna_cena)
    VALUES (p_sklad_id, p_produkt_id, p_qty, p_unit_cost)
    ON DUPLICATE KEY UPDATE
      priemerna_cena = CASE
        WHEN (sklad_polozky.mnozstvo + p_qty) <= 0 THEN 0
        ELSE ROUND(((sklad_polozky.mnozstvo * sklad_polozky.priemerna_cena) + (p_qty * p_unit_cost)) / (sklad_polozky.mnozstvo + p_qty), 4)
      END,
      mnozstvo = sklad_polozky.mnozstvo + p_qty;

    INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
    VALUES (p_sklad_id, p_produkt_id, p_qty, p_unit_cost, 0, 'zaznamy_prijem', NULL, p_note);
  COMMIT;
END//
DELIMITER ;

-- Výdaj/spotreba (len výrobný sklad pre rolu VYROBA)
DELIMITER //
CREATE PROCEDURE sp_inventory_consume(
    IN p_actor_user_id BIGINT,
    IN p_sklad_id BIGINT,
    IN p_produkt_id BIGINT,
    IN p_qty DECIMAL(18,3),
    IN p_movement_type TINYINT,      -- napr. 1=CONSUMPTION, 9=SLICING_OUT
    IN p_note VARCHAR(255)
)
BEGIN
  DECLARE v_typ TINYINT;
  DECLARE v_allowed TINYINT(1);
  DECLARE v_qty DECIMAL(18,3);
  DECLARE v_avg DECIMAL(18,4);

  IF p_qty <= 0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Qty must be > 0'; END IF;

  SELECT typ INTO v_typ FROM warehouses WHERE id = p_sklad_id;
  IF v_typ IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Warehouse not found'; END IF;

  IF v_typ = 0 THEN
    SET v_allowed = fn_user_has_permission(p_actor_user_id, 'inventory.production.consume');
  ELSE
    -- centrálna spotreba tu defaultne neumožnená
    SET v_allowed = 0;
  END IF;

  IF v_allowed = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Permission denied (consume)';
  END IF;

  START TRANSACTION;
    SELECT mnozstvo, priemerna_cena INTO v_qty, v_avg
    FROM sklad_polozky
    WHERE sklad_id=p_sklad_id AND produkt_id=p_produkt_id
    FOR UPDATE;

    IF v_qty IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='No stock snapshot'; END IF;
    IF v_qty < p_qty THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Insufficient stock'; END IF;

    UPDATE sklad_polozky
      SET mnozstvo = v_qty - p_qty
    WHERE sklad_id=p_sklad_id AND produkt_id=p_produkt_id;

    INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
    VALUES (p_sklad_id, p_produkt_id, -p_qty, v_avg, p_movement_type, NULL, NULL, p_note);
  COMMIT;
END//
DELIMITER ;

-- Inventúrna korekcia (výrobný: VYROBA, centrál: EXPEDICIA)
DELIMITER //
CREATE PROCEDURE sp_inventory_adjust(
    IN p_actor_user_id BIGINT,
    IN p_sklad_id BIGINT,
    IN p_produkt_id BIGINT,
    IN p_qty_delta DECIMAL(18,3),
    IN p_note VARCHAR(255)
)
BEGIN
  DECLARE v_typ TINYINT;
  DECLARE v_allowed TINYINT(1);
  DECLARE v_qty DECIMAL(18,3);
  DECLARE v_avg DECIMAL(18,4);

  IF p_qty_delta = 0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Delta must be != 0'; END IF;

  SELECT typ INTO v_typ FROM warehouses WHERE id = p_sklad_id;
  IF v_typ IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Warehouse not found'; END IF;

  IF v_typ = 0 THEN
    SET v_allowed = fn_user_has_permission(p_actor_user_id, 'inventory.production.adjust');
  ELSE
    SET v_allowed = fn_user_has_permission(p_actor_user_id, 'inventory.central.adjust');
  END IF;

  IF v_allowed = 0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Permission denied (adjust)'; END IF;

  START TRANSACTION;
    SELECT mnozstvo, priemerna_cena INTO v_qty, v_avg
    FROM sklad_polozky WHERE sklad_id=p_sklad_id AND produkt_id=p_produkt_id
    FOR UPDATE;

    IF v_qty IS NULL THEN
      -- ak neexistuje snapshot a ide o plusovú korekciu, založ
      IF p_qty_delta > 0 THEN
        INSERT INTO sklad_polozky(sklad_id, produkt_id, mnozstvo, priemerna_cena)
        VALUES (p_sklad_id, p_produkt_id, p_qty_delta, 0);
        SET v_avg = 0;
      ELSE
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='No stock to deduct';
      END IF;
    ELSE
      UPDATE sklad_polozky
        SET mnozstvo = v_qty + p_qty_delta
      WHERE sklad_id=p_sklad_id AND produkt_id=p_produkt_id;
    END IF;

    INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
    VALUES (p_sklad_id, p_produkt_id, p_qty_delta, v_avg, 6, 'inventura', NULL, p_note);
  COMMIT;
END//
DELIMITER ;

-- =========================
-- 5) PROCEDÚRY: EXPEDÍCIA (krájanie, finalizácia)
-- =========================

-- Krájanie (centrálny sklad): -source, +sliced s cenou zo zdroja
DELIMITER //
CREATE PROCEDURE sp_slicing_create(
    IN p_actor_user_id BIGINT,
    IN p_central_sklad_id BIGINT,
    IN p_source_product_id BIGINT,
    IN p_sliced_product_id BIGINT,
    IN p_source_qty DECIMAL(18,3),
    IN p_sliced_qty DECIMAL(18,3),
    IN p_operator VARCHAR(100)
)
BEGIN
  DECLARE v_allowed TINYINT(1);
  DECLARE v_typ TINYINT;
  DECLARE v_qty DECIMAL(18,3);
  DECLARE v_avg DECIMAL(18,4);

  IF p_source_qty <= 0 OR p_sliced_qty <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Quantities must be > 0';
  END IF;

  SELECT typ INTO v_typ FROM warehouses WHERE id = p_central_sklad_id;
  IF v_typ IS NULL OR v_typ <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Not a central warehouse'; END IF;

  SET v_allowed = fn_user_has_permission(p_actor_user_id, 'slicing.create');
  IF v_allowed = 0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Permission denied (slicing)'; END IF;

  START TRANSACTION;
    -- vyčítaj priemernú cenu source a skontroluj zásobu
    SELECT mnozstvo, priemerna_cena INTO v_qty, v_avg
    FROM sklad_polozky
    WHERE sklad_id=p_central_sklad_id AND produkt_id=p_source_product_id
    FOR UPDATE;
    IF v_qty IS NULL OR v_qty < p_source_qty THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Insufficient source stock';
    END IF;

    -- OUT zo zdroja
    UPDATE sklad_polozky
      SET mnozstvo = v_qty - p_source_qty
    WHERE sklad_id=p_central_sklad_id AND produkt_id=p_source_product_id;

    INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, note)
    VALUES (p_central_sklad_id, p_source_product_id, -p_source_qty, v_avg, 9, 'SLICING_OUT');

    -- IN do krájaného (vážený priemer s unit_cost = v_avg)
    INSERT INTO sklad_polozky(sklad_id, produkt_id, mnozstvo, priemerna_cena)
    VALUES (p_central_sklad_id, p_sliced_product_id, p_sliced_qty, v_avg)
    ON DUPLICATE KEY UPDATE
      priemerna_cena = CASE
        WHEN (sklad_polozky.mnozstvo + p_sliced_qty) <= 0 THEN 0
        ELSE ROUND(((sklad_polozky.mnozstvo * sklad_polozky.priemerna_cena) + (p_sliced_qty * v_avg)) / (sklad_polozky.mnozstvo + p_sliced_qty), 4)
      END,
      mnozstvo = sklad_polozky.mnozstvo + p_sliced_qty;

    INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, note)
    VALUES (p_central_sklad_id, p_sliced_product_id, p_sliced_qty, v_avg, 8, 'SLICING_IN');

    INSERT INTO slicing_logs(datum, source_product_id, sliced_product_id, source_qty, sliced_qty, operator)
    VALUES (CURRENT_TIMESTAMP(6), p_source_product_id, p_sliced_product_id, p_source_qty, p_sliced_qty, p_operator);
  COMMIT;
END//
DELIMITER ;

-- Finalizácia 1 dávky (Expedícia) -> príjem do centrálneho
DELIMITER //
CREATE PROCEDURE sp_production_finalize_batch(
    IN p_actor_user_id BIGINT,
    IN p_batch_id BIGINT,
    IN p_central_sklad_id BIGINT
)
BEGIN
  DECLARE v_allowed TINYINT(1);
  DECLARE v_state TINYINT;
  DECLARE v_vyrobok BIGINT;
  DECLARE v_vyrobene DECIMAL(18,3);
  DECLARE v_cena DECIMAL(18,4);
  DECLARE v_typ TINYINT;

  SELECT typ INTO v_typ FROM warehouses WHERE id = p_central_sklad_id;
  IF v_typ IS NULL OR v_typ <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Not a central warehouse'; END IF;

  SET v_allowed = fn_user_has_permission(p_actor_user_id, 'production.finalize_day');
  IF v_allowed = 0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Permission denied (finalize)'; END IF;

  SELECT stav, vyrobok_id,
         COALESCE(skutocne_vyrobene, planovane_mnozstvo) AS vyrobene,
         NULLIF(celkova_cena_surovin,0) / NULLIF(COALESCE(skutocne_vyrobene, planovane_mnozstvo),0) AS unit_cost
  INTO v_state, v_vyrobok, v_vyrobene, v_cena
  FROM zaznamy_vyroba
  WHERE id = p_batch_id
  FOR UPDATE;

  IF v_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Batch not found'; END IF;
  IF v_state <> 2 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Batch not in PrijateCakaNaTlac'; END IF;
  IF v_vyrobene IS NULL OR v_vyrobene <= 0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid produced qty'; END IF;
  IF v_cena IS NULL THEN SET v_cena = 0; END IF;

  START TRANSACTION;
    INSERT INTO sklad_polozky(sklad_id, produkt_id, mnozstvo, priemerna_cena)
    VALUES (p_central_sklad_id, v_vyrobok, v_vyrobene, v_cena)
    ON DUPLICATE KEY UPDATE
      priemerna_cena = CASE
        WHEN (sklad_polozky.mnozstvo + v_vyrobene) <= 0 THEN 0
        ELSE ROUND(((sklad_polozky.mnozstvo * sklad_polozky.priemerna_cena) + (v_vyrobene * v_cena)) / (sklad_polozky.mnozstvo + v_vyrobene), 4)
      END,
      mnozstvo = sklad_polozky.mnozstvo + v_vyrobene;

    INSERT INTO inventory_movements(sklad_id, produkt_id, qty_change, unit_cost, movement_type, ref_table, ref_id, note)
    VALUES (p_central_sklad_id, v_vyrobok, v_vyrobene, v_cena, 2, 'zaznamy_vyroba', p_batch_id, 'PRODUCTION_IN finalize');

    UPDATE zaznamy_vyroba SET stav = 1 WHERE id = p_batch_id;
  COMMIT;
END//
DELIMITER ;

-- =========================
-- 6) Užitočné pohľady (views)
-- =========================
CREATE OR REPLACE VIEW v_sklad_stav AS
SELECT sp.sklad_id, w.nazov AS sklad,
       sp.produkt_id, p.nazov AS produkt,
       sp.mnozstvo, sp.priemerna_cena
FROM sklad_polozky sp
JOIN warehouses w ON w.id = sp.sklad_id
JOIN products p ON p.id = sp.produkt_id;

CREATE OR REPLACE VIEW v_inventory_ledger AS
SELECT m.*, w.nazov AS sklad, p.nazov AS produkt
FROM inventory_movements m
JOIN warehouses w ON w.id=m.sklad_id
JOIN products p ON p.id=m.produkt_id;

-- Hotovo.
