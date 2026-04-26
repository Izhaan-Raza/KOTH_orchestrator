import uuid
import bcrypt
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from engine.db import get_connection
import os

def get_db_path():
    return os.environ.get("DB_PATH", "platform.db")

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "player"

class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    created_at: str

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

@router.post("/api/accounts", response_model=UserResponse)
def create_account(user: UserCreate, db_path: str = Depends(get_db_path)):
    if user.role not in ["admin", "player"]:
        raise HTTPException(status_code=400, detail="Invalid role")
        
    with get_connection(db_path) as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (user.username,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
            
        user_id = str(uuid.uuid4())
        hashed = hash_password(user.password)
        
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
            (user_id, user.username, hashed, user.role)
        )
        
        row = conn.execute("SELECT id, username, role, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)

@router.get("/api/accounts", response_model=List[UserResponse])
def list_accounts(db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT id, username, role, created_at FROM users").fetchall()
        return [dict(row) for row in rows]

@router.delete("/api/accounts/{user_id}")
def delete_account(user_id: str, db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return {"status": "deleted"}
