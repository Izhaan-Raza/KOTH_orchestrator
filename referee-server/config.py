from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_if_present() -> None:
    candidates = []

    override = os.getenv("KOTH_REFEREE_ENV")
    if override:
        candidates.append(Path(override).expanduser())

    module_env = Path(__file__).with_name(".env")
    cwd_env = Path.cwd() / ".env"
    candidates.extend([module_env, cwd_env])

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)

        for raw_line in resolved.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip("'\"")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_bool(value: str, *, default: bool) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


_load_dotenv_if_present()


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))

    db_path: Path = Path(os.getenv("DB_PATH", "./referee.db"))

    node_hosts: tuple[str, ...] = tuple(
        _split_csv(os.getenv("NODE_HOSTS", "192.168.0.70,192.168.0.103,192.168.0.106"))
    )
    node_priority: tuple[str, ...] = tuple(
        _split_csv(os.getenv("NODE_PRIORITY", "192.168.0.70,192.168.0.103,192.168.0.106"))
    )
    node_ssh_targets: tuple[str, ...] = tuple(_split_csv(os.getenv("NODE_SSH_TARGETS", "")))

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
    min_healthy_nodes: int = int(os.getenv("MIN_HEALTHY_NODES", "2"))

    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    rotation_interval_seconds: int = int(os.getenv("ROTATION_INTERVAL_SECONDS", "3600"))
    points_per_cycle: float = float(os.getenv("POINTS_PER_CYCLE", "1.0"))

    # <REMOTE_SERIES_ROOT>/h{series}/docker-compose.yml on each challenge node
    remote_series_root: str = os.getenv("REMOTE_SERIES_ROOT", "/opt/KOTH_orchestrator")
    container_name_template: str = os.getenv(
        "CONTAINER_NAME_TEMPLATE", "machineH{series}{variant}"
    )

    backend_url: str = os.getenv("BACKEND_URL", "")
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    allow_unsafe_no_admin_api_key: bool = _as_bool(
        os.getenv("ALLOW_UNSAFE_NO_ADMIN_API_KEY", "false"), default=False
    )
    allow_start_without_teams: bool = _as_bool(
        os.getenv("ALLOW_START_WITHOUT_TEAMS", "false"), default=False
    )

    static_dir: Path = Path(__file__).parent / "static"
    templates_dir: Path = Path(__file__).parent / "templates"

    def ssh_target_overrides(self) -> dict[str, str]:
        if not self.node_ssh_targets:
            return {}
        return dict(zip(self.node_hosts, self.node_ssh_targets))

    def validate_runtime(self) -> None:
        if not self.admin_api_key and not self.allow_unsafe_no_admin_api_key:
            raise RuntimeError(
                "ADMIN_API_KEY must be set; override only with ALLOW_UNSAFE_NO_ADMIN_API_KEY=true"
            )
        if not self.node_hosts:
            raise RuntimeError("NODE_HOSTS must define at least one challenge node")
        if self.node_ssh_targets and len(self.node_ssh_targets) != len(self.node_hosts):
            raise RuntimeError("NODE_SSH_TARGETS must have the same number of entries as NODE_HOSTS")
        if self.min_healthy_nodes < 1:
            raise RuntimeError("MIN_HEALTHY_NODES must be >= 1")
        if self.min_healthy_nodes > len(self.node_hosts):
            raise RuntimeError("MIN_HEALTHY_NODES cannot exceed NODE_HOSTS count")
        if not self.variants:
            raise RuntimeError("VARIANTS must define at least one variant")
        if self.total_series < 1:
            raise RuntimeError("TOTAL_SERIES must be >= 1")


SETTINGS = Settings()
