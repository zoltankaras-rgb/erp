CALL add_col_if_missing('fleet_vehicles','license_plate',
  'ALTER TABLE fleet_vehicles ADD COLUMN license_plate VARCHAR(32) AFTER id');

CALL add_col_if_missing('fleet_vehicles','name',
  'ALTER TABLE fleet_vehicles ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT '''' AFTER license_plate');

CALL add_col_if_missing('fleet_vehicles','type',
  'ALTER TABLE fleet_vehicles ADD COLUMN type VARCHAR(50) NULL AFTER name');

CALL add_col_if_missing('fleet_vehicles','default_driver',
  'ALTER TABLE fleet_vehicles ADD COLUMN default_driver VARCHAR(100) NULL AFTER type');

CALL add_col_if_missing('fleet_vehicles','initial_odometer',
  'ALTER TABLE fleet_vehicles ADD COLUMN initial_odometer INT NOT NULL DEFAULT 0 AFTER default_driver');

CALL add_col_if_missing('fleet_vehicles','is_active',
  'ALTER TABLE fleet_vehicles ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER initial_odometer');

CALL add_col_if_missing('fleet_vehicles','created_at',
  'ALTER TABLE fleet_vehicles ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER is_active');

-- unikátny index na ŠPZ (ak ešte nie je)
CALL add_idx_if_missing('fleet_vehicles','uq_fleet_lp',
  'ALTER TABLE fleet_vehicles ADD UNIQUE KEY uq_fleet_lp (license_plate)');
