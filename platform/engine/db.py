import sqlite3
import os
import glob
from contextlib import contextmanager

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # access columns by name
    # Enable WAL mode
    conn.execute("PRAGMA journal_mode=WAL")
    # 5000 ms is enough for the other writer to finish under normal load.
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def apply_migrations(db_path: str, migrations_dir: str):
    conn = get_connection(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT)"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    
    if not os.path.exists(migrations_dir):
        os.makedirs(migrations_dir, exist_ok=True)
        
    files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    for path in files:
        version = os.path.basename(path)
        if version not in applied:
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (version,)
            )
            conn.commit()
            print(f"Applied migration: {version}")
