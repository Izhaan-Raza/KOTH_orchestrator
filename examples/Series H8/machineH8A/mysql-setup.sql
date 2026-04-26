-- MySQL H8A setup: root with no password + UDF support
-- Root with no password
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '';
FLUSH PRIVILEGES;

-- Allow FILE privilege
GRANT FILE ON *.* TO 'root'@'localhost';

-- Create a database
CREATE DATABASE IF NOT EXISTS kothdb;
USE kothdb;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50),
    password VARCHAR(255),
    role VARCHAR(20)
);

INSERT INTO users VALUES (1, 'admin', 'admin123', 'admin'),
                         (2, 'user1', 'pass1', 'user');

-- UDF installation (attackers can do this after gaining MySQL root):
-- SELECT unhex('...') INTO DUMPFILE '/usr/lib/mysql/plugin/udf_sys.so';
-- CREATE FUNCTION sys_exec RETURNS INT SONAME 'udf_sys.so';
-- SELECT sys_exec('/usr/local/bin/mysql-root-shell');

FLUSH PRIVILEGES;
