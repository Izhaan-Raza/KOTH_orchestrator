from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TeamStatus = Literal["active", "warned", "series_banned", "banned"]
CompetitionStatus = Literal["stopped", "starting", "running", "paused", "rotating", "faulted", "stopping"]


class TeamResponse(BaseModel):
    name: str
    status: TeamStatus
    offense_count: int
    total_points: float


class EventResponse(BaseModel):
    id: int
    type: str
    severity: Literal["info", "warning", "critical"]
    machine: str | None
    series: int | None
    team_name: str | None
    detail: str
    evidence: dict | None
    timestamp: datetime


class ContainerResponse(BaseModel):
    machine_host: str
    variant: Literal["A", "B", "C"]
    container_id: str
    series: int
    status: str
    king: str | None
    king_mtime_epoch: int | None
    last_checked: datetime | None


class StatusResponse(BaseModel):
    competition_status: CompetitionStatus
    current_series: int
    next_rotation_seconds: int | None
    active_teams: int
    containers: list[ContainerResponse]


class RuntimeResponse(BaseModel):
    competition_status: CompetitionStatus
    current_series: int
    previous_series: int | None
    next_poll_seconds: int | None
    poll_interval_seconds: int
    next_rotation_seconds: int | None
    fault_reason: str | None
    last_validated_series: int | None
    last_validated_at: datetime | None
    active_jobs: list[str]


class LbServerResponse(BaseModel):
    name: str
    host: str
    port: int
    active_connections: int


class LbServiceResponse(BaseModel):
    name: str
    bind_port: int
    inbound_connections: int
    backend_connections: int
    servers: list[LbServerResponse]


class LbStatusResponse(BaseModel):
    configured: bool
    services: list[LbServiceResponse]
    total_inbound_connections: int
    total_backend_connections: int
    note: str | None = None


class RoutingServerResponse(BaseModel):
    name: str
    host: str
    port: int
    status: str | None
    check_status: str | None
    active_connections: int
    last_change_seconds: int | None


class RoutingServiceResponse(BaseModel):
    name: str
    bind_port: int
    variant: Literal["A", "B", "C"] | None
    inbound_connections: int
    backend_connections: int
    routing_text: str
    servers: list[RoutingServerResponse]


class RoutingStatusResponse(BaseModel):
    configured: bool
    current_series: int
    services: list[RoutingServiceResponse]
    total_inbound_connections: int
    total_backend_connections: int
    note: str | None = None


class HostTelemetryResponse(BaseModel):
    host: str
    role: Literal["lb", "node"]
    reachable: bool
    loadavg_1m: float | None
    loadavg_5m: float | None
    loadavg_15m: float | None
    mem_used_mb: int | None
    mem_total_mb: int | None
    mem_percent: float | None
    disk_used_gb: float | None
    disk_total_gb: float | None
    disk_percent: float | None
    uptime_seconds: int | None
    docker_status: str | None
    haproxy_status: str | None
    referee_status: str | None
    error: str | None = None


class ContainerTelemetryResponse(BaseModel):
    machine_host: str
    variant: Literal["A", "B", "C"]
    container_id: str
    series: int
    status: str
    health: str | None
    king: str | None
    cpu_percent: float | None
    memory_usage: str | None
    memory_percent: float | None
    pids: int | None
    restart_count: int | None
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    oom_killed: bool | None
    uptime_seconds: int | None
    downtime_seconds: int | None
    error: str | None = None


class TelemetryStatusResponse(BaseModel):
    current_series: int
    generated_at: datetime
    hosts: list[HostTelemetryResponse]
    containers: list[ContainerTelemetryResponse]
    note: str | None = None


class ValidationResponse(BaseModel):
    current_series: int
    valid: bool
    complete_snapshot_matrix: bool
    healthy_nodes: int
    total_nodes: int
    min_healthy_nodes: int
    healthy_counts_by_variant: dict[str, int]
    issues: list[str]


class RecoveryResponse(BaseModel):
    ok: bool
    competition_status: CompetitionStatus
    current_series: int
    fault_reason: str | None
    detail: str


class ClaimObservationResponse(BaseModel):
    id: int
    poll_cycle: int
    series: int
    node_host: str
    variant: Literal["A", "B", "C"]
    status: str
    king: str | None
    king_mtime_epoch: int | None
    observed_at: datetime
    selected: bool
    selection_reason: str | None


class LogTailResponse(BaseModel):
    source: Literal["referee", "haproxy"]
    path: str
    readable: bool
    lines: list[str]
    note: str | None = None


class SkipRequest(BaseModel):
    target_series: int = Field(ge=1)


class TeamIn(BaseModel):
    name: str


class TeamStatusUpdateResponse(BaseModel):
    ok: bool
    name: str
    status: TeamStatus
    offense_count: int
    total_points: float
    detail: str


class PublicDashboardConfigResponse(BaseModel):
    orchestrator_host: str | None
    port_ranges: str | None
    headline: str | None
    subheadline: str | None
    updated_at: datetime | None


class PublicDashboardConfigUpdate(BaseModel):
    orchestrator_host: str | None = None
    port_ranges: str | None = None
    headline: str | None = None
    subheadline: str | None = None


class PublicNotificationResponse(BaseModel):
    id: int
    message: str
    severity: Literal["info", "warning", "critical"]
    created_at: datetime


class PublicNotificationIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    severity: Literal["info", "warning", "critical"] = "info"


class PublicDashboardResponse(BaseModel):
    current_series: int
    competition_status: CompetitionStatus
    orchestrator_host: str
    port_ranges: str
    headline: str
    subheadline: str
    updated_at: datetime | None
    notifications: list[PublicNotificationResponse]


class WebhookPayload(BaseModel):
    event_id: int
    event_type: str
    severity: str
    machine: str | None
    series: int | None
    team_name: str | None
    detail: str
    evidence: dict | None
    timestamp: datetime
