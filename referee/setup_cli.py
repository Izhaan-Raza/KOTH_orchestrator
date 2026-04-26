from __future__ import annotations

import argparse
import shlex
import sys

from config import SETTINGS
from ssh_client import SSHClientPool


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"[ OK ] {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(description="KOTH referee preflight helper")
    parser.add_argument("--series", type=int, default=1, help="Series to validate (default H1)")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 1. Validate runtime config (fails fast with clear error message)
    # ------------------------------------------------------------------
    try:
        SETTINGS.validate_runtime()
    except RuntimeError as exc:
        _fail(f"Config validation failed: {exc}")
    _ok("Config valid")

    if not SETTINGS.remote_series_root:
        _fail("REMOTE_SERIES_ROOT must be set")
    _ok(f"REMOTE_SERIES_ROOT = {SETTINGS.remote_series_root}")

    series = args.series
    series_dir = f"{SETTINGS.remote_series_root}/h{series}"

    ssh = SSHClientPool(
        username=SETTINGS.ssh_user,
        private_key_path=SETTINGS.ssh_private_key,
        port=SETTINGS.ssh_port,
        timeout_seconds=SETTINGS.ssh_timeout_seconds,
        strict_host_key_checking=SETTINGS.ssh_strict_host_key_checking,
        host_target_overrides=SETTINGS.ssh_target_overrides(),
    )
    try:
        failures: list[str] = []

        for host in SETTINGS.node_hosts:
            prefix = f"[{host}]"

            # ------------------------------------------------------------------
            # 2. SSH reachability check
            # ------------------------------------------------------------------
            try:
                code, out, err = ssh.exec(host, "hostname")
                if code != 0:
                    failures.append(f"{prefix} SSH failed (code={code}): {err.strip()}")
                    continue
                _ok(f"{prefix} SSH reachable (hostname={out.strip()})")
            except Exception as exc:
                failures.append(f"{prefix} SSH connection error: {exc}")
                continue

            # ------------------------------------------------------------------
            # 3. Docker + compose version check
            # ------------------------------------------------------------------
            code, out, err = ssh.exec(host, f"docker --version && {SETTINGS.docker_compose_cmd} version")
            if code != 0:
                failures.append(f"{prefix} Docker/compose check failed: {(err or out).strip()}")
            else:
                first_line = (out or "").splitlines()[0].strip()
                _ok(f"{prefix} Docker OK ({first_line})")

            # ------------------------------------------------------------------
            # 4. Series directory and compose file present
            # ------------------------------------------------------------------
            quoted_dir = shlex.quote(series_dir)
            code, out, _ = ssh.exec(
                host,
                f"test -d {quoted_dir} && echo DIR_OK || echo DIR_MISSING; "
                f"test -f {quoted_dir}/docker-compose.yml && echo COMPOSE_OK || echo COMPOSE_MISSING",
            )
            result_lines = out.strip().splitlines()
            dir_result = result_lines[0].strip() if result_lines else "DIR_MISSING"
            compose_result = result_lines[1].strip() if len(result_lines) > 1 else "COMPOSE_MISSING"

            if dir_result != "DIR_OK":
                failures.append(f"{prefix} H{series} series dir missing: {series_dir}")
            else:
                _ok(f"{prefix} H{series} series dir present")

            if compose_result != "COMPOSE_OK":
                failures.append(f"{prefix} H{series} docker-compose.yml missing in {series_dir}")
            else:
                _ok(f"{prefix} H{series} docker-compose.yml present")

            # ------------------------------------------------------------------
            # 5. Compose file is parseable (config dry-run)
            # ------------------------------------------------------------------
            if compose_result == "COMPOSE_OK":
                code, out, err = ssh.exec(
                    host,
                    f"cd {quoted_dir} && {SETTINGS.docker_compose_cmd} config --quiet 2>&1 && echo CONFIG_VALID",
                )
                if code != 0 or "CONFIG_VALID" not in out:
                    failures.append(
                        f"{prefix} H{series} compose config invalid: {(err or out).strip()[:300]}"
                    )
                else:
                    _ok(f"{prefix} H{series} compose config valid")

        if failures:
            print("\n--- PREFLIGHT FAILURES ---", file=sys.stderr)
            for msg in failures:
                print(f"  {msg}", file=sys.stderr)
            _fail(f"{len(failures)} preflight check(s) failed")

        print("\nALL CHECKS PASSED")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()
