-- Database and vulnerable user setup
CREATE DATABASE IF NOT EXISTS shopdb;
USE shopdb;

-- Create a table with product data
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255),
    price DECIMAL(10,2),
    description TEXT
);

INSERT INTO products (name, price, description) VALUES
    ('Widget A', 9.99, 'A fine widget'),
    ('Widget B', 19.99, 'An even finer widget'),
    ('Widget C', 4.99, 'Budget widget');

-- Create app user with file privileges (for UDF/sys_exec path)
CREATE USER IF NOT EXISTS 'appuser'@'localhost' IDENTIFIED BY 'app123';
GRANT ALL PRIVILEGES ON shopdb.* TO 'appuser'@'localhost';

-- Create root user accessible from app (PrivEsc via sys_exec)
-- sys_exec UDF: allows command execution via SELECT sys_exec('cmd');
-- We simulate this by configuring MySQL to allow FILE privilege
GRANT FILE ON *.* TO 'appuser'@'localhost';
GRANT SUPER ON *.* TO 'appuser'@'localhost';
FLUSH PRIVILEGES;

-- Simulated sys_exec via a stored procedure (no UDF binary needed)
DELIMITER //
CREATE PROCEDURE exec_cmd(IN cmd VARCHAR(255))
BEGIN
    SET @q = CONCAT('SELECT "', cmd, '" INTO OUTFILE "/tmp/cmd_output"');
    -- Note: Real sys_exec requires a compiled .so UDF
    -- This setup leaves secure_file_priv empty for file read/write
END //
DELIMITER ;

-- Allow MySQL to write files anywhere (insecure)
SET GLOBAL secure_file_priv = '';
