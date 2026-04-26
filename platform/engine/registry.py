import json
from datetime import datetime, UTC
from .db import get_connection

def register_machine(db_path: str, machine_id: str, spec: dict, uploaded_by: str = "admin") -> None:
    now = datetime.now(UTC).isoformat()
    tags_json = json.dumps(spec.get("tags", []))
    hints_json = json.dumps(spec.get("hints", []))
    
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO machines (
                id, name, description, difficulty, points_per_tick, king_file,
                image_ref, dockerfile, compose_file, tags, hints, status, uploaded_at, uploaded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                machine_id,
                spec["name"],
                spec.get("description"),
                spec["difficulty"],
                spec.get("points_per_tick", 10),
                spec.get("king_file", "/root/king.txt"),
                spec.get("image"),
                spec.get("dockerfile"),
                spec.get("compose_file"),
                tags_json,
                hints_json,
                "registered",
                now,
                uploaded_by
            )
        )
        conn.commit()

def get_machine(db_path: str, machine_id: str) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
        if row:
            return dict(row)
    return None

def get_active_machines(db_path: str) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.name, d.node_host, d.node_ssh_user, d.container_id, 
                   d.host_port, m.king_file, m.points_per_tick
            FROM machines m
            JOIN deployments d ON m.id = d.machine_id
            WHERE m.status = 'active' AND d.stopped_at IS NULL
            """
        ).fetchall()
        return [dict(row) for row in rows]

def update_machine_status(db_path: str, machine_id: str, status: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute("UPDATE machines SET status = ? WHERE id = ?", (status, machine_id))
        conn.commit()

def record_deployment(db_path: str, deployment_id: str, machine_id: str, node_host: str, node_ssh_user: str, container_id: str, host_port: int) -> None:
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO deployments (id, machine_id, node_host, node_ssh_user, container_id, host_port, deployed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (deployment_id, machine_id, node_host, node_ssh_user, container_id, host_port, now)
        )
        conn.commit()

def stop_deployment(db_path: str, deployment_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE deployments SET stopped_at = ? WHERE id = ?",
            (now, deployment_id)
        )
        conn.commit()
