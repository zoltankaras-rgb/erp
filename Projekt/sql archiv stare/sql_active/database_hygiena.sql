-- =================================================================
-- === SCHÉMA DATABÁZY PRE MODUL HYGIENICKÝ REŽIM ===
-- =================================================================

-- Tabuľka pre definície hygienických úloh
CREATE TABLE IF NOT EXISTS `hygiene_tasks` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_name` VARCHAR(255) NOT NULL COMMENT 'Názov úlohy, napr. Umytie podlahy',
  `location` VARCHAR(100) NOT NULL COMMENT 'Miesto výkonu, napr. Rozrábka, Balička',
  `frequency` ENUM('denne', 'tyzdenne', 'mesacne', 'stvrtronne', 'rocne') NOT NULL COMMENT 'Ako často sa má úloha vykonávať',
  `description` TEXT COMMENT 'Podrobnejší popis postupu alebo použitých prostriedkov',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Či je úloha aktívna a má sa zobrazovať v plánoch',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Definície hygienických úloh a ich frekvencia.';


-- Tabuľka pre záznamy o vykonaných hygienických úkonoch
CREATE TABLE IF NOT EXISTS `hygiene_log` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` INT NOT NULL COMMENT 'Odkaz na ID z tabuľky hygiene_tasks',
  `completion_date` DATE NOT NULL COMMENT 'Dátum, kedy bola úloha reálne vykonaná',
  `user_id` INT NOT NULL COMMENT 'ID interného používateľa, ktorý úlohu vykonal',
  `user_fullname` VARCHAR(255) COMMENT 'Celé meno používateľa pre jednoduchšie zobrazenie',
  `notes` TEXT COMMENT 'Poznámky k vykonaniu (napr. zistené nedostatky)',
  `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Presný čas a dátum záznamu',
  PRIMARY KEY (`id`),
  FOREIGN KEY (`task_id`) REFERENCES `hygiene_tasks` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`user_id`) REFERENCES `internal_users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Záznamy o vykonaných hygienických úkonoch.';
