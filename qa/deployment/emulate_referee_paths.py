from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "referee-server"))

from db import Database


class FakeSSHPool:
    def __init__(self, *, series_root: str):
        self.series_root = series_root.rstrip("/")
        self.commands: list[tuple[str, str]] = []

    def exec(self, host: str, command: str) -> tuple[int, str, str]:
        self.commands.append((host, command))
        if "docker --version && docker-compose --version" in command:
            return 0, "Docker version 27.0.1\nDocker Compose version v2.29.1\n", ""
        if "docker-compose.yml" in command:
            return 0, "OK\n", ""
        return 0, "SIMULATED\n", ""

    def close(self) -> None:
        return


def emulate_ssh(*, hosts: list[str], series: int, series_root: str) -> list[str]:
    ssh = FakeSSHPool(series_root=series_root)
    lines: list[str] = []
    try:
        for host in hosts:
            code, out, err = ssh.exec(host, "docker --version && docker-compose --version")
            lines.append(f"[{host}] docker check code={code}")
            lines.append((out or err).strip())

            compose_cmd = (
                f"test -f {series_root}/h{series}/docker-compose.yml && echo OK || echo MISSING"
            )
            code, out, err = ssh.exec(host, compose_cmd)
            lines.append(f"[{host}] H{series} compose: {(out or err).strip()} (code={code})")
    finally:
        ssh.close()
    return lines


def emulate_team_creation(*, teams: list[str]) -> list[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "referee.db"
        db = Database(db_path)
        db.initialize()
        db.upsert_team_names(teams)
        rows = db.list_teams()
        db.close()
    return [
        f"created {len(rows)} team records",
        *[f"- {row['name']} status={row['status']} points={row['total_points']}" for row in rows],
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emulate referee SSH reachability checks and local team-roster creation."
    )
    parser.add_argument(
        "--hosts",
        default="192.168.0.70,192.168.0.103,192.168.0.106",
        help="Comma-separated host/IP list to emulate",
    )
    parser.add_argument("--series", type=int, default=1, help="Series number to emulate (default: 1)")
    parser.add_argument(
        "--series-root",
        default="/opt/KOTH_orchestrator",
        help="Remote series root to emulate in compose checks",
    )
    parser.add_argument(
        "--teams",
        default="Team Alpha,Team Beta",
        help="Comma-separated team names to create in the temporary referee DB",
    )
    args = parser.parse_args()

    hosts = [item.strip() for item in args.hosts.split(",") if item.strip()]
    teams = [item.strip() for item in args.teams.split(",") if item.strip()]
    if not hosts:
        raise SystemExit("no hosts supplied")
    if not teams:
        raise SystemExit("no teams supplied")

    print("== Emulated SSH Path ==")
    for line in emulate_ssh(hosts=hosts, series=args.series, series_root=args.series_root):
        print(line)

    print()
    print("== Emulated Team Creation ==")
    for line in emulate_team_creation(teams=teams):
        print(line)


if __name__ == "__main__":
    main()
