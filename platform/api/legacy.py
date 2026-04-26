import time
from fastapi import APIRouter

router = APIRouter()

# Mock endpoints to satisfy the legacy v1 dashboard.html JS requirements

@router.get("/api/status")
def get_status():
    return {
        "competition_status": "running",
        "current_series": 0,
        "active_teams": 0,
        "containers": []
    }

@router.get("/api/runtime")
def get_runtime():
    return {
        "competition_status": "running",
        "current_series": 0,
        "previous_series": 0,
        "last_validated_series": 0,
        "last_validated_at": None,
        "next_poll_seconds": None,
        "next_rotation_seconds": None,
        "poll_interval_seconds": 30,
        "active_jobs": [],
        "fault_reason": None
    }

@router.get("/api/teams")
def get_teams():
    return []

@router.get("/api/events")
def get_events(limit: int = 40):
    return []

@router.get("/api/admin/public/config")
def get_public_config():
    return {
        "orchestrator_host": "localhost",
        "port_ranges": "10000-20000",
        "headline": "KOTH Platform v2",
        "subheadline": "Dynamic generalized architecture is active."
    }

@router.get("/api/admin/public/notifications")
def get_public_notifications():
    return []

@router.get("/api/routing")
def get_routing():
    return {
        "services": [],
        "total_inbound_connections": 0,
        "total_backend_connections": 0,
        "current_series": 0,
        "note": "Legacy HAProxy routing is disabled in v2."
    }

@router.get("/api/telemetry")
def get_telemetry():
    return {
        "hosts": [],
        "containers": [],
        "note": "Telemetry is managed via Node APIs in v2."
    }

@router.get("/api/claims")
def get_claims(limit: int = 30):
    return []

@router.get("/api/logs/referee")
def get_referee_logs(lines: int = 60):
    return {"readable": True, "lines": ["Referee logs are handled natively in v2."]}

@router.get("/api/logs/haproxy")
def get_haproxy_logs(lines: int = 60):
    return {"readable": True, "lines": ["HAProxy logs are not applicable in v2."]}
