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
