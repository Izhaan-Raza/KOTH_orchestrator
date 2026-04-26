-- machines: one row per uploaded machine definition
CREATE TABLE machines (
    id          TEXT PRIMARY KEY,       -- UUID4, e.g. "a3f2c1..."
    name        TEXT NOT NULL,
    description TEXT,
    difficulty  TEXT CHECK(difficulty IN ('easy','medium','hard','insane')),
    points_per_tick INTEGER NOT NULL DEFAULT 10,
    king_file   TEXT NOT NULL DEFAULT '/root/king.txt',
    image_ref   TEXT,                   -- "myorg/vuln-nginx:latest" or NULL
    dockerfile  TEXT,                   -- path to Dockerfile or NULL
    compose_file TEXT,                  -- path to docker-compose.yml or NULL
    tags        TEXT,                   -- JSON array e.g. '["web","privesc"]'
    hints       TEXT,                   -- JSON array of hint strings
    status      TEXT NOT NULL DEFAULT 'registered',
    -- status values: registered | deploying | active | stopped | error
    uploaded_at TEXT NOT NULL,          -- ISO 8601
    uploaded_by TEXT                    -- organizer identifier
);

-- deployments: one row per running instance of a machine
CREATE TABLE deployments (
    id           TEXT PRIMARY KEY,      -- UUID4
    machine_id   TEXT NOT NULL REFERENCES machines(id),
    node_host    TEXT NOT NULL,         -- "192.168.1.10"
    node_ssh_user TEXT NOT NULL,        -- "ubuntu"
    container_id  TEXT,                 -- Docker container ID on remote node
    host_port    INTEGER NOT NULL,      -- port participants connect to
    deployed_at  TEXT NOT NULL,
    stopped_at   TEXT,
    UNIQUE(node_host, host_port)        -- prevent port conflicts
);

-- port_reservations: prevent races when two deploys happen simultaneously
CREATE TABLE port_reservations (
    node_host   TEXT NOT NULL,
    port        INTEGER NOT NULL,
    reserved_at TEXT NOT NULL,
    PRIMARY KEY (node_host, port)
);
