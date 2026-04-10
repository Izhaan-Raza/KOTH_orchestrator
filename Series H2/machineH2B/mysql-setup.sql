CREATE DATABASE IF NOT EXISTS admin_panel;
USE admin_panel;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255),
    password VARCHAR(255)
);

-- The player doesn't know this password, they must bypass it
INSERT INTO users (username, password) VALUES ('admin', 'Th3_M0st_S3cur3_P4ssw0rd_3v3r');

-- Changed 'localhost' to '127.0.0.1' for TCP access
CREATE USER IF NOT EXISTS 'appuser'@'127.0.0.1' IDENTIFIED BY 'app123';
GRANT ALL PRIVILEGES ON admin_panel.* TO 'appuser'@'127.0.0.1';
FLUSH PRIVILEGES;