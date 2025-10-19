-- ============ HYGIENA / HACCP — FK FIX (bez procedúr) ============

/* 0) Základné tabuľky (ak už existujú, warnings ignoruj) */
CREATE TABLE IF NOT EXISTS hygiene_agents (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  agent_name VARCHAR(120) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS hygiene_tasks (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_name VARCHAR(200) NOT NULL,
  location VARCHAR(120) NOT NULL,
  frequency ENUM('denne','tyzdenne','mesacne','stvrtronne','rocne') NOT NULL DEFAULT 'denne',
  description TEXT NULL,
  default_agent_id BIGINT NULL,
  default_concentration VARCHAR(60) NULL,
  default_exposure_time VARCHAR(60) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL,
  INDEX idx_ht_loc (location),
  INDEX idx_ht_active (is_active),
  CONSTRAINT fk_ht_agent FOREIGN KEY (default_agent_id) REFERENCES hygiene_agents(id) ON DELETE SET NULL
) ENGINE=InnoDB;

/* 1) hygiene_log (ak chýba) – bez FK */
CREATE TABLE IF NOT EXISTS hygiene_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id BIGINT NULL,
  plan_date DATE NOT NULL,
  start_time DATETIME NULL,
  exposure_end DATETIME NULL,
  rinse_end DATETIME NULL,
  end_time DATETIME NULL,
  performed_by VARCHAR(120) NULL,
  agent_id BIGINT NULL,
  concentration VARCHAR(60) NULL,
  exposure_time VARCHAR(60) NULL,
  notes TEXT NULL,
  checked_by_fullname VARCHAR(120) NULL,
  checked_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_hl_task_date (task_id, plan_date)
) ENGINE=InnoDB;

/* 1a) Uisti sa, že stĺpce existujú */
SET @sql := IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hygiene_log' AND COLUMN_NAME='task_id')=0,
  'ALTER TABLE hygiene_log ADD COLUMN task_id BIGINT NULL',
  'SELECT 1'
); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hygiene_log' AND COLUMN_NAME='agent_id')=0,
  'ALTER TABLE hygiene_log ADD COLUMN agent_id BIGINT NULL',
  'SELECT 1'
); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

/* 2) Zhoď existujúce FK, ak sú */
SET @sql := IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
          WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='hygiene_log'
            AND CONSTRAINT_TYPE='FOREIGN KEY' AND CONSTRAINT_NAME='fk_hl_task'),
  'ALTER TABLE hygiene_log DROP FOREIGN KEY fk_hl_task', 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
          WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='hygiene_log'
            AND CONSTRAINT_TYPE='FOREIGN KEY' AND CONSTRAINT_NAME='fk_hl_agent'),
  'ALTER TABLE hygiene_log DROP FOREIGN KEY fk_hl_agent', 'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

/* 3) Zisti presný COLUMN_TYPE referenčných id (vrátane unsigned) */
SELECT COLUMN_TYPE INTO @tasks_coltype
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hygiene_tasks' AND COLUMN_NAME='id' LIMIT 1;

SELECT COLUMN_TYPE INTO @agents_coltype
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hygiene_agents' AND COLUMN_NAME='id' LIMIT 1;

/* 4) Zosúlad typy v hygiene_log – OBE NULLABLE
      (pre ON DELETE SET NULL MUSÍ byť child column NULLable) */
SET @sql := CONCAT('ALTER TABLE hygiene_log MODIFY COLUMN task_id ', @tasks_coltype, ' NULL');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := CONCAT('ALTER TABLE hygiene_log MODIFY COLUMN agent_id ', @agents_coltype, ' NULL');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

/* 4a) Prečisti neplatné referencie (inak by pridanie FK padlo) */
UPDATE hygiene_log hl
LEFT JOIN hygiene_tasks ht ON hl.task_id = ht.id
SET hl.task_id = NULL
WHERE hl.task_id IS NOT NULL AND ht.id IS NULL;

UPDATE hygiene_log hl
LEFT JOIN hygiene_agents ha ON hl.agent_id = ha.id
SET hl.agent_id = NULL
WHERE hl.agent_id IS NOT NULL AND ha.id IS NULL;

/* 5) Pridaj FK iba ak chýbajú */
SET @sql := IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
          WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='fk_hl_task'),
  'SELECT 1',
  'ALTER TABLE `hygiene_log` ADD CONSTRAINT `fk_hl_task` FOREIGN KEY (`task_id`) REFERENCES `hygiene_tasks`(`id`) ON DELETE CASCADE'
);
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
          WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='fk_hl_agent'),
  'SELECT 1',
  'ALTER TABLE `hygiene_log` ADD CONSTRAINT `fk_hl_agent` FOREIGN KEY (`agent_id`) REFERENCES `hygiene_agents`(`id`) ON DELETE SET NULL'
);
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
