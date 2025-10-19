
-- Spustite ho celý naraz.

USE vyrobny_system;

CREATE TABLE sklad (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nazov VARCHAR(255) NOT NULL UNIQUE,
  typ VARCHAR(100),
  mnozstvo DECIMAL(10, 3) DEFAULT 0.000,
  nakupna_cena DECIMAL(10, 4) DEFAULT 0.0000,
  min_zasoba DECIMAL(10, 3) DEFAULT 0.000
);

CREATE TABLE katalog_produktov (
  ean VARCHAR(50) PRIMARY KEY,
  nazov_vyrobku VARCHAR(255) NOT NULL,
  mj VARCHAR(20) DEFAULT 'kg',
  kategoria_pre_recepty VARCHAR(100),
  typ_produktu VARCHAR(50),
  vaha_balenia_g DECIMAL(10, 2) DEFAULT 0.00,
  zdrojovy_ean VARCHAR(50) NULL
);

CREATE TABLE recepty (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nazov_vyrobku VARCHAR(255) NOT NULL,
  nazov_suroviny VARCHAR(255) NOT NULL,
  mnozstvo_na_davku_kg DECIMAL(10, 4) NOT NULL
);

CREATE TABLE zaznamy_vyroba (
  id_davky VARCHAR(255) PRIMARY KEY,
  stav VARCHAR(100),
  datum_vyroby DATETIME,
  nazov_vyrobku VARCHAR(255),
  planovane_mnozstvo_kg DECIMAL(10, 2),
  realne_mnozstvo_kg DECIMAL(10, 2),
  realne_mnozstvo_ks INT,
  celkova_cena_surovin DECIMAL(10, 2),
  datum_spustenia DATETIME,
  datum_ukoncenia DATETIME,
  zmeneny_recept VARCHAR(10),
  detaily_zmeny TEXT
);

CREATE TABLE zaznamy_prijem (
  id INT AUTO_INCREMENT PRIMARY KEY,
  datum DATETIME,
  nazov_suroviny VARCHAR(255),
  mnozstvo DECIMAL(10, 3),
  cena_za_jednotku DECIMAL(10, 4),
  poznamka VARCHAR(255)
);