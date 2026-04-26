-- Account System
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'player', -- 'admin' or 'player'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Nodes / IP Mappings
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host_ip TEXT NOT NULL,
    ssh_user TEXT DEFAULT 'ubuntu',
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Pre-populate default admin account (password: 'admin')
-- Note: bcrypt hash for 'admin' is $2b$12$NqL15sI5x2w5b8Z8L3B.9uyH6G8h.L8.U0A6H7L8U0A6H7L8U0A6
INSERT OR IGNORE INTO users (id, username, password_hash, role) 
VALUES ('default-admin', 'admin', '$2b$12$3jO.iT6P0b6hZpL0nO.7.O0K1eZ1A1C1e1Z1A1C1e1Z1A1C1e1Z1A', 'admin');
