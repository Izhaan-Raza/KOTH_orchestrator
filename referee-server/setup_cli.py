from __future__ import annotations

import argparse
import shlex

from config import SETTINGS
from ssh_client import SSHClientPool


def main() -> None:
    parser = argparse.ArgumentParser(description="KOTH referee setup helper")
    parser.add_argument("--series", type=int, default=1, help="Series to validate (default H1)")
    args = parser.parse_args()
    SETTINGS.validate_runtime()

    ssh = SSHClientPool(
        username=SETTINGS.ssh_user,
        private_key_path=SETTINGS.ssh_private_key,
        port=SETTINGS.ssh_port,
        timeout_seconds=SETTINGS.ssh_timeout_seconds,
        strict_host_key_checking=SETTINGS.ssh_strict_host_key_checking,
        host_target_overrides=SETTINGS.ssh_target_overrides(),
    )
    try:
        for host in SETTINGS.node_hosts:
            code, out, err = ssh.exec(
                host, f"docker --version && {SETTINGS.docker_compose_cmd} version"
            )
            print(f"[{host}] code={code}")
            print((out or err).strip())

            series_dir = shlex.quote(f"{SETTINGS.remote_series_root}/h{args.series}")
            cmd = f"test -f {series_dir}/docker-compose.yml && echo OK || echo MISSING"
            code, out, _ = ssh.exec(host, cmd)
            print(f"[{host}] H{args.series} compose: {out.strip()} (code={code})")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
