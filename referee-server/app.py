from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import SETTINGS
from db import Database
from models import EventResponse, SkipRequest, StatusResponse, TeamResponse
from scheduler import RefereeRuntime
from ssh_client import SSHClientPool

app = FastAPI(title="KOTH Referee")


db = Database(SETTINGS.db_path)
db.initialize()

ssh_pool = SSHClientPool(
    username=SETTINGS.ssh_user,
    private_key_path=SETTINGS.ssh_private_key,
    port=SETTINGS.ssh_port,
    timeout_seconds=SETTINGS.ssh_timeout_seconds,
    strict_host_key_checking=SETTINGS.ssh_strict_host_key_checking,
)
runtime = RefereeRuntime(db, ssh_pool)

templates = Jinja2Templates(directory=str(SETTINGS.templates_dir))
app.mount("/static", StaticFiles(directory=str(SETTINGS.static_dir)), name="static")


def require_admin_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not SETTINGS.admin_api_key:
        return
    if x_api_key != SETTINGS.admin_api_key:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.on_event("startup")
def on_startup() -> None:
    runtime.start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    runtime.shutdown()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/status", response_model=StatusResponse)
def api_status() -> StatusResponse:
    comp = db.get_competition()
    next_rotation = comp.get("next_rotation")
    next_rotation_seconds = None
    if next_rotation:
        try:
            dt = datetime.fromisoformat(next_rotation)
            next_rotation_seconds = max(0, int((dt - datetime.now(UTC)).total_seconds()))
        except ValueError:
            next_rotation_seconds = None

    teams = db.list_teams()
    active_teams = len([t for t in teams if t["status"] != "banned"])
    containers = db.list_containers()

    return StatusResponse(
        competition_status=comp["status"],
        current_series=int(comp["current_series"]),
        next_rotation_seconds=next_rotation_seconds,
        active_teams=active_teams,
        containers=containers,
    )


@app.get("/api/teams", response_model=list[TeamResponse])
def api_teams() -> list[TeamResponse]:
    return [TeamResponse(**item) for item in db.list_teams()]


@app.get("/api/events", response_model=list[EventResponse])
def api_events(
    limit: int = Query(default=50, ge=1, le=500),
    type: str | None = Query(default=None),
) -> list[EventResponse]:
    return [EventResponse(**item) for item in db.list_events(limit=limit, event_type=type)]


@app.post("/api/competition/start", dependencies=[Depends(require_admin_api_key)])
def api_start() -> dict:
    runtime.start_competition()
    return {"ok": True}


@app.post("/api/competition/stop", dependencies=[Depends(require_admin_api_key)])
def api_stop() -> dict:
    runtime.stop_competition()
    return {"ok": True}


@app.post("/api/pause", dependencies=[Depends(require_admin_api_key)])
def api_pause() -> dict:
    runtime.pause_rotation()
    return {"ok": True}


@app.post("/api/resume", dependencies=[Depends(require_admin_api_key)])
def api_resume() -> dict:
    runtime.resume_rotation()
    return {"ok": True}


@app.post("/api/rotate", dependencies=[Depends(require_admin_api_key)])
def api_rotate() -> dict:
    runtime.rotate_next_series()
    return {"ok": True}


@app.post("/api/rotate/restart", dependencies=[Depends(require_admin_api_key)])
def api_rotate_restart() -> dict:
    runtime.restart_current_series()
    return {"ok": True}


@app.post("/api/rotate/skip", dependencies=[Depends(require_admin_api_key)])
def api_rotate_skip(payload: SkipRequest) -> dict:
    runtime.rotate_to_series(payload.target_series)
    return {"ok": True}


@app.post("/api/poll", dependencies=[Depends(require_admin_api_key)])
def api_poll_once() -> dict:
    runtime.poll_once()
    return {"ok": True}
