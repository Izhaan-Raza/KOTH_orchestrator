import uuid
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from engine.db import get_connection
from .setup import get_db_path

router = APIRouter()

class NodeCreate(BaseModel):
    name: str
    host_ip: str
    ssh_user: str = "ubuntu"

class NodeResponse(BaseModel):
    id: str
    name: str
    host_ip: str
    ssh_user: str
    status: str
    created_at: str

@router.post("/api/nodes", response_model=NodeResponse)
def create_node(node: NodeCreate, db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        node_id = str(uuid.uuid4())
        
        conn.execute(
            "INSERT INTO nodes (id, name, host_ip, ssh_user) VALUES (?, ?, ?, ?)",
            (node_id, node.name, node.host_ip, node.ssh_user)
        )
        
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return dict(row)

@router.get("/api/nodes", response_model=List[NodeResponse])
def list_nodes(db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM nodes").fetchall()
        return [dict(row) for row in rows]

@router.delete("/api/nodes/{node_id}")
def delete_node(node_id: str, db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        return {"status": "deleted"}
