-- Tento skript zabezpečí, že vaša databáza má správnu štruktúru pre modul vozového parku.
-- Je bezpečné ho spustiť, aj keď tabuľky už existujú.

CREATE TABLE IF NOT EXISTS `fleet_vehicles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT 'Názov vozidla, napr. Iveco Daily',
  `license_plate` varchar(15) NOT NULL COMMENT 'ŠPZ vozidla',
  `type` varchar(50) DEFAULT NULL COMMENT 'Typ vozidla, napr. Dodávka',
  `default_driver` varchar(100) DEFAULT NULL COMMENT 'Meno predvoleného šoféra',
  `initial_odometer` int NOT NULL DEFAULT '0' COMMENT 'Počiatočný stav tachometra pri zaradení',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '1 = aktívne, 0 = neaktívne',
  PRIMARY KEY (`id`),
  UNIQUE KEY `license_plate` (`license_plate`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Zoznam všetkých vozidiel vo vozovom parku.';


CREATE TABLE IF NOT EXISTS `fleet_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `vehicle_id` int NOT NULL,
  `log_date` date NOT NULL,
  `driver` varchar(100) DEFAULT NULL,
  `start_odometer` int DEFAULT NULL,
  `end_odometer` int DEFAULT NULL,
  `km_driven` int DEFAULT NULL,
  `goods_out_kg` decimal(10,2) DEFAULT NULL,
  `goods_in_kg` decimal(10,2) DEFAULT NULL,
  `delivery_notes_count` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `vehicle_date_unique` (`vehicle_id`,`log_date`),
  KEY `fk_logs_vehicle_id` (`vehicle_id`),
  CONSTRAINT `fk_logs_vehicle_id` FOREIGN KEY (`vehicle_id`) REFERENCES `fleet_vehicles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Denné záznamy z knihy jázd.';


CREATE TABLE IF NOT EXISTS `fleet_refueling` (
  `id` int NOT NULL AUTO_INCREMENT,
  `vehicle_id` int NOT NULL,
  `refueling_date` date NOT NULL,
  `driver` varchar(100) DEFAULT NULL,
  `liters` decimal(10,2) NOT NULL,
  `total_price` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_refueling_vehicle_id` (`vehicle_id`),
  CONSTRAINT `fk_refueling_vehicle_id` FOREIGN KEY (`vehicle_id`) REFERENCES `fleet_vehicles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Záznamy o tankovaní.';


CREATE TABLE IF NOT EXISTS `fleet_costs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `cost_name` varchar(255) NOT NULL COMMENT 'Názov nákladu, napr. Mzda - Ján Novák',
  `cost_type` enum('MZDA','POISTENIE','SERVIS','PNEUMATIKY','DIALNICNA','SKODA','INE') NOT NULL COMMENT 'Typ nákladu',
  `vehicle_id` int DEFAULT NULL COMMENT 'ID vozidla, ak sa náklad viaže na konkrétne vozidlo (NULL = všeobecný náklad)',
  `valid_from` date NOT NULL COMMENT 'Dátum, od ktorého náklad platí',
  `valid_to` date DEFAULT NULL COMMENT 'Dátum, do ktorého náklad platí (NULL = platí stále)',
  `monthly_cost` decimal(10,2) NOT NULL COMMENT 'Mesačná výška nákladu v EUR',
  PRIMARY KEY (`id`),
  KEY `fk_costs_vehicle_id` (`vehicle_id`),
  CONSTRAINT `fk_costs_vehicle_id` FOREIGN KEY (`vehicle_id`) REFERENCES `fleet_vehicles` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Tabuľka pre správu variabilných a fixných nákladov.';
