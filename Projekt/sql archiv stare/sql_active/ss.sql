-- 1) Vytvor tabuľku b2b_retail_chains, ak neexistuje
CREATE TABLE IF NOT EXISTS `b2b_retail_chains` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) COLLATE utf8mb4_slovak_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_slovak_ci;

-- 2) Vytvor tabuľku b2b_promotions, ak neexistuje
CREATE TABLE IF NOT EXISTS `b2b_promotions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `chain_id` INT NOT NULL,
  `ean` VARCHAR(255) COLLATE utf8mb4_slovak_ci NOT NULL,
  `product_name` VARCHAR(255) COLLATE utf8mb4_slovak_ci NOT NULL,
  `start_date` DATE NOT NULL,
  `end_date` DATE NOT NULL,
  `delivery_start_date` DATE DEFAULT NULL,
  `sale_price_net` DECIMAL(10,4) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `chain_id` (`chain_id`),
  CONSTRAINT `b2b_promotions_ibfk_1` FOREIGN KEY (`chain_id`) REFERENCES `b2b_retail_chains` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_slovak_ci;

-- 3) Dopln chýbajúce stĺpce (okrem primárneho kľúča)
ALTER TABLE `b2b_retail_chains`
  ADD COLUMN IF NOT EXISTS `name` VARCHAR(255) COLLATE utf8mb4_slovak_ci NOT NULL;

ALTER TABLE `b2b_promotions`
  ADD COLUMN IF NOT EXISTS `chain_id` INT NOT NULL,
  ADD COLUMN IF NOT EXISTS `ean` VARCHAR(255) COLLATE utf8mb4_slovak_ci NOT NULL,
  ADD COLUMN IF NOT EXISTS `product_name` VARCHAR(255) COLLATE utf8mb4_slovak_ci NOT NULL,
  ADD COLUMN IF NOT EXISTS `start_date` DATE NOT NULL,
  ADD COLUMN IF NOT EXISTS `end_date` DATE NOT NULL,
  ADD COLUMN IF NOT EXISTS `delivery_start_date` DATE DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `sale_price_net` DECIMAL(10,4) NOT NULL;

-- 4) Na stĺpce s PRIMARY KEY a AUTO_INCREMENT treba ísť podmienkovo
--    (kontrola cez information_schema, lebo IF NOT EXISTS nefunguje na PRIMARY KEY)

-- Ak id stĺpec neexistuje v b2b_retail_chains, pridaj ho
SET @col_exists := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'b2b_retail_chains'
    AND COLUMN_NAME = 'id'
);
SET @sql := IF(@col_exists = 0,
  'ALTER TABLE `b2b_retail_chains` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY;',
  'SELECT "Column id already exists in b2b_retail_chains";'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Ak id stĺpec neexistuje v b2b_promotions, pridaj ho
SET @col_exists := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'b2b_promotions'
    AND COLUMN_NAME = 'id'
);
SET @sql := IF(@col_exists = 0,
  'ALTER TABLE `b2b_promotions` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY;',
  'SELECT "Column id already exists in b2b_promotions";'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
