from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import SETTINGS
from db import Database
from models import (
    EventResponse,
    RecoveryResponse,
    RuntimeResponse,
    SkipRequest,
    StatusResponse,
    TeamResponse,
    ValidationResponse,
)
from scheduler import RefereeRuntime, RuntimeGuardError
from ssh_client import SSHClientPool

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    SETTINGS.validate_runtime()
    runtime.start_scheduler()
    try:
        yield
    finally:
        runtime.shutdown()


app = FastAPI(title="KOTH Referee", lifespan=lifespan)

templates = Jinja2Templates(directory=str(SETTINGS.templates_dir))
app.mount("/static", StaticFiles(directory=str(SETTINGS.static_dir)), name="static")


def run_admin_action(action) -> dict:
    try:
        action()
    except RuntimeGuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


def require_admin_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not SETTINGS.admin_api_key:
        return
    if x_api_key != SETTINGS.admin_api_key:
        raise HTTPException(status_code=401, detail="unauthorized")


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


@app.get("/api/runtime", response_model=RuntimeResponse)
def api_runtime() -> RuntimeResponse:
    comp = db.get_competition()
    next_rotation = comp.get("next_rotation")
    next_rotation_seconds = None
    if next_rotation:
        try:
            dt = datetime.fromisoformat(next_rotation)
            next_rotation_seconds = max(0, int((dt - datetime.now(UTC)).total_seconds()))
        except ValueError:
            next_rotation_seconds = None

    jobs = sorted(job.id for job in runtime.scheduler.get_jobs())
    return RuntimeResponse(
        competition_status=comp["status"],
        current_series=int(comp["current_series"]),
        previous_series=int(comp["previous_series"]) if comp.get("previous_series") is not None else None,
        next_rotation_seconds=next_rotation_seconds,
        fault_reason=comp.get("fault_reason"),
        last_validated_series=(
            int(comp["last_validated_series"]) if comp.get("last_validated_series") is not None else None
        ),
        last_validated_at=(
            datetime.fromisoformat(str(comp["last_validated_at"])) if comp.get("last_validated_at") else None
        ),
        active_jobs=jobs,
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
    return run_admin_action(runtime.start_competition)


@app.post("/api/competition/stop", dependencies=[Depends(require_admin_api_key)])
def api_stop() -> dict:
    return run_admin_action(runtime.stop_competition)


@app.post("/api/pause", dependencies=[Depends(require_admin_api_key)])
def api_pause() -> dict:
    return run_admin_action(runtime.pause_rotation)


@app.post("/api/resume", dependencies=[Depends(require_admin_api_key)])
def api_resume() -> dict:
    return run_admin_action(runtime.resume_rotation)


@app.post("/api/rotate", dependencies=[Depends(require_admin_api_key)])
def api_rotate() -> dict:
    return run_admin_action(runtime.rotate_next_series)


@app.post("/api/rotate/restart", dependencies=[Depends(require_admin_api_key)])
def api_rotate_restart() -> dict:
    return run_admin_action(runtime.restart_current_series)


@app.post("/api/rotate/skip", dependencies=[Depends(require_admin_api_key)])
def api_rotate_skip(payload: SkipRequest) -> dict:
    return run_admin_action(lambda: runtime.rotate_to_series(payload.target_series))


@app.post("/api/poll", dependencies=[Depends(require_admin_api_key)])
def api_poll_once() -> dict:
    return run_admin_action(runtime.poll_once)


@app.post("/api/recover/validate", response_model=ValidationResponse, dependencies=[Depends(require_admin_api_key)])
def api_recover_validate() -> ValidationResponse:
    try:
        result = runtime.validate_current_series()
    except RuntimeGuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ValidationResponse(**result)


@app.post("/api/recover/redeploy", response_model=RecoveryResponse, dependencies=[Depends(require_admin_api_key)])
def api_recover_redeploy() -> RecoveryResponse:
    try:
        result = runtime.recover_current_series()
    except RuntimeGuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RecoveryResponse(**result)
