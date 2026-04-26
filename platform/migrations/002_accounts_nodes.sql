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


