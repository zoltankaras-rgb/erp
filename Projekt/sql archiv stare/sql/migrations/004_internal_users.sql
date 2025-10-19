CREATE TABLE IF NOT EXISTS internal_users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(120) NOT NULL UNIQUE,
  password_salt VARCHAR(128) NOT NULL,
  password_hash VARCHAR(128) NOT NULL,
  role ENUM('vyroba','expedicia','kancelaria','admin') NOT NULL DEFAULT 'kancelaria',
  full_name VARCHAR(255) NULL,
  email VARCHAR(255) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
