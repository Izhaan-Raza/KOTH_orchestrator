from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
import statistics
import shlex
from threading import RLock
from typing import Any

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from config import SETTINGS
from db import Database
from enforcer import Enforcer
from poller import Poller, VariantSnapshot
from scorer import resolve_earliest_winners
from ssh_client import SSHClientPool
from webhook import fire_and_forget


class RefereeRuntime:
    def __init__(self, db: Database, ssh_pool: SSHClientPool):
        self.db = db
        self.ssh_pool = ssh_pool
        self.poller = Poller(ssh_pool)
        self.enforcer = Enforcer(db)
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = RLock()

    def start_scheduler(self) -> None:
        self.scheduler.start()
        if not self.scheduler.get_job("poll"):
            self.scheduler.add_job(
                self.poll_once,
                "interval",
                seconds=SETTINGS.poll_interval_seconds,
                id="poll",
                replace_existing=True,
                max_instances=1,
            )

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)
        self.ssh_pool.close()

    def _set_next_rotation(self) -> str:
        next_rotation = datetime.now(UTC) + timedelta(seconds=SETTINGS.rotation_interval_seconds)
        next_rotation_iso = next_rotation.isoformat()
        self.db.set_competition_state(next_rotation=next_rotation_iso)
        return next_rotation_iso

    def _enable_rotation_job(self) -> None:
        if not self.scheduler.get_job("rotate"):
            self.scheduler.add_job(
                self.rotate_next_series,
                "interval",
                seconds=SETTINGS.rotation_interval_seconds,
                id="rotate",
                replace_existing=True,
                max_instances=1,
            )

    def _disable_rotation_job(self) -> None:
        if self.scheduler.get_job("rotate"):
            self.scheduler.remove_job("rotate")

    def _fetch_teams_from_backend(self) -> list[str]:
        if not SETTINGS.backend_url:
            return []
        url = f"{SETTINGS.backend_url.rstrip('/')}/teams"
        try:
            response = httpx.get(url, timeout=8)
            response.raise_for_status()
            payload = response.json()
            return [item["name"].strip() for item in payload if item.get("name")]
        except Exception:
            return []

    def _post_final_scores(self, series_completed: int) -> None:
        if not SETTINGS.backend_url:
            return
        teams = self.db.list_teams()
        body = {
            "competition_ended_at": datetime.now(UTC).isoformat(),
            "series_completed": series_completed,
            "teams": teams,
        }
        url = f"{SETTINGS.backend_url.rstrip('/')}/teams/points"
        try:
            httpx.post(url, json=body, timeout=8)
        except Exception:
            return

    def _run_compose_on_node(self, host: str, series: int, command: str) -> tuple[str, bool, str]:
        series_dir = shlex.quote(f"{SETTINGS.remote_series_root}/h{series}")
        full_command = f"cd {series_dir} && {command}"
        try:
            code, out, err = self.ssh_pool.exec(host, full_command)
            return host, code == 0, (out or err)
        except Exception as exc:
            return host, False, str(exc)

    def _run_compose_parallel(self, series: int, command: str) -> dict[str, tuple[bool, str]]:
        results: dict[str, tuple[bool, str]] = {}
        if not SETTINGS.node_hosts:
            return results
        with ThreadPoolExecutor(max_workers=len(SETTINGS.node_hosts)) as pool:
            futures = {
                pool.submit(self._run_compose_on_node, host, series, command): host
                for host in SETTINGS.node_hosts
            }
            for future in as_completed(futures):
                host, ok, output = future.result()
                results[host] = (ok, output)
        return results

    def start_competition(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] in {"running", "paused"}:
                return

            self.db.reset_for_new_competition()
            team_names = self._fetch_teams_from_backend()
            if team_names:
                self.db.upsert_team_names(team_names)

            self.db.set_competition_state(
                status="running",
                current_series=1,
                started_at=datetime.now(UTC).isoformat(),
            )
            self._set_next_rotation()
            self._enable_rotation_job()

            self.db.add_event(
                event_type="lifecycle",
                severity="info",
                series=1,
                detail="Competition started; deploying H1",
            )
            fire_and_forget({"type": "competition_started", "series": 1})

            up_results = self._run_compose_parallel(1, "docker-compose up -d --force-recreate")
            for host, (ok, output) in up_results.items():
                if not ok:
                    self.db.add_event(
                        event_type="rotation",
                        severity="critical",
                        machine=host,
                        series=1,
                        detail="Deploy failed on node",
                        evidence={"output": output[:1000]},
                    )
            baseline_snaps, _ = self.poller.run_cycle(series=1)
            self._mark_clock_drift_degraded(series=1, snapshots=baseline_snaps)
            self._apply_container_updates(1, baseline_snaps)
            self._log_series_health(series=1, snapshots=baseline_snaps)
            self._capture_baselines(series=1, snapshots=baseline_snaps)

    def stop_competition(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            current_series = int(state["current_series"])
            if state["status"] == "stopped":
                return

            self.poll_once()
            if current_series > 0:
                self._run_compose_parallel(current_series, "docker-compose down -v --remove-orphans")

            self._disable_rotation_job()
            self._post_final_scores(current_series)

            self.db.set_competition_state(status="stopped", current_series=0, next_rotation="")
            self.db.add_event(
                event_type="lifecycle",
                severity="info",
                detail="Competition stopped",
            )
            fire_and_forget({"type": "competition_stopped"})

    def pause_rotation(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] != "running":
                return
            self.db.set_competition_state(status="paused")
            self._disable_rotation_job()
            self.db.add_event(event_type="admin_action", severity="info", detail="Rotation paused")

    def resume_rotation(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] != "paused":
                return
            self.db.set_competition_state(status="running")
            self._set_next_rotation()
            self._enable_rotation_job()
            self.db.add_event(event_type="admin_action", severity="info", detail="Rotation resumed")

    def restart_current_series(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            series = int(state["current_series"])
            if series <= 0:
                return
            self._run_compose_parallel(series, "docker-compose down -v --remove-orphans")
            self._run_compose_parallel(series, "docker-compose up -d --force-recreate")
            self.db.add_event(
                event_type="rotation",
                severity="warning",
                series=series,
                detail=f"Restarted current series H{series}",
            )

    def rotate_to_series(self, target_series: int) -> None:
        with self._lock:
            if target_series < 1 or target_series > SETTINGS.total_series:
                return
            state = self.db.get_competition()
            current_series = int(state["current_series"])

            if current_series > 0:
                self.poll_once()
                self._run_compose_parallel(current_series, "docker-compose down -v --remove-orphans")

            self.db.reset_series_bans()
            up_results = self._run_compose_parallel(target_series, "docker-compose up -d --force-recreate")
            for host, (ok, output) in up_results.items():
                if not ok:
                    self._log_event_and_webhook(
                        event_type="rotation",
                        severity="critical",
                        machine=host,
                        series=target_series,
                        detail="Deploy failed on node",
                        evidence={"output": output[:1000]},
                    )
            baseline_snaps, _ = self.poller.run_cycle(series=target_series)
            self._mark_clock_drift_degraded(series=target_series, snapshots=baseline_snaps)
            self._apply_container_updates(target_series, baseline_snaps)
            self._log_series_health(series=target_series, snapshots=baseline_snaps)
            self._capture_baselines(series=target_series, snapshots=baseline_snaps)
            self.db.set_competition_state(current_series=target_series)
            self._set_next_rotation()
            self.db.add_event(
                event_type="rotation",
                severity="info",
                series=target_series,
                detail=f"Rotated to H{target_series}",
            )

    def rotate_next_series(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] != "running":
                return
            current_series = int(state["current_series"])
            target = current_series + 1
            if target > SETTINGS.total_series:
                self.stop_competition()
                return
        self.rotate_to_series(target)

    def _status_for_team(self, team_name: str) -> str | None:
        team = self.db.get_team(team_name)
        if team is None:
            return None
        return str(team["status"])

    def _log_event_and_webhook(
        self,
        *,
        event_type: str,
        severity: str,
        detail: str,
        machine: str | None = None,
        variant: str | None = None,
        series: int | None = None,
        team_name: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        event_id = self.db.add_event(
            event_type=event_type,
            severity=severity,
            machine=machine,
            variant=variant,
            series=series,
            team_name=team_name,
            detail=detail,
            evidence=evidence,
        )
        fire_and_forget(
            {
                "event_id": event_id,
                "event_type": event_type,
                "severity": severity,
                "machine": machine,
                "variant": variant,
                "series": series,
                "team_name": team_name,
                "detail": detail,
                "evidence": evidence,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def _apply_container_updates(self, series: int, snapshots: list[VariantSnapshot]) -> None:
        node_to_idx = {host: i + 1 for i, host in enumerate(SETTINGS.node_hosts)}
        for snap in snapshots:
            node_idx = node_to_idx.get(snap.node_host, 0)
            container_id = f"H{series}{snap.variant}_Node{node_idx}"
            self.db.upsert_container_status(
                machine_host=snap.node_host,
                variant=snap.variant,
                container_id=container_id,
                series=series,
                status=snap.status,
                king=snap.king,
                king_mtime_epoch=snap.king_mtime_epoch,
                last_checked=snap.checked_at.isoformat(),
            )

    def _capture_baselines(self, series: int, snapshots: list[VariantSnapshot]) -> None:
        for snap in snapshots:
            shadow_hash = self.poller.extract_sha256(snap.sections.get("SHADOW", ""))
            authkeys_hash = self.poller.extract_sha256(snap.sections.get("AUTHKEYS", ""))
            iptables_sig = self.poller.stable_signature(snap.sections.get("IPTABLES", ""))
            ports_sig = self.poller.stable_signature(snap.sections.get("PORTS", ""))
            self.db.upsert_baseline(
                machine_host=snap.node_host,
                variant=snap.variant,
                series=series,
                shadow_hash=shadow_hash,
                authkeys_hash=authkeys_hash,
                iptables_sig=iptables_sig,
                ports_sig=ports_sig,
            )

    def _mark_clock_drift_degraded(self, *, series: int, snapshots: list[VariantSnapshot]) -> set[str]:
        epochs: dict[str, int] = {}
        for snap in snapshots:
            raw = snap.sections.get("NODE_EPOCH", "")
            first = raw.splitlines()[0].strip() if raw else ""
            if not first or first == "EPOCH_FAIL":
                continue
            try:
                epochs[snap.node_host] = int(first)
            except ValueError:
                continue

        if len(epochs) < 2:
            return set()

        baseline = int(statistics.median(epochs.values()))
        degraded_hosts = {
            host
            for host, epoch in epochs.items()
            if abs(epoch - baseline) > SETTINGS.max_clock_drift_seconds
        }
        for snap in snapshots:
            if snap.node_host in degraded_hosts and snap.status == "running":
                snap.status = "degraded"

        for host in sorted(degraded_hosts):
            self._log_event_and_webhook(
                event_type="node_health",
                severity="warning",
                machine=host,
                series=series,
                detail="Node excluded from scoring due to clock drift",
                evidence={
                    "node_epoch": epochs.get(host),
                    "median_epoch": baseline,
                    "max_clock_drift_seconds": SETTINGS.max_clock_drift_seconds,
                },
            )
        return degraded_hosts

    def _log_series_health(self, *, series: int, snapshots: list[VariantSnapshot]) -> None:
        for snap in snapshots:
            if snap.status != "running":
                self._log_event_and_webhook(
                    event_type="node_health",
                    severity="critical",
                    machine=snap.node_host,
                    variant=snap.variant,
                    series=series,
                    team_name=snap.king,
                    detail="Container not healthy after deployment",
                    evidence={"status": snap.status},
                )
                continue
            if snap.king is not None and snap.king.lower() != "unclaimed":
                self._log_event_and_webhook(
                    event_type="node_health",
                    severity="warning",
                    machine=snap.node_host,
                    variant=snap.variant,
                    series=series,
                    team_name=snap.king,
                    detail="Container king.txt not reset to unclaimed after deploy",
                    evidence={"king": snap.king},
                )

    def _merge_baseline_violations(
        self,
        *,
        series: int,
        snapshots: list[VariantSnapshot],
        violations: dict[tuple[str, str], list[Any]],
    ) -> None:
        from poller import ViolationHit

        for snap in snapshots:
            baseline = self.db.get_baseline(
                machine_host=snap.node_host,
                variant=snap.variant,
                series=series,
            )
            if baseline is None:
                continue

            shadow_hash = self.poller.extract_sha256(snap.sections.get("SHADOW", ""))
            authkeys_hash = self.poller.extract_sha256(snap.sections.get("AUTHKEYS", ""))
            iptables_sig = self.poller.stable_signature(snap.sections.get("IPTABLES", ""))
            ports_sig = self.poller.stable_signature(snap.sections.get("PORTS", ""))

            key = (snap.node_host, snap.variant)
            bucket = violations.setdefault(key, [])

            if baseline.get("ports_sig") and ports_sig and baseline["ports_sig"] != ports_sig:
                bucket.append(
                    ViolationHit(
                        12,
                        "service_ports_changed",
                        {"expected_sig": baseline["ports_sig"], "actual_sig": ports_sig},
                    )
                )
            if baseline.get("iptables_sig") and iptables_sig and baseline["iptables_sig"] != iptables_sig:
                bucket.append(
                    ViolationHit(
                        13,
                        "iptables_changed",
                        {"expected_sig": baseline["iptables_sig"], "actual_sig": iptables_sig},
                    )
                )
            if (
                (baseline.get("shadow_hash") and shadow_hash and baseline["shadow_hash"] != shadow_hash)
                or (
                    baseline.get("authkeys_hash")
                    and authkeys_hash
                    and baseline["authkeys_hash"] != authkeys_hash
                )
            ):
                bucket.append(
                    ViolationHit(
                        14,
                        "credential_material_changed",
                        {
                            "shadow_expected": baseline.get("shadow_hash"),
                            "shadow_actual": shadow_hash,
                            "authkeys_expected": baseline.get("authkeys_hash"),
                            "authkeys_actual": authkeys_hash,
                        },
                    )
                )

    def poll_once(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] == "stopped":
                return
            series = int(state["current_series"])
            if series <= 0:
                return

            snapshots, violations = self.poller.run_cycle(series=series)
            self._mark_clock_drift_degraded(series=series, snapshots=snapshots)
            self._merge_baseline_violations(series=series, snapshots=snapshots, violations=violations)
            poll_cycle = self.db.increment_poll_cycle()
            self._apply_container_updates(series, snapshots)

            winners = resolve_earliest_winners(snapshots)
            for variant, winner in winners.items():
                team_status = self._status_for_team(winner.team_name)
                if team_status is None:
                    self._log_event_and_webhook(
                        event_type="points_awarded",
                        severity="warning",
                        machine=winner.node_host,
                        variant=variant,
                        series=series,
                        team_name=winner.team_name,
                        detail="Unknown team claim ignored",
                        evidence={"mtime_epoch": winner.mtime_epoch},
                    )
                    continue
                if not self.poller.is_valid_team_claim(winner.team_name):
                    self._log_event_and_webhook(
                        event_type="points_awarded",
                        severity="warning",
                        machine=winner.node_host,
                        variant=variant,
                        series=series,
                        team_name=winner.team_name,
                        detail="Malformed team claim ignored",
                        evidence={"mtime_epoch": winner.mtime_epoch},
                    )
                    continue
                if team_status in {"series_banned", "banned"}:
                    self._log_event_and_webhook(
                        event_type="ban",
                        severity="info",
                        machine=winner.node_host,
                        variant=variant,
                        series=series,
                        team_name=winner.team_name,
                        detail=f"Claim ignored due to status={team_status}",
                        evidence={"mtime_epoch": winner.mtime_epoch},
                    )
                    continue

                self.db.add_points(
                    winner.team_name,
                    variant,
                    series,
                    SETTINGS.points_per_cycle,
                    poll_cycle,
                )
                self._log_event_and_webhook(
                    event_type="points_awarded",
                    severity="info",
                    machine=winner.node_host,
                    variant=variant,
                    series=series,
                    team_name=winner.team_name,
                    detail=f"+{SETTINGS.points_per_cycle} point for {variant} by earliest change",
                    evidence={"mtime_epoch": winner.mtime_epoch, "poll_cycle": poll_cycle},
                )

            # Escalate once per team per cycle.
            snapshot_map = {(s.node_host, s.variant): s for s in snapshots}
            teams_to_escalate: set[str] = set()
            for key in violations:
                snap = snapshot_map.get(key)
                if snap is None or not snap.king:
                    continue
                if snap.king.lower() == "unclaimed":
                    continue
                if self.db.team_exists(snap.king):
                    teams_to_escalate.add(snap.king)

            team_actions: dict[str, str] = {}
            for team in teams_to_escalate:
                result = self.enforcer.escalate_team(team)
                team_actions[team] = result.action
                self._log_event_and_webhook(
                    event_type="ban",
                    severity="warning" if result.action == "warning" else "critical",
                    team_name=team,
                    series=series,
                    detail=f"Team action escalated: {result.action}",
                    evidence={"offense_count": result.offense_count},
                )

            for (node_host, variant), hits in violations.items():
                snap = snapshot_map.get((node_host, variant))
                if snap is None or not snap.king:
                    continue
                team = snap.king
                if not self.db.team_exists(team):
                    continue
                action = team_actions.get(team, "warning")
                for hit in hits:
                    self.enforcer.record_violation(
                        team_name=team,
                        machine=node_host,
                        variant=variant,
                        series=series,
                        offense_id=hit.offense_id,
                        offense_name=hit.offense_name,
                        evidence=hit.evidence,
                        action=action,
                    )
