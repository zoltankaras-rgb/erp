-- Tabuľka pre evidenciu čistiacich a dezinfekčných prostriedkov
CREATE TABLE IF NOT EXISTS `hygiene_agents` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `agent_name` VARCHAR(255) NOT NULL,
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `agent_name_UNIQUE` (`agent_name` ASC));

-- Úprava tabuľky s úlohami: pridanie predvolených hodnôt
ALTER TABLE `hygiene_tasks` 
ADD COLUMN `default_agent_id` INT NULL AFTER `description`,
ADD COLUMN `default_concentration` VARCHAR(50) NULL COMMENT 'napr. 2%' AFTER `default_agent_id`,
ADD COLUMN `default_exposure_time` VARCHAR(50) NULL COMMENT 'napr. 15 min' AFTER `default_concentration`,
ADD INDEX `fk_hygiene_tasks_agent_idx` (`default_agent_id` ASC);

-- Bezpečná úprava pre pridanie cudzieho kľúča, ak ešte neexistuje
SET @fk_exists = (SELECT COUNT(1) FROM information_schema.key_column_usage WHERE table_schema = DATABASE() AND table_name = 'hygiene_tasks' AND constraint_name = 'fk_hygiene_tasks_agent');
SET @sql = IF(@fk_exists = 0, 'ALTER TABLE `hygiene_tasks` ADD CONSTRAINT `fk_hygiene_tasks_agent` FOREIGN KEY (`default_agent_id`) REFERENCES `hygiene_agents` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;', 'SELECT "Cudzí kľúč už existuje." as message;');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Úprava tabuľky s logmi: pridanie detailných záznamov a kontroly
ALTER TABLE `hygiene_log` 
ADD COLUMN `agent_id` INT NULL AFTER `user_fullname`,
ADD COLUMN `concentration` VARCHAR(50) NULL AFTER `agent_id`,
ADD COLUMN `exposure_time` VARCHAR(50) NULL AFTER `concentration`,
ADD COLUMN `checked_by_user_id` INT NULL AFTER `notes`,
ADD COLUMN `checked_by_fullname` VARCHAR(255) NULL AFTER `checked_by_user_id`,
ADD COLUMN `checked_at` DATETIME NULL AFTER `checked_by_fullname`,
ADD INDEX `fk_hygiene_log_agent_idx` (`agent_id` ASC);

-- Bezpečná úprava pre pridanie cudzieho kľúča, ak ešte neexistuje
SET @fk_exists_log = (SELECT COUNT(1) FROM information_schema.key_column_usage WHERE table_schema = DATABASE() AND table_name = 'hygiene_log' AND constraint_name = 'fk_hygiene_log_agent');
SET @sql_log = IF(@fk_exists_log = 0, 'ALTER TABLE `hygiene_log` ADD CONSTRAINT `fk_hygiene_log_agent` FOREIGN KEY (`agent_id`) REFERENCES `hygiene_agents` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;', 'SELECT "Cudzí kľúč v logu už existuje." as message;');
PREPARE stmt_log FROM @sql_log;
EXECUTE stmt_log;
DEALLOCATE PREPARE stmt_log;

