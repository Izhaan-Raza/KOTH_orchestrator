import os
import shutil
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from engine.registry import get_active_machines, get_machine
from engine.db import get_connection

router = APIRouter()

def get_db_path() -> str:
    return os.environ.get("DB_PATH", "platform.db")

@router.get("/api/machines")
def list_machines(status: Optional[str] = None, db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        if status:
            rows = conn.execute("SELECT * FROM machines WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM machines").fetchall()
        return [dict(r) for r in rows]

@router.get("/api/machines/active")
def list_active_machines(db_path: str = Depends(get_db_path)):
    # Public endpoint used by referee
    return get_active_machines(db_path)

@router.get("/api/machines/{machine_id}")
def get_machine_detail(machine_id: str, db_path: str = Depends(get_db_path)):
    machine = get_machine(db_path, machine_id)
    if not machine:
        raise HTTPException(404, "Machine not found")
    return machine

@router.delete("/api/machines/{machine_id}")
def delete_machine(machine_id: str, db_path: str = Depends(get_db_path)):
    machine = get_machine(db_path, machine_id)
    if not machine:
        raise HTTPException(404, "Machine not found")
    if machine["status"] not in ("registered", "stopped", "error"):
        raise HTTPException(400, "Cannot delete machine in active or deploying state")
        
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
        conn.commit()
        
    # Clean up uploaded files
    machine_dir = os.path.join(os.environ.get("UPLOAD_DIR", "uploads"), machine_id)
    if os.path.exists(machine_dir):
        shutil.rmtree(machine_dir, ignore_errors=True)
        
    return {"status": "deleted"}
