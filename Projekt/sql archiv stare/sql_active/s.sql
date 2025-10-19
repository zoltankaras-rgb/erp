-- Tento skript bezpečne zmaže staré tabuľky a vytvorí nové,
-- s vylepšenými pravidlami pre automatické mazanie prepojených dát.
-- Je bezpečné ho spustiť aj viackrát.

SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS b2b_objednavky_polozky;
DROP TABLE IF EXISTS b2b_objednavky;
DROP TABLE IF EXISTS b2b_cennik_polozky;
DROP TABLE IF EXISTS b2b_zakaznik_cennik;
DROP TABLE IF EXISTS b2b_cenniky;
DROP TABLE IF EXISTS b2b_zakaznici;
SET FOREIGN_KEY_CHECKS=1;

-- Tabuľka pre B2B zákazníkov
CREATE TABLE b2b_zakaznici (
id INT NOT NULL AUTO_INCREMENT,
zakaznik_id VARCHAR(50) NOT NULL UNIQUE,
nazov_firmy VARCHAR(255) NOT NULL,
adresa VARCHAR(255) NULL,
email VARCHAR(255) NOT NULL UNIQUE,
telefon VARCHAR(50) NULL,
heslo_hash VARCHAR(255) NOT NULL,
heslo_salt VARCHAR(255) NOT NULL,
je_schvaleny BOOLEAN NOT NULL DEFAULT FALSE,
je_admin BOOLEAN NOT NULL DEFAULT FALSE,
datum_registracie TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
reset_token VARCHAR(255) NULL,
reset_token_expiry DATETIME NULL,
PRIMARY KEY (id)
);

-- Tabuľka pre cenníky
CREATE TABLE b2b_cenniky (
id INT NOT NULL AUTO_INCREMENT,
nazov_cennika VARCHAR(255) NOT NULL UNIQUE,
PRIMARY KEY (id)
);

-- Prepojovacia tabuľka medzi zákazníkmi a cenníkmi
CREATE TABLE b2b_zakaznik_cennik (
zakaznik_id INT NOT NULL,
cennik_id INT NOT NULL,
PRIMARY KEY (zakaznik_id, cennik_id),
FOREIGN KEY (zakaznik_id) REFERENCES b2b_zakaznici(id) ON DELETE CASCADE,
FOREIGN KEY (cennik_id) REFERENCES b2b_cenniky(id) ON DELETE CASCADE
);

-- Tabuľka pre položky v cenníkoch
CREATE TABLE b2b_cennik_polozky (
id INT NOT NULL AUTO_INCREMENT,
cennik_id INT NOT NULL,
ean_produktu VARCHAR(100) NOT NULL,
cena DECIMAL(10, 2) NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY (cennik_id) REFERENCES b2b_cenniky(id) ON DELETE CASCADE
);

-- Tabuľka pre objednávky
CREATE TABLE b2b_objednavky (
id INT NOT NULL AUTO_INCREMENT,
zakaznik_id INT NOT NULL,
cislo_objednavky VARCHAR(100) NOT NULL UNIQUE,
datum_objednavky TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
pozadovany_datum_dodania DATE NULL,
poznamka TEXT NULL,
celkova_suma DECIMAL(10, 2) NOT NULL,
status VARCHAR(50) NOT NULL DEFAULT 'Prijatá',
PRIMARY KEY (id),
FOREIGN KEY (zakaznik_id) REFERENCES b2b_zakaznici(id) ON DELETE CASCADE
);

-- Tabuľka pre položky v objednávkach
CREATE TABLE b2b_objednavky_polozky (
id INT NOT NULL AUTO_INCREMENT,
objednavka_id INT NOT NULL,
ean_produktu VARCHAR(100) NOT NULL,
nazov_produktu VARCHAR(255) NOT NULL,
mnozstvo DECIMAL(10, 2) NOT NULL,
cena_za_jednotku DECIMAL(10, 2) NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY (objednavka_id) REFERENCES b2b_objednavky(id) ON DELETE CASCADE
);