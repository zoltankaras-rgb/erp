-- Tabuľka pre mesačné záznamy o spotrebe elektriny
CREATE TABLE IF NOT EXISTS `costs_energy_electricity` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `record_year` INT NOT NULL,
  `record_month` INT NOT NULL,
  `odpis_vse` DECIMAL(10,2) NULL,
  `fakturacia_vse` DECIMAL(10,2) NULL,
  `rozdiel_vse` DECIMAL(10,2) NULL,
  `odpis_vse_nt` DECIMAL(10,2) NULL,
  `fakturacia_vse_nt` DECIMAL(10,2) NULL,
  `rozdiel_vse_nt` DECIMAL(10,2) NULL,
  `faktura_s_dph` DECIMAL(10,2) NULL,
  `final_cost` DECIMAL(10,2) NULL COMMENT 'Vypočítaná hodnota FA s dph / 4,68',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `electricity_period_UNIQUE` (`record_year` ASC, `record_month` ASC));

-- Tabuľka pre mesačné záznamy o spotrebe plynu
CREATE TABLE IF NOT EXISTS `costs_energy_gas` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `record_year` INT NOT NULL,
  `record_month` INT NOT NULL,
  `stav_odpisany` DECIMAL(10,3) NULL,
  `stav_fakturovany` DECIMAL(10,3) NULL,
  `rozdiel_m3` DECIMAL(10,3) NULL,
  `spal_teplo` DECIMAL(10,4) NULL,
  `obj_koeficient` DECIMAL(10,4) NULL,
  `spotreba_kwh` DECIMAL(10,3) NULL,
  `nakup_plynu_eur` DECIMAL(10,2) NULL,
  `distribucia_eur` DECIMAL(10,2) NULL,
  `straty_eur` DECIMAL(10,2) NULL,
  `poplatok_okte_eur` DECIMAL(10,2) NULL,
  `spolu_bez_dph` DECIMAL(10,2) NULL,
  `dph` DECIMAL(10,2) NULL,
  `spolu_s_dph` DECIMAL(10,2) NULL,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `gas_period_UNIQUE` (`record_year` ASC, `record_month` ASC));

-- Tabuľka pre mesačné náklady na ľudské zdroje
CREATE TABLE IF NOT EXISTS `costs_hr` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `record_year` INT NOT NULL,
  `record_month` INT NOT NULL,
  `total_salaries` DECIMAL(12,2) NULL COMMENT 'Celková suma vyplatená na mzdách',
  `total_levies` DECIMAL(12,2) NULL COMMENT 'Celková suma odvodov',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `hr_period_UNIQUE` (`record_year` ASC, `record_month` ASC));

-- Tabuľka pre kategórie prevádzkových nákladov
CREATE TABLE IF NOT EXISTS `costs_categories` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `name_UNIQUE` (`name` ASC));

-- Hlavná tabuľka pre všetky ostatné prevádzkové náklady
CREATE TABLE IF NOT EXISTS `costs_items` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entry_date` DATE NOT NULL,
  `category_id` INT NOT NULL,
  `name` VARCHAR(255) NOT NULL COMMENT 'Názov položky, napr. Rukavice, Toner, Internet',
  `description` TEXT NULL,
  `amount_net` DECIMAL(12,2) NOT NULL COMMENT 'Suma bez DPH',
  `is_recurring` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 pre opakujúci sa náklad, 0 pre jednorazový',
  PRIMARY KEY (`id`),
  INDEX `fk_category_id_idx` (`category_id` ASC),
  CONSTRAINT `fk_category_id`
    FOREIGN KEY (`category_id`)
    REFERENCES `costs_categories` (`id`)
    ON DELETE RESTRICT
    ON UPDATE NO ACTION);