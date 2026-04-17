from __future__ import annotations

import re
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import SETTINGS
from db import Database
from models import (
    EventResponse,
    LbServerResponse,
    LbServiceResponse,
    LbStatusResponse,
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
    host_target_overrides=SETTINGS.ssh_target_overrides(),
)
runtime = RefereeRuntime(db, ssh_pool)
HAPROXY_CONFIG_PATH = Path("/etc/haproxy/haproxy.cfg")
LISTEN_RE = re.compile(r"^listen\s+(\S+)")
FRONTEND_RE = re.compile(r"^frontend\s+(\S+)")
BACKEND_RE = re.compile(r"^backend\s+(\S+)")
BIND_RE = re.compile(r"^bind\s+\*?:(\d+)")
SERVER_RE = re.compile(r"^server\s+(\S+)\s+([0-9.]+):(\d+)")


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


def _parse_endpoint_port(endpoint: str) -> int | None:
    if endpoint.startswith("["):
        parts = endpoint.rsplit("]:", 1)
        if len(parts) != 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None
    parts = endpoint.rsplit(":", 1)
    if len(parts) != 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _parse_endpoint_host_port(endpoint: str) -> tuple[str, int] | None:
    if endpoint.startswith("["):
        parts = endpoint.rsplit("]:", 1)
        if len(parts) != 2:
            return None
        host = parts[0].lstrip("[")
        try:
            return host, int(parts[1])
        except ValueError:
            return None
    parts = endpoint.rsplit(":", 1)
    if len(parts) != 2:
        return None
    host = parts[0]
    try:
        return host, int(parts[1])
    except ValueError:
        return None


def _haproxy_services() -> list[dict]:
    if not HAPROXY_CONFIG_PATH.is_file():
        return []

    frontends: dict[str, dict] = {}
    backends: dict[str, list[dict]] = {}
    listens: list[dict] = []
    current_kind: str | None = None
    current_name: str | None = None

    for raw_line in HAPROXY_CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        listen_match = LISTEN_RE.match(line)
        if listen_match:
            current_kind = "listen"
            current_name = listen_match.group(1)
            listens.append({"name": current_name, "bind_port": None, "servers": []})
            continue

        frontend_match = FRONTEND_RE.match(line)
        if frontend_match:
            current_kind = "frontend"
            current_name = frontend_match.group(1)
            frontends[current_name] = {"name": current_name, "bind_port": None, "backend": None}
            continue

        backend_match = BACKEND_RE.match(line)
        if backend_match:
            current_kind = "backend"
            current_name = backend_match.group(1)
            backends.setdefault(current_name, [])
            continue

        if current_kind is None or current_name is None:
            continue

        bind_match = BIND_RE.match(line)
        if bind_match and current_kind in {"listen", "frontend"}:
            bind_port = int(bind_match.group(1))
            if current_kind == "listen":
                listens[-1]["bind_port"] = bind_port
            else:
                frontends[current_name]["bind_port"] = bind_port
            continue

        server_match = SERVER_RE.match(line)
        if server_match and current_kind in {"listen", "backend"}:
            server = {
                "name": server_match.group(1),
                "host": server_match.group(2),
                "port": int(server_match.group(3)),
            }
            if current_kind == "listen":
                listens[-1]["servers"].append(server)
            else:
                backends.setdefault(current_name, []).append(server)
            continue

        if current_kind == "frontend" and line.startswith("default_backend "):
            frontends[current_name]["backend"] = line.split(None, 1)[1].strip()

    services = [service for service in listens if service.get("bind_port") and service.get("servers")]
    for frontend in frontends.values():
        bind_port = frontend.get("bind_port")
        backend_name = frontend.get("backend")
        servers = backends.get(backend_name or "", [])
        if not bind_port or not servers:
            continue
        services.append(
            {
                "name": frontend["name"],
                "bind_port": bind_port,
                "servers": servers,
            }
        )
    return services


def _ss_established_rows() -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            ["ss", "-Htn", "state", "established"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    rows: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        rows.append((parts[-2], parts[-1]))
    return rows


def _lb_status() -> LbStatusResponse:
    services = _haproxy_services()
    if not services:
        return LbStatusResponse(
            configured=False,
            services=[],
            total_inbound_connections=0,
            total_backend_connections=0,
            note=f"HAProxy config not found at {HAPROXY_CONFIG_PATH}",
        )

    rows = _ss_established_rows()
    inbound_by_port: dict[int, int] = {}
    backend_by_host_port: dict[tuple[str, int], int] = {}

    for local, peer in rows:
        local_port = _parse_endpoint_port(local)
        if local_port is not None:
            inbound_by_port[local_port] = inbound_by_port.get(local_port, 0) + 1

        host_port = _parse_endpoint_host_port(peer)
        if host_port is not None:
            backend_by_host_port[host_port] = backend_by_host_port.get(host_port, 0) + 1

    response_services: list[LbServiceResponse] = []
    total_inbound = 0
    total_backend = 0
    for service in services:
        bind_port = int(service["bind_port"])
        servers: list[LbServerResponse] = []
        backend_total = 0
        for server in service["servers"]:
            active = backend_by_host_port.get((server["host"], int(server["port"])), 0)
            backend_total += active
            servers.append(
                LbServerResponse(
                    name=str(server["name"]),
                    host=str(server["host"]),
                    port=int(server["port"]),
                    active_connections=active,
                )
            )
        inbound = inbound_by_port.get(bind_port, 0)
        total_inbound += inbound
        total_backend += backend_total
        response_services.append(
            LbServiceResponse(
                name=str(service["name"]),
                bind_port=bind_port,
                inbound_connections=inbound,
                backend_connections=backend_total,
                servers=servers,
            )
        )

    return LbStatusResponse(
        configured=True,
        services=response_services,
        total_inbound_connections=total_inbound,
        total_backend_connections=total_backend,
        note=None,
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"request": request})


@app.get("/api/status", response_model=StatusResponse, dependencies=[Depends(require_admin_api_key)])
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


@app.get("/api/runtime", response_model=RuntimeResponse, dependencies=[Depends(require_admin_api_key)])
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


@app.get("/api/lb", response_model=LbStatusResponse, dependencies=[Depends(require_admin_api_key)])
def api_lb_status() -> LbStatusResponse:
    return _lb_status()


@app.get("/api/teams", response_model=list[TeamResponse], dependencies=[Depends(require_admin_api_key)])
def api_teams() -> list[TeamResponse]:
    return [TeamResponse(**item) for item in db.list_teams()]


@app.get("/api/events", response_model=list[EventResponse], dependencies=[Depends(require_admin_api_key)])
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
