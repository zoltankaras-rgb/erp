-- Vozidlá
CREATE TABLE IF NOT EXISTS fleet_vehicles (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  license_plate VARCHAR(32) NOT NULL,
  name VARCHAR(100) NOT NULL,
  type VARCHAR(50),
  default_driver VARCHAR(100),
  initial_odometer INT NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_fleet_lp (license_plate)
) ENGINE=InnoDB;

-- Denné záznamy (kniha jázd)
CREATE TABLE IF NOT EXISTS fleet_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  vehicle_id BIGINT NOT NULL,
  log_date DATE NOT NULL,
  driver VARCHAR(100),
  start_odometer INT,
  end_odometer INT,
  km_driven INT,
  goods_out_kg DECIMAL(12,3),
  goods_in_kg DECIMAL(12,3),
  delivery_notes_count INT,
  UNIQUE KEY uq_fleet_log_vehicle_date (vehicle_id, log_date),
  KEY idx_fleet_log_vehicle (vehicle_id, log_date),
  CONSTRAINT fk_fleet_log_vehicle FOREIGN KEY (vehicle_id) REFERENCES fleet_vehicles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Tankovania (PLURAL!)
CREATE TABLE IF NOT EXISTS fleet_refuelings (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  vehicle_id BIGINT NOT NULL,
  refueling_date DATE NOT NULL,
  driver VARCHAR(100),
  liters DECIMAL(10,3) NOT NULL,
  price_per_liter DECIMAL(10,4),
  total_price DECIMAL(12,2),
  KEY idx_fr_vehicle_date (vehicle_id, refueling_date),
  CONSTRAINT fk_fr_vehicle FOREIGN KEY (vehicle_id) REFERENCES fleet_vehicles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Náklady
CREATE TABLE IF NOT EXISTS fleet_costs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  cost_name VARCHAR(120) NOT NULL,
  cost_type VARCHAR(30) NOT NULL,
  monthly_cost DECIMAL(12,2) NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE NULL,
  vehicle_id BIGINT NULL,
  KEY idx_fc_valid (valid_from, valid_to),
  KEY idx_fc_vehicle (vehicle_id),
  CONSTRAINT fk_fc_vehicle FOREIGN KEY (vehicle_id) REFERENCES fleet_vehicles(id) ON DELETE SET NULL
) ENGINE=InnoDB;
