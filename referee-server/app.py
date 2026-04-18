from __future__ import annotations

import csv
import io
import json
import os
import re
import shlex
import socket
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import SETTINGS
from db import Database
from models import (
    ClaimObservationResponse,
    ContainerTelemetryResponse,
    EventResponse,
    HostTelemetryResponse,
    LbServerResponse,
    LbServiceResponse,
    LbStatusResponse,
    LogTailResponse,
    RecoveryResponse,
    RoutingServerResponse,
    RoutingServiceResponse,
    RoutingStatusResponse,
    RuntimeResponse,
    SkipRequest,
    StatusResponse,
    TelemetryStatusResponse,
    TeamIn,
    TeamResponse,
    TeamStatusUpdateResponse,
    ValidationResponse,
)
from poller import Poller
from runtime_logging import configure_logging
from scheduler import RefereeRuntime, RuntimeGuardError
from ssh_client import SSHClientPool

configure_logging(SETTINGS.referee_log_path)
logger = logging.getLogger("koth.referee")

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


def _safe_int(value: str | None) -> int | None:
    if value in {None, "", "-"}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _safe_float(value: str | None) -> float | None:
    if value in {None, "", "-"}:
        return None
    cleaned = str(value).strip().rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_docker_timestamp(value: str | None) -> datetime | None:
    if not value or value.startswith("0001-01-01T00:00:00"):
        return None
    normalized = value.replace("Z", "+00:00")
    if "." in normalized:
        head, rest = normalized.split(".", 1)
        tz_index = max(rest.rfind("+"), rest.rfind("-"))
        if tz_index > 0:
            fractional = rest[:tz_index]
            suffix = rest[tz_index:]
        else:
            fractional = rest
            suffix = ""
        normalized = f"{head}.{fractional[:6]}{suffix}"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _duration_seconds(started_at: datetime | None, ended_at: datetime | None = None) -> int | None:
    if started_at is None:
        return None
    endpoint = ended_at or datetime.now(UTC)
    return max(0, int((endpoint - started_at).total_seconds()))


def _run_local(command: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _service_state(command_runner, service_name: str) -> str | None:
    code, out, _ = command_runner(["systemctl", "is-active", service_name])
    if code == 0:
        return out.strip() or "active"
    normalized = (out or "").strip()
    return normalized or None


def _collect_linux_host_metrics() -> dict[str, float | int | None]:
    if os.name == "nt":
        return {
            "loadavg_1m": None,
            "loadavg_5m": None,
            "loadavg_15m": None,
            "mem_used_mb": None,
            "mem_total_mb": None,
            "mem_percent": None,
            "disk_used_gb": None,
            "disk_total_gb": None,
            "disk_percent": None,
            "uptime_seconds": None,
        }

    load1 = load5 = load15 = None
    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        pass

    mem_total_kb = mem_available_kb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available_kb = int(line.split()[1])
    except OSError:
        pass

    mem_total_mb = mem_used_mb = None
    mem_percent = None
    if mem_total_kb and mem_available_kb is not None:
        mem_total_mb = mem_total_kb // 1024
        mem_used_mb = max(mem_total_kb - mem_available_kb, 0) // 1024
        mem_percent = round(((mem_total_kb - mem_available_kb) * 100) / mem_total_kb, 1)

    disk_total_gb = disk_used_gb = None
    disk_percent = None
    try:
        fs = os.statvfs("/")
        disk_total_gb = round((fs.f_blocks * fs.f_frsize) / (1024**3), 1)
        disk_used_gb = round(((fs.f_blocks - fs.f_bavail) * fs.f_frsize) / (1024**3), 1)
        if fs.f_blocks:
            disk_percent = round(((fs.f_blocks - fs.f_bavail) * 100) / fs.f_blocks, 1)
    except OSError:
        pass

    uptime_seconds = None
    try:
        with open("/proc/uptime", encoding="utf-8") as handle:
            uptime_seconds = int(float(handle.read().split()[0]))
    except OSError:
        pass

    return {
        "loadavg_1m": load1,
        "loadavg_5m": load5,
        "loadavg_15m": load15,
        "mem_used_mb": mem_used_mb,
        "mem_total_mb": mem_total_mb,
        "mem_percent": mem_percent,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_percent": disk_percent,
        "uptime_seconds": uptime_seconds,
    }


def _haproxy_socket_command(command: str) -> str:
    socket_path = SETTINGS.haproxy_admin_socket_path
    if not socket_path.exists():
        return ""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2.0)
        client.connect(str(socket_path))
        client.sendall(f"{command}\n".encode("utf-8"))
        chunks: list[bytes] = []
        while True:
            data = client.recv(65536)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _haproxy_runtime_rows() -> list[dict[str, str]]:
    try:
        payload = _haproxy_socket_command("show stat")
    except OSError as exc:
        logger.warning("haproxy runtime stats unavailable: %s", exc)
        return []
    lines = [line for line in payload.splitlines() if line.strip()]
    if not lines:
        return []
    header = None
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("#"):
            header = line.lstrip("# ").strip()
            continue
        data_lines.append(line)
    if not header or not data_lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join([header, *data_lines])))
    return [dict(row) for row in reader]


def _series_variant_ports(series: int) -> dict[int, str]:
    try:
        ports = tuple(runtime._series_public_ports(series))  # noqa: SLF001 - shared runtime helper
    except Exception:
        return {}
    variants = ("A", "B", "C")
    return {port: variants[index] for index, port in enumerate(ports[: len(variants)])}


def _compose_service_name(series: int, variant: str) -> str:
    return SETTINGS.container_name_template.format(
        series=series,
        variant=variant,
        variant_lower=variant.lower(),
    )


def _routing_status() -> RoutingStatusResponse:
    competition = db.get_competition()
    current_series = int(competition["current_series"])
    services = _haproxy_services()
    if not services:
        return RoutingStatusResponse(
            configured=False,
            current_series=current_series,
            services=[],
            total_inbound_connections=0,
            total_backend_connections=0,
            note=f"HAProxy config not found at {HAPROXY_CONFIG_PATH}",
        )

    variant_map = _series_variant_ports(current_series) if current_series > 0 else {}
    active_ports = set(variant_map)
    stat_rows = _haproxy_runtime_rows()
    stat_index = {(row.get("pxname"), row.get("svname")): row for row in stat_rows}

    route_services: list[RoutingServiceResponse] = []
    total_inbound = 0
    total_backend = 0

    for service in services:
        bind_port = int(service["bind_port"])
        if active_ports and bind_port not in active_ports:
            continue

        frontend_row = stat_index.get((service["name"], "FRONTEND"), {})
        backend_row = stat_index.get((service["name"], "BACKEND"), {})
        inbound_connections = _safe_int(frontend_row.get("scur")) or service.get("inbound_connections", 0)
        backend_connections = _safe_int(backend_row.get("scur")) or 0

        servers: list[RoutingServerResponse] = []
        route_labels: list[str] = []
        for server in service["servers"]:
            row = stat_index.get((service["name"], server["name"]), {})
            active_connections = _safe_int(row.get("scur")) or 0
            status = row.get("status") or "unknown"
            check_status = row.get("check_status") or row.get("check_desc")
            last_change_seconds = _safe_int(row.get("lastchg"))
            route_labels.append(f"{server['name']} {server['host']}:{server['port']} [{status}]")
            servers.append(
                RoutingServerResponse(
                    name=str(server["name"]),
                    host=str(server["host"]),
                    port=int(server["port"]),
                    status=status,
                    check_status=check_status,
                    active_connections=active_connections,
                    last_change_seconds=last_change_seconds,
                )
            )
        if not backend_connections:
            backend_connections = sum(server.active_connections for server in servers)

        total_inbound += inbound_connections
        total_backend += backend_connections
        route_services.append(
            RoutingServiceResponse(
                name=str(service["name"]),
                bind_port=bind_port,
                variant=variant_map.get(bind_port),
                inbound_connections=inbound_connections,
                backend_connections=backend_connections,
                routing_text=" -> ".join(route_labels),
                servers=servers,
            )
        )

    note = None
    if current_series <= 0:
        note = "Competition is not active; routing is parked."
    elif not route_services:
        note = f"No active listener data found for H{current_series}."

    return RoutingStatusResponse(
        configured=True,
        current_series=current_series,
        services=route_services,
        total_inbound_connections=total_inbound,
        total_backend_connections=total_backend,
        note=note,
    )


def _local_host_telemetry() -> HostTelemetryResponse:
    metrics = _collect_linux_host_metrics()
    docker_status = _service_state(_run_local, "docker")
    haproxy_status = _service_state(_run_local, "haproxy")
    referee_status = _service_state(_run_local, "koth-referee")
    return HostTelemetryResponse(
        host="192.168.0.12",
        role="lb",
        reachable=True,
        loadavg_1m=metrics["loadavg_1m"],
        loadavg_5m=metrics["loadavg_5m"],
        loadavg_15m=metrics["loadavg_15m"],
        mem_used_mb=metrics["mem_used_mb"],
        mem_total_mb=metrics["mem_total_mb"],
        mem_percent=metrics["mem_percent"],
        disk_used_gb=metrics["disk_used_gb"],
        disk_total_gb=metrics["disk_total_gb"],
        disk_percent=metrics["disk_percent"],
        uptime_seconds=metrics["uptime_seconds"],
        docker_status=docker_status,
        haproxy_status=haproxy_status,
        referee_status=referee_status,
        error=None,
    )


_REMOTE_HOST_METRICS_COMMAND = """python3 - <<'PY'
import json, os

data = {
    "loadavg_1m": None,
    "loadavg_5m": None,
    "loadavg_15m": None,
    "mem_used_mb": None,
    "mem_total_mb": None,
    "mem_percent": None,
    "disk_used_gb": None,
    "disk_total_gb": None,
    "disk_percent": None,
    "uptime_seconds": None,
}
try:
    load1, load5, load15 = os.getloadavg()
    data["loadavg_1m"] = load1
    data["loadavg_5m"] = load5
    data["loadavg_15m"] = load15
except OSError:
    pass
try:
    mem = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0])
    total = mem.get("MemTotal")
    available = mem.get("MemAvailable")
    if total:
        data["mem_total_mb"] = total // 1024
        data["mem_used_mb"] = max(total - (available or 0), 0) // 1024
        data["mem_percent"] = round(((total - (available or 0)) * 100) / total, 1)
except OSError:
    pass
try:
    stat = os.statvfs("/")
    total = stat.f_blocks * stat.f_frsize
    used = (stat.f_blocks - stat.f_bavail) * stat.f_frsize
    data["disk_total_gb"] = round(total / (1024 ** 3), 1)
    data["disk_used_gb"] = round(used / (1024 ** 3), 1)
    if stat.f_blocks:
        data["disk_percent"] = round(((stat.f_blocks - stat.f_bavail) * 100) / stat.f_blocks, 1)
except OSError:
    pass
try:
    with open("/proc/uptime", "r", encoding="utf-8") as handle:
        data["uptime_seconds"] = int(float(handle.read().split()[0]))
except OSError:
    pass
print(json.dumps(data))
PY"""


def _remote_host_telemetry(
    host: str,
    containers: list[dict],
) -> tuple[HostTelemetryResponse, list[ContainerTelemetryResponse]]:
    try:
        metrics_code, metrics_out, metrics_err = ssh_pool.exec(host, _REMOTE_HOST_METRICS_COMMAND)
    except Exception as exc:
        error = str(exc)
        return (
            HostTelemetryResponse(
                host=host,
                role="node",
                reachable=False,
                loadavg_1m=None,
                loadavg_5m=None,
                loadavg_15m=None,
                mem_used_mb=None,
                mem_total_mb=None,
                mem_percent=None,
                disk_used_gb=None,
                disk_total_gb=None,
                disk_percent=None,
                uptime_seconds=None,
                docker_status=None,
                haproxy_status=None,
                referee_status=None,
                error=error,
            ),
            [],
        )

    if metrics_code != 0:
        error = metrics_err.strip() or "host metrics command failed"
        return (
            HostTelemetryResponse(
                host=host,
                role="node",
                reachable=False,
                loadavg_1m=None,
                loadavg_5m=None,
                loadavg_15m=None,
                mem_used_mb=None,
                mem_total_mb=None,
                mem_percent=None,
                disk_used_gb=None,
                disk_total_gb=None,
                disk_percent=None,
                uptime_seconds=None,
                docker_status=None,
                haproxy_status=None,
                referee_status=None,
                error=error,
            ),
            [],
        )

    try:
        metrics = json.loads(metrics_out or "{}")
    except json.JSONDecodeError:
        metrics = {}

    live_name_by_service: dict[str, str] = {}
    if containers:
        current_series = int(containers[0]["series"])
        compose_dir = f"{SETTINGS.remote_series_root}/h{current_series}"
        compose_ps_command = f"cd {shlex.quote(compose_dir)} && docker compose ps --format json"
        compose_ps_code, compose_ps_out, compose_ps_err = ssh_pool.exec(host, compose_ps_command)
        if compose_ps_code == 0:
            for line in compose_ps_out.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                service_name = str(payload.get('Service') or '').strip()
                live_name = str(payload.get('Name') or payload.get('Names') or '').strip()
                if service_name and live_name:
                    live_name_by_service[service_name] = live_name
        elif compose_ps_err.strip():
            logger.warning("docker compose ps failed on %s: %s", host, compose_ps_err.strip())

    container_specs: list[tuple[str, str]] = []
    for item in containers:
        service_name = _compose_service_name(int(item["series"]), str(item["variant"]))
        live_name = live_name_by_service.get(service_name) or service_name
        container_specs.append((service_name, live_name))

    container_names = [live_name for _, live_name in container_specs if live_name]
    stats_index: dict[str, dict] = {}
    inspect_index: dict[str, dict] = {}

    if container_names:
        stats_command = (
            "docker stats --no-stream --format '{{json .}}' " + " ".join(container_names)
        )
        inspect_command = "docker inspect " + " ".join(container_names)
        stats_code, stats_out, stats_err = ssh_pool.exec(host, stats_command)
        inspect_code, inspect_out, inspect_err = ssh_pool.exec(host, inspect_command)

        if stats_code == 0:
            for line in stats_out.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                stats_index[payload.get("Name") or payload.get("Container") or ""] = payload
        elif stats_err.strip():
            logger.warning("docker stats failed on %s: %s", host, stats_err.strip())

        if inspect_code == 0:
            try:
                for item in json.loads(inspect_out or "[]"):
                    name = str(item.get("Name", "")).lstrip("/")
                    if name:
                        inspect_index[name] = item
            except json.JSONDecodeError:
                logger.warning("docker inspect returned non-json on %s", host)
        elif inspect_err.strip():
            logger.warning("docker inspect failed on %s: %s", host, inspect_err.strip())

    telemetry: list[ContainerTelemetryResponse] = []
    for item, (_, query_name) in zip(containers, container_specs):
        stats = stats_index.get(query_name, {})
        inspect = inspect_index.get(query_name, {})
        state = inspect.get("State", {})
        started_at_raw = state.get("StartedAt")
        finished_at_raw = state.get("FinishedAt")
        started_at = _parse_docker_timestamp(started_at_raw)
        finished_at = _parse_docker_timestamp(finished_at_raw)
        status = state.get("Status") or item["status"]
        telemetry.append(
            ContainerTelemetryResponse(
                machine_host=host,
                variant=str(item["variant"]),
                container_id=query_name,
                series=int(item["series"]),
                status=str(status),
                health=((state.get("Health") or {}).get("Status")),
                king=item.get("king"),
                cpu_percent=_safe_float(stats.get("CPUPerc")),
                memory_usage=stats.get("MemUsage"),
                memory_percent=_safe_float(stats.get("MemPerc")),
                pids=_safe_int(stats.get("PIDs")),
                restart_count=int(inspect.get("RestartCount", 0)) if inspect else None,
                started_at=started_at_raw,
                finished_at=finished_at_raw,
                exit_code=int(state.get("ExitCode")) if state.get("ExitCode") is not None else None,
                oom_killed=state.get("OOMKilled"),
                uptime_seconds=_duration_seconds(started_at) if state.get("Running") else None,
                downtime_seconds=(
                    _duration_seconds(finished_at)
                    if finished_at and not state.get("Running")
                    else (
                        max(0, int((started_at - finished_at).total_seconds()))
                        if started_at and finished_at and state.get("Running")
                        else None
                    )
                ),
                error=state.get("Error") or None,
            )
        )

    host_response = HostTelemetryResponse(
        host=host,
        role="node",
        reachable=True,
        loadavg_1m=metrics.get("loadavg_1m"),
        loadavg_5m=metrics.get("loadavg_5m"),
        loadavg_15m=metrics.get("loadavg_15m"),
        mem_used_mb=metrics.get("mem_used_mb"),
        mem_total_mb=metrics.get("mem_total_mb"),
        mem_percent=metrics.get("mem_percent"),
        disk_used_gb=metrics.get("disk_used_gb"),
        disk_total_gb=metrics.get("disk_total_gb"),
        disk_percent=metrics.get("disk_percent"),
        uptime_seconds=metrics.get("uptime_seconds"),
        docker_status="active",
        haproxy_status=None,
        referee_status=None,
        error=None,
    )
    return host_response, telemetry


def _telemetry_status() -> TelemetryStatusResponse:
    competition = db.get_competition()
    current_series = int(competition["current_series"])
    containers = db.list_containers(
        series=current_series if current_series > 0 else None,
        machine_hosts=SETTINGS.node_hosts,
    )
    containers_by_host: dict[str, list[dict]] = {host: [] for host in SETTINGS.node_hosts}
    for item in containers:
        containers_by_host.setdefault(str(item["machine_host"]), []).append(item)

    hosts: list[HostTelemetryResponse] = [_local_host_telemetry()]
    container_rows: list[ContainerTelemetryResponse] = []
    for host in SETTINGS.node_hosts:
        host_metrics, host_containers = _remote_host_telemetry(host, containers_by_host.get(host, []))
        hosts.append(host_metrics)
        container_rows.extend(host_containers)

    note = None
    if current_series <= 0:
        note = "Competition is stopped; container telemetry reflects the most recent known state."

    return TelemetryStatusResponse(
        current_series=current_series,
        generated_at=datetime.now(UTC),
        hosts=hosts,
        containers=sorted(container_rows, key=lambda item: (item.machine_host, item.variant)),
        note=note,
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
    current_series = int(comp["current_series"])
    containers = db.list_containers(
        series=current_series if current_series > 0 else None,
        machine_hosts=SETTINGS.node_hosts,
    )

    return StatusResponse(
        competition_status=comp["status"],
        current_series=current_series,
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


@app.get("/api/routing", response_model=RoutingStatusResponse, dependencies=[Depends(require_admin_api_key)])
def api_routing_status() -> RoutingStatusResponse:
    return _routing_status()


@app.get("/api/telemetry", response_model=TelemetryStatusResponse, dependencies=[Depends(require_admin_api_key)])
def api_telemetry_status() -> TelemetryStatusResponse:
    return _telemetry_status()


def _tail_log(path: Path, *, source: str, lines: int) -> LogTailResponse:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return LogTailResponse(
            source=source,
            path=str(path),
            readable=False,
            lines=[],
            note="log file does not exist",
        )
    except PermissionError:
        return LogTailResponse(
            source=source,
            path=str(path),
            readable=False,
            lines=[],
            note="log file is not readable by the referee service user",
        )
    except OSError as exc:
        logger.error("log tail failed for %s: %s", path, exc)
        return LogTailResponse(
            source=source,
            path=str(path),
            readable=False,
            lines=[],
            note=str(exc),
        )
    return LogTailResponse(
        source=source,
        path=str(path),
        readable=True,
        lines=content[-lines:],
        note=None,
    )


@app.get("/api/logs/referee", response_model=LogTailResponse, dependencies=[Depends(require_admin_api_key)])
def api_referee_logs(lines: int = Query(default=80, ge=1, le=500)) -> LogTailResponse:
    return _tail_log(SETTINGS.referee_log_path, source="referee", lines=lines)


@app.get("/api/logs/haproxy", response_model=LogTailResponse, dependencies=[Depends(require_admin_api_key)])
def api_haproxy_logs(lines: int = Query(default=80, ge=1, le=500)) -> LogTailResponse:
    return _tail_log(SETTINGS.haproxy_log_path, source="haproxy", lines=lines)


@app.get("/api/claims", response_model=list[ClaimObservationResponse], dependencies=[Depends(require_admin_api_key)])
def api_claims(
    limit: int = Query(default=60, ge=1, le=500),
    series: int | None = Query(default=None, ge=1),
) -> list[ClaimObservationResponse]:
    return [ClaimObservationResponse(**row) for row in db.list_claim_observations(limit=limit, series=series)]


@app.get("/api/teams", response_model=list[TeamResponse], dependencies=[Depends(require_admin_api_key)])
def api_teams() -> list[TeamResponse]:
    return [TeamResponse(**item) for item in db.list_teams()]


@app.post("/api/admin/teams", response_model=TeamStatusUpdateResponse, dependencies=[Depends(require_admin_api_key)])
def api_create_team(payload: TeamIn) -> TeamStatusUpdateResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="team name is required")
    if not Poller.is_valid_team_claim(name):
        raise HTTPException(status_code=422, detail="team name is not a valid claim")
    if db.team_exists(name):
        raise HTTPException(status_code=409, detail="team already exists")
    team = db.create_team(name)
    db.add_event(
        event_type="admin_action",
        severity="info",
        team_name=name,
        detail="Team created from dashboard",
    )
    return TeamStatusUpdateResponse(
        ok=True,
        detail="Team created",
        **team,
    )


@app.post(
    "/api/admin/teams/{team_name}/ban",
    response_model=TeamStatusUpdateResponse,
    dependencies=[Depends(require_admin_api_key)],
)
def api_ban_team(team_name: str) -> TeamStatusUpdateResponse:
    team = db.get_team(team_name)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    updated = db.set_team_status(team_name, status="banned")
    db.add_event(
        event_type="admin_action",
        severity="warning",
        team_name=team_name,
        detail="Team manually banned from dashboard",
    )
    return TeamStatusUpdateResponse(
        ok=True,
        detail="Team banned",
        **updated,
    )


@app.post(
    "/api/admin/teams/{team_name}/unban",
    response_model=TeamStatusUpdateResponse,
    dependencies=[Depends(require_admin_api_key)],
)
def api_unban_team(team_name: str) -> TeamStatusUpdateResponse:
    team = db.get_team(team_name)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    updated = db.set_team_status(team_name, status="active", offense_count=0)
    db.add_event(
        event_type="admin_action",
        severity="info",
        team_name=team_name,
        detail="Team manually unbanned from dashboard",
    )
    return TeamStatusUpdateResponse(
        ok=True,
        detail="Team unbanned",
        **updated,
    )


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
