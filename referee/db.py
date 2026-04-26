from __future__ import annotations
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

class Database:
    def __init__(self, path: Path | str):
        self._path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        with self.tx() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    total_points REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS point_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_name TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    machine_name TEXT NOT NULL,
                    points REAL NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    machine_id TEXT,
                    machine_name TEXT,
                    team_name TEXT,
                    detail TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def get_team(self, name: str) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute("SELECT * FROM teams WHERE name=?", (name,)).fetchone()

    def create_team(self, name: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO teams (name, status, total_points, created_at)
                VALUES (?, 'active', 0, ?)
                ON CONFLICT(name) DO NOTHING
                """,
                (name, now),
            )
            row = conn.execute(
                "SELECT name, status, total_points FROM teams WHERE name=?",
                (name,),
            ).fetchone()
        return dict(row)

    def list_teams(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, status, total_points FROM teams ORDER BY total_points DESC, name ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_points(self, team_name: str, machine_id: str, machine_name: str, points: float) -> None:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            # Ensure team exists
            conn.execute(
                "INSERT INTO teams (name, status, total_points, created_at) VALUES (?, 'active', 0, ?) ON CONFLICT DO NOTHING",
                (team_name, now)
            )
            
            conn.execute(
                """
                INSERT INTO point_events (team_name, machine_id, machine_name, points, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (team_name, machine_id, machine_name, points, now),
            )
            conn.execute(
                "UPDATE teams SET total_points = total_points + ? WHERE name=?",
                (points, team_name),
            )
