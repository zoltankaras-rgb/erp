-- Krok 1: Vrátime späť pôvodnú tabuľku pre Predajné kanály
CREATE TABLE IF NOT EXISTS `profit_sales_monthly` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `report_year` INT NOT NULL,
  `report_month` INT NOT NULL,
  `sales_channel` VARCHAR(100) NOT NULL COMMENT 'Predajný kanál, napr. Coop Jednota',
  `product_ean` VARCHAR(45) NOT NULL,
  `sales_kg` DECIMAL(10,3) NULL,
  `purchase_price_net` DECIMAL(10,4) NULL,
  `purchase_price_vat` DECIMAL(10,4) NULL,
  `sell_price_net` DECIMAL(10,4) NULL,
  `sell_price_vat` DECIMAL(10,4) NULL,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `record_UNIQUE` (`report_year` ASC, `report_month` ASC, `sales_channel` ASC, `product_ean` ASC));

-- Krok 2: Pridáme nové tabuľky pre Kalkulácie (ak ešte neexistujú)
CREATE TABLE IF NOT EXISTS `profit_calculations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL COMMENT 'Názov kalkulácie, napr. Súťaž Obec XY',
  `report_year` INT NOT NULL,
  `report_month` INT NOT NULL,
  `vehicle_id` INT NULL COMMENT 'ID vozidla z tabuľky fleet_vehicles',
  `distance_km` DECIMAL(10,2) NULL DEFAULT 0.00 COMMENT 'Vzdialenosť v km pre výpočet dopravy',
  `transport_cost` DECIMAL(10,2) NULL DEFAULT 0.00 COMMENT 'Vypočítaná cena za dopravu',
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`));

CREATE TABLE IF NOT EXISTS `profit_calculation_items` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `calculation_id` INT NOT NULL,
  `product_ean` VARCHAR(45) NOT NULL,
  `estimated_kg` DECIMAL(10,3) NULL DEFAULT 0.000 COMMENT 'Predpokladané (súťažné) množstvo v kg',
  `purchase_price_net` DECIMAL(10,4) NULL COMMENT 'Automaticky načítaná nákupná/výrobná cena',
  `sell_price_net` DECIMAL(10,4) NULL COMMENT 'Ručne zadaná predajná cena pre súťaž',
  PRIMARY KEY (`id`),
  INDEX `fk_calc_id_idx` (`calculation_id` ASC),
  UNIQUE INDEX `calc_item_UNIQUE` (`calculation_id` ASC, `product_ean` ASC),
  CONSTRAINT `fk_calc_id`
    FOREIGN KEY (`calculation_id`)
    REFERENCES `profit_calculations` (`id`)
    ON DELETE CASCADE
    ON UPDATE NO ACTION);