-- Tento skript spusti v MySQL Workbench IBA RAZ.
-- Vytvorí všetky potrebné tabuľky a stĺpce pre B2C cenník a vernostný systém.

-- Vytvorenie tabuľky pre B2C cenník (OPRAVUJE PÔVODNÚ CHYBU)
CREATE TABLE IF NOT EXISTS b2c_cennik_polozky (
id INT NOT NULL AUTO_INCREMENT,
ean_produktu VARCHAR(45) NOT NULL,
cena_bez_dph DECIMAL(10,4) NOT NULL,
je_v_akcii BOOLEAN NOT NULL DEFAULT FALSE,
akciova_cena_bez_dph DECIMAL(10,4) NULL DEFAULT NULL,
PRIMARY KEY (id),
UNIQUE INDEX ean_produktu_UNIQUE (ean_produktu ASC) VISIBLE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pridanie stĺpca pre vernostné body k zákazníkom
-- Skript skontroluje, či stĺpec už existuje, aby sa predišlo chybe pri opakovanom spustení.
SET @db = 'vyrobny_system';
SET @tbl = 'b2b_zakaznici';
SET @col = 'vernostne_body';
SET @sql = CONCAT('ALTER TABLE ', @tbl, ' ADD COLUMN ', @col, ' INT NOT NULL DEFAULT 0 AFTER gdpr_suhlas');
SELECT IF(
(SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = @db AND table_name = @tbl AND column_name = @col) > 0,
"SELECT 'Stĺpec vernostne_body už existuje.'",
@sql
) INTO @sql;
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Úprava B2C objednávok pre sledovanie pripísaných bodov
SET @tbl2 = 'b2c_objednavky';
SET @col2 = 'datum_pripisania_bodov';
SET @sql2 = CONCAT('ALTER TABLE ', @tbl2, ' ADD COLUMN ', @col2, ' DATETIME NULL DEFAULT NULL AFTER celkova_suma_s_dph');
SELECT IF(
(SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = @db AND table_name = @tbl2 AND column_name = @col2) > 0,
"SELECT 'Stĺpec datum_pripisania_bodov už existuje.'",
@sql2
) INTO @sql2;
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- Nová tabuľka pre definíciu vernostných odmien
CREATE TABLE IF NOT EXISTS b2c_vernostne_odmeny (
id INT NOT NULL AUTO_INCREMENT,
nazov_odmeny VARCHAR(255) NOT NULL,
potrebne_body INT NOT NULL,
je_aktivna BOOLEAN NOT NULL DEFAULT TRUE,
PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;