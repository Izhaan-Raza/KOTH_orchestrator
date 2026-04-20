from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_UNSET = object()


class Database:
    def __init__(self, path: Path):
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
                    offense_count INTEGER NOT NULL DEFAULT 0,
                    total_points REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS point_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_name TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    series INTEGER NOT NULL,
                    points REAL NOT NULL,
                    poll_cycle INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    machine TEXT,
                    variant TEXT,
                    series INTEGER,
                    team_name TEXT,
                    detail TEXT NOT NULL,
                    evidence TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_name TEXT NOT NULL,
                    machine TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    series INTEGER NOT NULL,
                    offense_id INTEGER NOT NULL,
                    offense_name TEXT NOT NULL,
                    evidence TEXT,
                    action_taken TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS containers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_host TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    container_id TEXT NOT NULL,
                    series INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    king TEXT,
                    king_mtime_epoch INTEGER,
                    last_checked TEXT,
                    UNIQUE(machine_host, variant)
                );

                CREATE TABLE IF NOT EXISTS baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_host TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    series INTEGER NOT NULL,
                    shadow_hash TEXT,
                    authkeys_hash TEXT,
                    iptables_sig TEXT,
                    ports_sig TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(machine_host, variant, series)
                );

                CREATE TABLE IF NOT EXISTS variant_ownership (
                    series INTEGER NOT NULL,
                    variant TEXT NOT NULL,
                    owner_team TEXT,
                    accepted_mtime_epoch INTEGER,
                    accepted_at TEXT NOT NULL,
                    source_node_host TEXT,
                    evidence_json TEXT,
                    PRIMARY KEY (series, variant)
                );

                CREATE TABLE IF NOT EXISTS claim_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poll_cycle INTEGER NOT NULL,
                    series INTEGER NOT NULL,
                    node_host TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    status TEXT NOT NULL,
                    king TEXT,
                    king_mtime_epoch INTEGER,
                    observed_at TEXT NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    selection_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS active_violations (
                    team_name TEXT NOT NULL,
                    machine TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    series INTEGER NOT NULL,
                    offense_name TEXT NOT NULL,
                    evidence_sig TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (team_name, machine, variant, series, offense_name, evidence_sig)
                );

                CREATE TABLE IF NOT EXISTS competition (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    status TEXT NOT NULL DEFAULT 'stopped',
                    current_series INTEGER NOT NULL DEFAULT 0,
                    previous_series INTEGER,
                    poll_cycle INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    next_rotation TEXT,
                    fault_reason TEXT,
                    last_validated_series INTEGER,
                    last_validated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS public_dashboard_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    orchestrator_host TEXT,
                    port_ranges TEXT,
                    headline TEXT,
                    subheadline TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS public_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(
                conn,
                table="competition",
                column="previous_series",
                definition="INTEGER",
            )
            self._ensure_column(
                conn,
                table="competition",
                column="fault_reason",
                definition="TEXT",
            )
            self._ensure_column(
                conn,
                table="competition",
                column="last_validated_series",
                definition="INTEGER",
            )
            self._ensure_column(
                conn,
                table="competition",
                column="last_validated_at",
                definition="TEXT",
            )
            now = datetime.now(UTC).isoformat()
            conn.execute(
                """
                INSERT INTO competition (
                    id, status, current_series, previous_series, poll_cycle, started_at, next_rotation, fault_reason,
                    last_validated_series, last_validated_at
                )
                VALUES (1, 'stopped', 0, NULL, 0, ?, NULL, NULL, NULL, NULL)
                ON CONFLICT(id) DO NOTHING
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO public_dashboard_config (id, orchestrator_host, port_ranges, headline, subheadline, updated_at)
                VALUES (1, NULL, NULL, NULL, NULL, NULL)
                ON CONFLICT(id) DO NOTHING
                """
            )

    def _ensure_column(self, conn: sqlite3.Connection, *, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {str(row["name"]) for row in rows}
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def upsert_team_names(self, team_names: list[str]) -> None:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            for name in team_names:
                conn.execute(
                    """
                    INSERT INTO teams (name, status, offense_count, total_points, created_at)
                    VALUES (?, 'active', 0, 0, ?)
                    ON CONFLICT(name) DO NOTHING
                    """,
                    (name, now),
                )

    def get_active_violation_keys(self, *, series: int) -> set[tuple[str, str, str, int, str, str]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT team_name, machine, variant, series, offense_name, evidence_sig
                FROM active_violations
                WHERE series=?
                """,
                (series,),
            ).fetchall()
        return {
            (
                str(row["team_name"]),
                str(row["machine"]),
                str(row["variant"]),
                int(row["series"]),
                str(row["offense_name"]),
                str(row["evidence_sig"]),
            )
            for row in rows
        }

    def replace_active_violations(
        self,
        *,
        series: int,
        entries: set[tuple[str, str, str, int, str, str]],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            conn.execute("DELETE FROM active_violations WHERE series=?", (series,))
            for team_name, machine, variant, row_series, offense_name, evidence_sig in entries:
                conn.execute(
                    """
                    INSERT INTO active_violations (
                        team_name, machine, variant, series, offense_name, evidence_sig, first_seen_at, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (team_name, machine, variant, row_series, offense_name, evidence_sig, now, now),
                )

    def create_team(self, name: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO teams (name, status, offense_count, total_points, created_at)
                VALUES (?, 'active', 0, 0, ?)
                """,
                (name, now),
            )
            row = conn.execute(
                "SELECT name, status, offense_count, total_points FROM teams WHERE name=?",
                (name,),
            ).fetchone()
        return dict(row)

    def get_public_dashboard_config(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT orchestrator_host, port_ranges, headline, subheadline, updated_at
                FROM public_dashboard_config
                WHERE id=1
                """
            ).fetchone()
        if row is None:
            return {
                "orchestrator_host": None,
                "port_ranges": None,
                "headline": None,
                "subheadline": None,
                "updated_at": None,
            }
        return dict(row)

    def set_public_dashboard_config(
        self,
        *,
        orchestrator_host: str | None = _UNSET,
        port_ranges: str | None = _UNSET,
        headline: str | None = _UNSET,
        subheadline: str | None = _UNSET,
    ) -> dict[str, Any]:
        assignments: list[str] = []
        params: list[Any] = []
        if orchestrator_host is not _UNSET:
            assignments.append("orchestrator_host=?")
            params.append(orchestrator_host)
        if port_ranges is not _UNSET:
            assignments.append("port_ranges=?")
            params.append(port_ranges)
        if headline is not _UNSET:
            assignments.append("headline=?")
            params.append(headline)
        if subheadline is not _UNSET:
            assignments.append("subheadline=?")
            params.append(subheadline)
        assignments.append("updated_at=?")
        params.append(datetime.now(UTC).isoformat())
        params.append(1)
        with self.tx() as conn:
            conn.execute(
                f"UPDATE public_dashboard_config SET {', '.join(assignments)} WHERE id=?",
                tuple(params),
            )
        return self.get_public_dashboard_config()

    def list_public_notifications(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, message, severity, created_at
                FROM public_notifications
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_public_notification(self, *, message: str, severity: str) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            cursor = conn.execute(
                """
                INSERT INTO public_notifications (message, severity, created_at)
                VALUES (?, ?, ?)
                """,
                (message, severity, created_at),
            )
            row = conn.execute(
                """
                SELECT id, message, severity, created_at
                FROM public_notifications
                WHERE id=?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return dict(row) if row is not None else {}

    def delete_public_notification(self, notification_id: int) -> bool:
        with self.tx() as conn:
            cursor = conn.execute(
                "DELETE FROM public_notifications WHERE id=?",
                (notification_id,),
            )
        return cursor.rowcount > 0

    def team_exists(self, name: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM teams WHERE name=?", (name,)).fetchone()
        return row is not None

    def get_team(self, name: str) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute("SELECT * FROM teams WHERE name=?", (name,)).fetchone()

    def list_teams(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, status, offense_count, total_points FROM teams ORDER BY total_points DESC, name ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_point_events(self, *, team_names: list[str] | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if team_names:
            placeholders = ", ".join("?" for _ in team_names)
            where = f"WHERE team_name IN ({placeholders})"
            params.extend(team_names)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT team_name, points, timestamp
                FROM point_events
                {where}
                ORDER BY timestamp ASC, id ASC
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_team_status(
        self,
        name: str,
        *,
        status: str,
        offense_count: int | None = None,
    ) -> dict[str, Any]:
        assignments = ["status=?"]
        params: list[Any] = [status]
        if offense_count is not None:
            assignments.append("offense_count=?")
            params.append(offense_count)
        params.append(name)
        with self.tx() as conn:
            conn.execute(
                f"UPDATE teams SET {', '.join(assignments)} WHERE name=?",
                tuple(params),
            )
            row = conn.execute(
                "SELECT name, status, offense_count, total_points FROM teams WHERE name=?",
                (name,),
            ).fetchone()
        if row is None:
            raise KeyError(name)
        return dict(row)

    def team_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS count FROM teams").fetchone()
        return int(row["count"])

    def increment_poll_cycle(self) -> int:
        with self.tx() as conn:
            conn.execute("UPDATE competition SET poll_cycle = poll_cycle + 1 WHERE id=1")
            row = conn.execute("SELECT poll_cycle FROM competition WHERE id=1").fetchone()
        return int(row["poll_cycle"])

    def add_points(
        self,
        team_name: str,
        variant: str,
        series: int,
        points: float,
        poll_cycle: int,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO point_events (team_name, variant, series, points, poll_cycle, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (team_name, variant, series, points, poll_cycle, now),
            )
            conn.execute(
                "UPDATE teams SET total_points = total_points + ? WHERE name=?",
                (points, team_name),
            )

    def add_event(
        self,
        event_type: str,
        severity: str,
        detail: str,
        machine: str | None = None,
        variant: str | None = None,
        series: int | None = None,
        team_name: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        evidence_json = json.dumps(evidence) if evidence is not None else None
        with self.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO events (type, severity, machine, variant, series, team_name, detail, evidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, severity, machine, variant, series, team_name, detail, evidence_json, now),
            )
            return int(cur.lastrowid)

    def list_events(self, limit: int, event_type: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if event_type:
            where = "WHERE type=?"
            params.append(event_type)
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT id, type, severity, machine, variant, series, team_name, detail, evidence, timestamp
                FROM events
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item["evidence"]) if item["evidence"] else None
            out.append(item)
        return out

    def get_competition(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM competition WHERE id=1").fetchone()
        return dict(row)

    def set_competition_state(
        self,
        *,
        status: str | None | object = _UNSET,
        current_series: int | None | object = _UNSET,
        previous_series: int | None | object = _UNSET,
        next_rotation: str | None | object = _UNSET,
        started_at: str | None | object = _UNSET,
        fault_reason: str | None | object = _UNSET,
        last_validated_series: int | None | object = _UNSET,
        last_validated_at: str | None | object = _UNSET,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if status is not _UNSET:
            updates.append("status=?")
            params.append(status)
        if current_series is not _UNSET:
            updates.append("current_series=?")
            params.append(current_series)
        if previous_series is not _UNSET:
            updates.append("previous_series=?")
            params.append(previous_series)
        if next_rotation is not _UNSET:
            updates.append("next_rotation=?")
            params.append(next_rotation)
        if started_at is not _UNSET:
            updates.append("started_at=?")
            params.append(started_at)
        if fault_reason is not _UNSET:
            updates.append("fault_reason=?")
            params.append(fault_reason)
        if last_validated_series is not _UNSET:
            updates.append("last_validated_series=?")
            params.append(last_validated_series)
        if last_validated_at is not _UNSET:
            updates.append("last_validated_at=?")
            params.append(last_validated_at)
        if not updates:
            return
        params.append(1)
        with self.tx() as conn:
            conn.execute(f"UPDATE competition SET {', '.join(updates)} WHERE id=?", tuple(params))

    def reset_series_bans(self) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE teams SET status='warned' WHERE status='series_banned'")

    def record_violation(
        self,
        *,
        team_name: str,
        machine: str,
        variant: str,
        series: int,
        offense_id: int,
        offense_name: str,
        evidence: dict[str, Any],
        action_taken: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO violations (team_name, machine, variant, series, offense_id, offense_name, evidence, action_taken, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team_name,
                    machine,
                    variant,
                    series,
                    offense_id,
                    offense_name,
                    json.dumps(evidence),
                    action_taken,
                    now,
                ),
            )

    def list_violations(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT team_name, machine, variant, series, offense_id, offense_name, evidence, action_taken, timestamp
            FROM violations
            ORDER BY id ASC
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def increment_team_offense(self, team_name: str) -> tuple[int, str]:
        with self.tx() as conn:
            row = conn.execute(
                "SELECT offense_count, status FROM teams WHERE name=?",
                (team_name,),
            ).fetchone()
            if row is None:
                raise ValueError(f"team does not exist: {team_name}")
            offense_count = int(row["offense_count"]) + 1
            if offense_count == 1:
                status = "warned"
            elif offense_count == 2:
                status = "series_banned"
            else:
                status = "banned"
            conn.execute(
                "UPDATE teams SET offense_count=?, status=? WHERE name=?",
                (offense_count, status, team_name),
            )
        return offense_count, status

    def upsert_container_status(
        self,
        *,
        machine_host: str,
        variant: str,
        container_id: str,
        series: int,
        status: str,
        king: str | None,
        king_mtime_epoch: int | None,
        last_checked: str | None,
    ) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO containers (machine_host, variant, container_id, series, status, king, king_mtime_epoch, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_host, variant) DO UPDATE SET
                    container_id=excluded.container_id,
                    series=excluded.series,
                    status=excluded.status,
                    king=excluded.king,
                    king_mtime_epoch=excluded.king_mtime_epoch,
                    last_checked=excluded.last_checked
                """,
                (
                    machine_host,
                    variant,
                    container_id,
                    series,
                    status,
                    king,
                    king_mtime_epoch,
                    last_checked,
                ),
            )

    def list_containers(
        self,
        *,
        series: int | None = None,
        machine_hosts: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if series is not None:
            where_parts.append("series=?")
            params.append(series)
        if machine_hosts:
            placeholders = ", ".join("?" for _ in machine_hosts)
            where_parts.append(f"machine_host IN ({placeholders})")
            params.extend(machine_hosts)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT machine_host, variant, container_id, series, status, king, king_mtime_epoch, last_checked
                FROM containers
                """
                + where
                + """
                ORDER BY machine_host, variant
                """,
                tuple(params),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_baseline(
        self,
        *,
        machine_host: str,
        variant: str,
        series: int,
        shadow_hash: str | None,
        authkeys_hash: str | None,
        iptables_sig: str | None,
        ports_sig: str | None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO baselines (machine_host, variant, series, shadow_hash, authkeys_hash, iptables_sig, ports_sig, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_host, variant, series) DO UPDATE SET
                    shadow_hash=excluded.shadow_hash,
                    authkeys_hash=excluded.authkeys_hash,
                    iptables_sig=excluded.iptables_sig,
                    ports_sig=excluded.ports_sig,
                    created_at=excluded.created_at
                """,
                (
                    machine_host,
                    variant,
                    series,
                    shadow_hash,
                    authkeys_hash,
                    iptables_sig,
                    ports_sig,
                    now,
                ),
            )

    def get_baseline(self, *, machine_host: str, variant: str, series: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT machine_host, variant, series, shadow_hash, authkeys_hash, iptables_sig, ports_sig
                FROM baselines
                WHERE machine_host=? AND variant=? AND series=?
                """,
                (machine_host, variant, series),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_variant_owner(self, *, series: int, variant: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT series, variant, owner_team, accepted_mtime_epoch, accepted_at, source_node_host, evidence_json
                FROM variant_ownership
                WHERE series=? AND variant=?
                """,
                (series, variant),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["evidence_json"] = json.loads(item["evidence_json"]) if item["evidence_json"] else None
        return item

    def list_variant_owners(self, *, series: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT series, variant, owner_team, accepted_mtime_epoch, accepted_at, source_node_host, evidence_json
                FROM variant_ownership
                WHERE series=?
                ORDER BY variant
                """,
                (series,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence_json"] = json.loads(item["evidence_json"]) if item["evidence_json"] else None
            out.append(item)
        return out

    def set_variant_owner(
        self,
        *,
        series: int,
        variant: str,
        owner_team: str,
        accepted_mtime_epoch: int,
        source_node_host: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        evidence_json = json.dumps(evidence) if evidence is not None else None
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO variant_ownership (
                    series, variant, owner_team, accepted_mtime_epoch, accepted_at, source_node_host, evidence_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(series, variant) DO UPDATE SET
                    owner_team=excluded.owner_team,
                    accepted_mtime_epoch=excluded.accepted_mtime_epoch,
                    accepted_at=excluded.accepted_at,
                    source_node_host=excluded.source_node_host,
                    evidence_json=excluded.evidence_json
                """,
                (
                    series,
                    variant,
                    owner_team,
                    accepted_mtime_epoch,
                    now,
                    source_node_host,
                    evidence_json,
                ),
            )

    def add_claim_observations(self, observations: list[dict[str, Any]]) -> None:
        if not observations:
            return
        with self.tx() as conn:
            conn.executemany(
                """
                INSERT INTO claim_observations (
                    poll_cycle, series, node_host, variant, status, king, king_mtime_epoch,
                    observed_at, selected, selection_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["poll_cycle"],
                        item["series"],
                        item["node_host"],
                        item["variant"],
                        item["status"],
                        item.get("king"),
                        item.get("king_mtime_epoch"),
                        item["observed_at"],
                        1 if item.get("selected") else 0,
                        item.get("selection_reason"),
                    )
                    for item in observations
                ],
            )

    def list_claim_observations(self, *, limit: int, series: int | None = None) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if series is not None:
            where = "WHERE series=?"
            params.append(series)
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT id, poll_cycle, series, node_host, variant, status, king, king_mtime_epoch,
                       observed_at, selected, selection_reason
                FROM claim_observations
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def reset_for_new_competition(self) -> None:
        with self.tx() as conn:
            conn.execute("DELETE FROM point_events")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM violations")
            conn.execute("DELETE FROM containers")
            conn.execute("DELETE FROM baselines")
            conn.execute("DELETE FROM variant_ownership")
            conn.execute("DELETE FROM claim_observations")
            conn.execute(
                """
                UPDATE teams
                SET status='active',
                    offense_count=0,
                    total_points=0
                """
            )
            conn.execute(
                """
                UPDATE competition
                SET poll_cycle=0,
                    previous_series=NULL,
                    fault_reason=NULL,
                    last_validated_series=NULL,
                    last_validated_at=NULL
                WHERE id=1
                """
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
