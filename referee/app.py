import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from db import Database
from poller import Poller

load_dotenv()

db = Database(os.environ.get("DB_PATH", "referee.db"))
db.initialize()

async def score_machine(machine_id: str, machine_name: str, owner: str, points: int):
    # This is called by Poller for every active machine on every cycle
    db.add_points(owner, machine_id, machine_name, points)

poller = Poller(
    platform_url=os.environ.get("PLATFORM_URL", "http://localhost:8000"),
    ssh_key_path=os.environ.get("SSH_KEY_PATH", ""),
    interval_seconds=int(os.environ.get("SCORE_INTERVAL", "30")),
    scorer_callback=score_machine
)

poller_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poller_task
    poller_task = asyncio.create_task(poller.run_forever())
    yield
    if poller_task:
        poller_task.cancel()

app = FastAPI(title="KoTH Referee Server v2", lifespan=lifespan)

def require_admin_api_key(x_admin_key: str | None = Header(default=None)):
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/api/leaderboard")
def get_leaderboard():
    return db.list_teams()

@app.get("/health")
def health_check():
    return {"status": "ok"}
