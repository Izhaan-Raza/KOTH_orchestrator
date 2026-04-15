from __future__ import annotations

import hashlib
import re
import shlex
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config import SETTINGS
from ssh_client import SSHClientPool

VARIANT_START = re.compile(r"^===VARIANT:([A-Z])===$")
SECTION_LINE = re.compile(r"^===([A-Z_]+)===$")


@dataclass
class VariantSnapshot:
    node_host: str
    variant: str
    king: str | None
    king_mtime_epoch: int | None
    status: str
    sections: dict[str, str]
    checked_at: datetime


@dataclass
class ViolationHit:
    offense_id: int
    offense_name: str
    evidence: dict[str, Any]


class Poller:
    def __init__(self, ssh_pool: SSHClientPool):
        self._ssh = ssh_pool

    def _build_probe_command(self, series: int) -> str:
        variant_fragments: list[str] = []
        for variant in SETTINGS.variants:
            container = shlex.quote(
                SETTINGS.container_name_template.format(
                    series=series,
                    variant=variant,
                    variant_lower=variant.lower(),
                )
            )
            fragment = f"""
echo "===VARIANT:{variant}===";
docker exec {container} sh -lc '
  echo "===NODE_EPOCH===";
  date +%s 2>/dev/null || echo "EPOCH_FAIL";
  echo "===KING===";
  cat /root/king.txt 2>/dev/null || echo "FILE_MISSING";
  echo "===KING_STAT===";
  stat -c "%Y %a %U:%G %F" /root/king.txt 2>/dev/null || echo "STAT_FAIL";
  echo "===ROOT_DIR===";
  stat -c "%a" /root 2>/dev/null;
  echo "===IMMUTABLE===";
  lsattr /root/king.txt 2>/dev/null || echo "NO_LSATTR";
  echo "===CRON===";
  crontab -l 2>/dev/null; cat /etc/cron.d/* 2>/dev/null | grep -i king;
  echo "===PROCS===";
  ps aux 2>/dev/null | grep -E "inotify|fswatch|king\\.txt" | grep -v grep;
  echo "===IPTABLES===";
  iptables -L -n 2>/dev/null;
  echo "===PORTS===";
  ss -tlnp 2>/dev/null;
  echo "===SHADOW===";
  sha256sum /etc/shadow 2>/dev/null;
  echo "===AUTHKEYS===";
  sha256sum /root/.ssh/authorized_keys 2>/dev/null;
' 2>/tmp/referee_probe.err || cat /tmp/referee_probe.err;
echo "===END_VARIANT===";
"""
            variant_fragments.append(fragment)
        return "\n".join(variant_fragments)

    def _parse_snapshots(self, node_host: str, output: str) -> list[VariantSnapshot]:
        now = datetime.now(UTC)
        lines = output.splitlines()
        snapshots: list[VariantSnapshot] = []

        idx = 0
        while idx < len(lines):
            m = VARIANT_START.match(lines[idx].strip())
            if not m:
                idx += 1
                continue
            variant = m.group(1)
            idx += 1

            sections: dict[str, list[str]] = {}
            current_section = ""
            while idx < len(lines):
                raw = lines[idx]
                line = raw.strip()
                idx += 1

                if line == "===END_VARIANT===":
                    break

                section = SECTION_LINE.match(line)
                if section:
                    current_section = section.group(1)
                    sections.setdefault(current_section, [])
                    continue

                if current_section:
                    sections[current_section].append(raw)

            flat_sections = {k: "\n".join(v).strip() for k, v in sections.items()}
            king = self._normalize_king(flat_sections.get("KING", ""))
            king_mtime = self._parse_mtime(flat_sections.get("KING_STAT", ""))
            status = "running"
            if not flat_sections:
                status = "failed"
            elif king is None and "FILE_MISSING" in flat_sections.get("KING", ""):
                status = "failed"

            snapshots.append(
                VariantSnapshot(
                    node_host=node_host,
                    variant=variant,
                    king=king,
                    king_mtime_epoch=king_mtime,
                    status=status,
                    sections=flat_sections,
                    checked_at=now,
                )
            )

        return snapshots

    @staticmethod
    def _normalize_king(raw: str) -> str | None:
        if not raw:
            return None
        line = raw.splitlines()[0].strip()
        if not line or line == "FILE_MISSING":
            return None
        return line

    @staticmethod
    def is_valid_team_claim(team_name: str) -> bool:
        normalized = team_name.strip()
        if not normalized or len(normalized) > 128:
            return False
        if normalized.lower() == "unclaimed":
            return False
        return all(ord(ch) >= 32 for ch in normalized)

    @staticmethod
    def _parse_mtime(raw: str) -> int | None:
        if not raw or "STAT_FAIL" in raw:
            return None
        first = raw.splitlines()[0].strip()
        parts = first.split()
        if not parts:
            return None
        try:
            return int(parts[0])
        except ValueError:
            return None

    def _detect_violations(self, snap: VariantSnapshot) -> list[ViolationHit]:
        out: list[ViolationHit] = []
        king_stat = snap.sections.get("KING_STAT", "")
        king = snap.sections.get("KING", "")
        root_dir = snap.sections.get("ROOT_DIR", "")
        immutable = snap.sections.get("IMMUTABLE", "")
        cron = snap.sections.get("CRON", "")
        procs = snap.sections.get("PROCS", "")

        if king_stat and "STAT_FAIL" not in king_stat:
            fields = king_stat.splitlines()[0].split()
            if len(fields) >= 4:
                perm = fields[1]
                owner = fields[2]
                file_type = " ".join(fields[3:]).lower()
                if perm != "644":
                    out.append(ViolationHit(1, "king_perm_changed", {"perm": perm}))
                if owner != "root:root":
                    out.append(ViolationHit(2, "king_owner_changed", {"owner": owner}))
                if "regular file" not in file_type:
                    out.append(ViolationHit(5, "king_not_regular", {"file_type": file_type}))

        if "FILE_MISSING" in king:
            out.append(ViolationHit(4, "king_deleted", {"king": king}))

        if root_dir and root_dir.splitlines()[0].strip() != "700":
            out.append(ViolationHit(6, "root_dir_perm_changed", {"root_dir": root_dir.strip()}))

        if immutable and " i " in f" {immutable} ":
            out.append(ViolationHit(3, "king_immutable", {"lsattr": immutable.strip()}))

        if re.search(r"king", cron, re.IGNORECASE):
            out.append(ViolationHit(7, "cron_king_persistence", {"cron": cron[:500]}))

        if re.search(r"inotify|fswatch|king\.txt", procs, re.IGNORECASE):
            out.append(ViolationHit(8, "watchdog_process", {"procs": procs[:500]}))

        return out

    @staticmethod
    def extract_sha256(raw: str) -> str | None:
        if not raw:
            return None
        line = raw.splitlines()[0].strip()
        if not line:
            return None
        token = line.split()[0]
        if re.fullmatch(r"[0-9a-fA-F]{64}", token):
            return token.lower()
        return None

    @staticmethod
    def stable_signature(raw: str) -> str | None:
        if not raw:
            return None
        normalized = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
        if not normalized:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def run_cycle(
        self,
        *,
        series: int,
    ) -> tuple[list[VariantSnapshot], dict[tuple[str, str], list[ViolationHit]]]:
        command = self._build_probe_command(series)
        snapshots: list[VariantSnapshot] = []
        violations: dict[tuple[str, str], list[ViolationHit]] = {}
        if not SETTINGS.node_hosts:
            return snapshots, violations

        with ThreadPoolExecutor(max_workers=len(SETTINGS.node_hosts)) as pool:
            futures = {
                pool.submit(self._ssh.exec, host, command): host for host in SETTINGS.node_hosts
            }
            for future in as_completed(futures):
                host = futures[future]
                try:
                    code, out, err = future.result()
                    if code != 0 and not out.strip():
                        snap_time = datetime.now(UTC)
                        for variant in SETTINGS.variants:
                            snapshots.append(
                                VariantSnapshot(
                                    node_host=host,
                                    variant=variant,
                                    king=None,
                                    king_mtime_epoch=None,
                                    status="unreachable",
                                    sections={"ERROR": err.strip()},
                                    checked_at=snap_time,
                                )
                            )
                        continue

                    parsed = self._parse_snapshots(host, out)
                    if not parsed:
                        snap_time = datetime.now(UTC)
                        for variant in SETTINGS.variants:
                            snapshots.append(
                                VariantSnapshot(
                                    node_host=host,
                                    variant=variant,
                                    king=None,
                                    king_mtime_epoch=None,
                                    status="failed",
                                    sections={"ERROR": err.strip(), "RAW": out[:500]},
                                    checked_at=snap_time,
                                )
                            )
                        continue

                    for snap in parsed:
                        snapshots.append(snap)
                        hits = self._detect_violations(snap)
                        if hits:
                            violations[(snap.node_host, snap.variant)] = hits
                except Exception as exc:
                    snap_time = datetime.now(UTC)
                    for variant in SETTINGS.variants:
                        snapshots.append(
                            VariantSnapshot(
                                node_host=host,
                                variant=variant,
                                king=None,
                                king_mtime_epoch=None,
                                status="unreachable",
                                sections={"EXCEPTION": str(exc)},
                                checked_at=snap_time,
                            )
                        )

        return snapshots, violations
