from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_bool(value: str, *, default: bool) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))

    db_path: Path = Path(os.getenv("DB_PATH", "./referee.db"))

    node_hosts: tuple[str, ...] = tuple(
        _split_csv(os.getenv("NODE_HOSTS", "10.0.0.11,10.0.0.12,10.0.0.13"))
    )
    node_priority: tuple[str, ...] = tuple(
        _split_csv(os.getenv("NODE_PRIORITY", "10.0.0.11,10.0.0.12,10.0.0.13"))
    )

    ssh_user: str = os.getenv("SSH_USER", "root")
    ssh_port: int = int(os.getenv("SSH_PORT", "22"))
    ssh_private_key: str = os.getenv("SSH_PRIVATE_KEY", "~/.ssh/id_rsa")
    ssh_timeout_seconds: int = int(os.getenv("SSH_TIMEOUT_SECONDS", "8"))
    ssh_strict_host_key_checking: bool = _as_bool(
        os.getenv("SSH_STRICT_HOST_KEY_CHECKING", "true"), default=True
    )

    variants: tuple[str, ...] = tuple(_split_csv(os.getenv("VARIANTS", "A,B,C")))
    total_series: int = int(os.getenv("TOTAL_SERIES", "8"))
    max_clock_drift_seconds: int = int(os.getenv("MAX_CLOCK_DRIFT_SECONDS", "2"))

    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    rotation_interval_seconds: int = int(os.getenv("ROTATION_INTERVAL_SECONDS", "3600"))
    points_per_cycle: float = float(os.getenv("POINTS_PER_CYCLE", "1.0"))

    # /opt/koth/h{series}/docker-compose.yml on each challenge node
    remote_series_root: str = os.getenv("REMOTE_SERIES_ROOT", "/opt/koth")
    container_name_template: str = os.getenv(
        "CONTAINER_NAME_TEMPLATE", "koth_h{series}{variant_lower}"
    )

    backend_url: str = os.getenv("BACKEND_URL", "")
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")

    static_dir: Path = Path(__file__).parent / "static"
    templates_dir: Path = Path(__file__).parent / "templates"


SETTINGS = Settings()
