f-- =================================================================
-- === BEZPEČNÝ MIGRAČNÝ SKRIPT PRE MODUL VOZOVÉHO PARKU (v2) ===
-- Tento skript je možné spustiť viackrát bez toho, aby spôsobil chyby.
-- =================================================================

-- Pomocná časť: Definuje procedúry na bezpečné úpravy tabuliek
DELIMITER $$

-- Procedúra na bezpečné pridanie stĺpca
DROP PROCEDURE IF EXISTS AddColumnIfNotExists$$
CREATE PROCEDURE AddColumnIfNotExists(
    IN dbName VARCHAR(64), IN tableName VARCHAR(64), IN colName VARCHAR(64), IN colDef TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT * FROM INFORMATION_SCHEMA.COLUMNS
        WHERE table_schema = dbName AND table_name = tableName AND column_name = colName
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', tableName, '` ADD COLUMN `', colName, '` ', colDef);
        PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
END$$

-- OPRAVA: Nová procedúra na bezpečné odstránenie stĺpca
DROP PROCEDURE IF EXISTS DropColumnIfExists$$
CREATE PROCEDURE DropColumnIfExists(
    IN dbName VARCHAR(64), IN tableName VARCHAR(64), IN colName VARCHAR(64)
)
BEGIN
    IF EXISTS (
        SELECT * FROM INFORMATION_SCHEMA.COLUMNS
        WHERE table_schema = dbName AND table_name = tableName AND column_name = colName
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', tableName, '` DROP COLUMN `', colName, '`');
        PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
END$$

DELIMITER ;

-- Zmena 1: Rozšírenie tabuľky vozidiel (bezpečne)
CALL AddColumnIfNotExists(DATABASE(), 'fleet_vehicles', 'default_driver', 'VARCHAR(255) NULL AFTER `type`');
CALL AddColumnIfNotExists(DATABASE(), 'fleet_vehicles', 'initial_odometer', 'INT(11) NOT NULL DEFAULT 0 AFTER `default_driver`');


-- Zmena 2: Úprava tabuľky knihy jázd (bezpečne)
CALL AddColumnIfNotExists(DATABASE(), 'fleet_logs', 'odometer_start', 'INT(11) NULL AFTER `driver`');
CALL AddColumnIfNotExists(DATABASE(), 'fleet_logs', 'odometer_end', 'INT(11) NULL AFTER `odometer_start`');
-- OPRAVA: Použijeme novú procedúru na odstránenie starého stĺpca
CALL DropColumnIfExists(DATABASE(), 'fleet_logs', 'km_driven');


-- Zmena 3: Vytvorenie novej tabuľky pre správu nákladov
CREATE TABLE IF NOT EXISTS `fleet_costs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `cost_name` VARCHAR(255) NOT NULL COMMENT 'Názov nákladu, napr. Mzda - Ján Novák',
  `cost_type` ENUM('MZDA', 'POISTENIE', 'SERVIS', 'PNEUMATIKY', 'INÉ') NOT NULL COMMENT 'Typ nákladu',
  `vehicle_id` INT NULL COMMENT 'ID vozidla, ak sa náklad viaže na konkrétne vozidlo',
  `valid_from` DATE NOT NULL COMMENT 'Dátum, od ktorého náklad platí',
  `valid_to` DATE NULL COMMENT 'Dátum, do ktorého náklad platí (NULL = platí stále)',
  `monthly_cost` DECIMAL(10, 2) NOT NULL COMMENT 'Mesačná výška nákladu v EUR',
  FOREIGN KEY (`vehicle_id`) REFERENCES `fleet_vehicles`(`id`) ON DELETE SET NULL
) COMMENT='Tabuľka pre správu variabilných a fixných nákladov na vozidlá.';


-- Príklad vloženia nákladu (iba ak je tabuľka prázdna)
INSERT INTO `fleet_costs` (`cost_name`, `cost_type`, `vehicle_id`, `valid_from`, `monthly_cost`)
SELECT * FROM (
    SELECT 'Superhrubá mzda - Ján Vodič' AS cost_name, 'MZDA' AS cost_type, NULL AS vehicle_id, '2025-01-01' AS valid_from, 2100.00 AS monthly_cost
    UNION ALL
    SELECT 'PZP - Iveco Daily', 'POISTENIE', 1, '2025-01-01', 45.00
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM `fleet_costs`);


-- Vyčistenie: Odstránenie pomocných procedúr
DROP PROCEDURE IF EXISTS AddColumnIfNotExists;
DROP PROCEDURE IF EXISTS DropColumnIfExists;

