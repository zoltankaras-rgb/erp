-- Nová tabuľka na zaznamenávanie inventúrnych rozdielov finálnych produktov
CREATE TABLE IF NOT EXISTS `inventurne_rozdiely_produkty` (
  `id` int NOT NULL AUTO_INCREMENT,
  `datum` datetime NOT NULL,
  `ean_produktu` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `nazov_produktu` varchar(150) COLLATE utf8mb4_general_ci NOT NULL,
  `predajna_kategoria` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `systemovy_stav_kg` decimal(10,3) NOT NULL,
  `realny_stav_kg` decimal(10,3) NOT NULL,
  `rozdiel_kg` decimal(10,3) NOT NULL,
  `hodnota_rozdielu_eur` decimal(10,2) NOT NULL,
  `pracovnik` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ean_produktu` (`ean_produktu`),
  KEY `datum` (`datum`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
