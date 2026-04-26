from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from engine.db import get_connection
import os
import uuid
import yaml
from engine.registry import register_machine
from engine.normalizer import normalize_compose
from api.accounts import hash_password
import secrets

router = APIRouter()

def get_db_path():
    return os.environ.get("DB_PATH", "platform.db")

class SetupPayload(BaseModel):
    admin_username: str
    admin_password: str
    node_name: str
    node_ip: str
    node_user: str
    load_examples: bool

@router.post("/api/setup/initialize")
def initialize_platform(payload: SetupPayload, db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        # 1. Create Admin
        admin_id = str(uuid.uuid4())
        hashed_pw = hash_password(payload.admin_password)
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, 'admin')",
            (admin_id, payload.admin_username, hashed_pw)
        )
        
        # 2. Create Node
        node_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO nodes (id, name, host_ip, ssh_user) VALUES (?, ?, ?, ?)",
            (node_id, payload.node_name, payload.node_ip, payload.node_user)
        )
        
        # 3. Load Examples if requested
        if payload.load_examples:
            examples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "examples")
            if os.path.exists(examples_dir):
                for i in range(1, 9):
                    series_dir = os.path.join(examples_dir, f"Series H{i}")
                    if os.path.isdir(series_dir):
                        compose_file = os.path.join(series_dir, "docker-compose.yml")
                        if os.path.exists(compose_file):
                            try:
                                info = normalize_compose(compose_file)
                                spec = {
                                    "name": f"Series H{i}",
                                    "difficulty": "medium",
                                    "points_per_tick": 10,
                                    "king_file": "/root/king.txt",
                                    "build_context": series_dir,
                                    "image": info["image"],
                                    "ports": info["ports"]
                                }
                                machine_id = str(uuid.uuid4())
                                register_machine(db_path, machine_id, spec)
                            except Exception as e:
                                pass # Skip on error
        
        # 4. Generate API Key
        api_key = secrets.token_urlsafe(32)
        os.environ["ADMIN_API_KEY"] = api_key
        
        # Write to .env
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        with open(env_path, "a") as f:
            f.write(f"\nADMIN_API_KEY={api_key}\n")
                                
    return {"status": "initialized", "api_key": api_key}

@router.get("/api/setup/status")
def setup_status(db_path: str = Depends(get_db_path)):
    # Platform is "setup" if there is at least one admin user
    try:
        with get_connection(db_path) as conn:
            user = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
            return {"is_setup": user is not None}
    except Exception:
        return {"is_setup": False}
