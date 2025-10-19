USE erp;

CREATE TABLE IF NOT EXISTS sales_categories (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product_sales_categories (
  product_id BIGINT NOT NULL,
  sales_category_id INT NOT NULL,
  PRIMARY KEY(product_id, sales_category_id),
  CONSTRAINT fk_psc_prod FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT fk_psc_cat FOREIGN KEY (sales_category_id) REFERENCES sales_categories(id) ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT IGNORE INTO sales_categories(name) VALUES
('Bravčové mäso chladené'), ('Bravčové mäso mrazené'), ('Výrobky');
