import sqlite3
import datetime

PORT_RANGE_START = 10000
PORT_RANGE_END   = 20000

def reserve_port(db_path: str, node_host: str, preferred_port: int | None = None) -> int:
    """
    Reserve the next available port on node_host.
    If preferred_port is given and free, reserves that port.
    Returns the reserved port number.
    Raises RuntimeError if no ports are available.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        
        # Fetch all currently reserved ports for this node
        taken = {
            row[0] for row in conn.execute(
                "SELECT port FROM port_reservations WHERE node_host = ?",
                (node_host,)
            )
        }
        
        # Also check the deployments table for active containers
        active = {
            row[0] for row in conn.execute(
                "SELECT host_port FROM deployments WHERE node_host = ? AND stopped_at IS NULL",
                (node_host,)
            )
        }
        
        reserved = taken | active
        
        # Try preferred port first
        candidates = []
        if preferred_port and preferred_port not in reserved:
            candidates.append(preferred_port)
            
        candidates += [p for p in range(PORT_RANGE_START, PORT_RANGE_END) if p not in reserved]
        
        if not candidates:
            raise RuntimeError(f"No free ports on {node_host}")
            
        chosen = candidates[0]
        
        conn.execute(
            "INSERT INTO port_reservations (node_host, port, reserved_at) VALUES (?, ?, ?)",
            (node_host, chosen, datetime.datetime.utcnow().isoformat())
        )
        conn.commit()
        
        return chosen

def release_port(db_path: str, node_host: str, port: int):
    """Remove a port reservation when a container is stopped."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM port_reservations WHERE node_host = ? AND port = ?",
            (node_host, port)
        )
        conn.commit()

def reserve_port_with_retry(db_path: str, node_host: str, preferred_port: int | None = None, max_attempts: int = 5) -> int:
    for attempt in range(max_attempts):
        try:
            return reserve_port(db_path, node_host, preferred_port)
        except sqlite3.IntegrityError:
            preferred_port = None  # clear preference; pick any free port
            continue
    raise RuntimeError(f"Could not reserve a port after {max_attempts} attempts")
