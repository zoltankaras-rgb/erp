-- použij správnu DB
USE erp_new;

-- Tabuľka výrobných kategórií (ak už je, nič sa nemení)
CREATE TABLE IF NOT EXISTS production_categories (
  id   INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Bezchybný, idempotentný PATCH ako procedúra
DELIMITER $$

DROP PROCEDURE IF EXISTS _patch_prodmeta $$
CREATE PROCEDURE _patch_prodmeta()
BEGIN
  DECLARE v INT DEFAULT 0;

  -- products.production_category_id
  SELECT COUNT(*) INTO v
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'products'
    AND COLUMN_NAME  = 'production_category_id';
  IF v = 0 THEN
    ALTER TABLE products
      ADD COLUMN production_category_id INT NULL AFTER kategoria_id;
  END IF;

  -- products.production_unit  (0=kg, 1=ks)
  SELECT COUNT(*) INTO v
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'products'
    AND COLUMN_NAME  = 'production_unit';
  IF v = 0 THEN
    ALTER TABLE products
      ADD COLUMN production_unit TINYINT NOT NULL DEFAULT 0 AFTER jednotka;
  END IF;

  -- products.piece_weight_g (gramy, ak production_unit=1)
  SELECT COUNT(*) INTO v
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'products'
    AND COLUMN_NAME  = 'piece_weight_g';
  IF v = 0 THEN
    ALTER TABLE products
      ADD COLUMN piece_weight_g INT NULL AFTER production_unit;
  END IF;

  -- FK: products.production_category_id -> production_categories(id), len ak ešte neexistuje
  SELECT COUNT(*) INTO v
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA           = DATABASE()
    AND TABLE_NAME             = 'products'
    AND COLUMN_NAME            = 'production_category_id'
    AND REFERENCED_TABLE_NAME  = 'production_categories';
  IF v = 0 THEN
    ALTER TABLE products
      ADD CONSTRAINT fk_products_prodcat
      FOREIGN KEY (production_category_id)
      REFERENCES production_categories(id)
      ON DELETE SET NULL;
  END IF;
END $$
DELIMITER ;

CALL _patch_prodmeta();
DROP PROCEDURE _patch_prodmeta;

-- seed (ak už sú, ponechá)
INSERT INTO production_categories(name) VALUES
('Párkoviny'),('Paštéty'),('Solené mäsá')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- rýchla kontrola
SELECT COLUMN_NAME, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE()
  AND TABLE_NAME='products'
  AND COLUMN_NAME IN ('production_category_id','production_unit','piece_weight_g');

SELECT CONSTRAINT_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA=DATABASE()
  AND TABLE_NAME='products'
  AND COLUMN_NAME='production_category_id'
  AND REFERENCED_TABLE_NAME='production_categories';
