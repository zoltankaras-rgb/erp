USE erp;

CREATE TABLE IF NOT EXISTS suppliers (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  ico VARCHAR(20) NULL,
  dic VARCHAR(20) NULL,
  ic_dph VARCHAR(20) NULL,
  email VARCHAR(255) NULL,
  phone VARCHAR(50) NULL,
  address VARCHAR(255) NULL,
  note TEXT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product_suppliers (
  product_id BIGINT NOT NULL,
  supplier_id BIGINT NOT NULL,
  supplier_code VARCHAR(100) NULL,
  last_price DECIMAL(18,4) NULL,
  preferred TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY(product_id, supplier_id),
  CONSTRAINT fk_ps_prod FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT fk_ps_supp FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
) ENGINE=InnoDB;
