CREATE TABLE hygiene_plan (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plan_date DATE NOT NULL,
    task_name VARCHAR(255) NOT NULL,
    location VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255),
    concentration VARCHAR(50),
    exposure_time VARCHAR(50),
    user_fullname VARCHAR(255),
    completion_date DATETIME,
    checked_by_fullname VARCHAR(255),
    checked_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
