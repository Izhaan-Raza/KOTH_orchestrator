from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import UTC, datetime, timedelta
import logging
import statistics
import shlex
from threading import RLock
import time
from typing import Any

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from config import SETTINGS
from db import Database
from enforcer import Enforcer
from poller import Poller, VariantSnapshot
from runtime_logging import log_structured
from scorer import resolve_earliest_winners
from ssh_client import SSHClientPool
from webhook import fire_and_forget

logger = logging.getLogger("koth.referee")


class RuntimeGuardError(RuntimeError):
    pass


class RefereeRuntime:
    _VIOLATION_EXEMPTIONS: dict[tuple[int, str], set[str]] = {
        (1, "B"): {"authkeys_changed"},
        (7, "B"): {"shadow_changed"},
    }

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
        state = self.db.get_competition()
        if state["status"] == "running":
            next_rotation = state.get("next_rotation")
            if next_rotation:
                try:
                    run_at = datetime.fromisoformat(str(next_rotation))
                except ValueError:
                    run_at = datetime.now(UTC) + timedelta(seconds=SETTINGS.rotation_interval_seconds)
                    self.db.set_competition_state(next_rotation=run_at.isoformat())
                self._enable_rotation_job(run_at=run_at)

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)
        self.ssh_pool.close()

    def _set_next_rotation(self) -> str:
        next_rotation = datetime.now(UTC) + timedelta(seconds=SETTINGS.rotation_interval_seconds)
        next_rotation_iso = next_rotation.isoformat()
        self.db.set_competition_state(next_rotation=next_rotation_iso)
        return next_rotation_iso

    def _enable_rotation_job(self, *, run_at: datetime | None = None) -> None:
        effective_run_at = run_at or (datetime.now(UTC) + timedelta(seconds=SETTINGS.rotation_interval_seconds))
        if effective_run_at < datetime.now(UTC):
            effective_run_at = datetime.now(UTC)
        self.scheduler.add_job(
            self.rotate_next_series,
            "date",
            run_date=effective_run_at,
            id="rotate",
            replace_existing=True,
            max_instances=1,
        )

    def _disable_rotation_job(self) -> None:
        if self.scheduler.get_job("rotate"):
            self.scheduler.remove_job("rotate")

    def _arm_rotation_from_now(self) -> str:
        next_rotation_iso = self._set_next_rotation()
        self._enable_rotation_job(run_at=datetime.fromisoformat(next_rotation_iso))
        return next_rotation_iso

    def _fetch_teams_from_backend(self) -> list[str]:
        if not SETTINGS.backend_url:
            return []
        url = f"{SETTINGS.backend_url.rstrip('/')}/teams"
        try:
            response = httpx.get(url, timeout=8)
            response.raise_for_status()
            payload = response.json()
            team_names = [item["name"].strip() for item in payload if item.get("name")]
            log_structured(logger, logging.INFO, "backend_teams_loaded", url=url, teams=len(team_names))
            return team_names
        except Exception as exc:
            log_structured(logger, logging.ERROR, "backend_teams_failed", url=url, error=str(exc))
            self.db.add_event(
                event_type="integration",
                severity="critical",
                detail="Failed to load teams from backend",
                evidence={"url": url, "error": str(exc)},
            )
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
            response = httpx.post(url, json=body, timeout=8)
            response.raise_for_status()
            log_structured(logger, logging.INFO, "backend_scores_posted", url=url, series_completed=series_completed)
        except Exception as exc:
            log_structured(
                logger,
                logging.ERROR,
                "backend_scores_failed",
                url=url,
                series_completed=series_completed,
                error=str(exc),
            )
            self.db.add_event(
                event_type="integration",
                severity="critical",
                series=series_completed,
                detail="Failed to post final scores to backend",
                evidence={"url": url, "error": str(exc)},
            )
            return

    def _ensure_team_roster_available(self) -> None:
        if self.db.team_count() > 0:
            return
        if SETTINGS.allow_start_without_teams:
            self.db.add_event(
                event_type="lifecycle",
                severity="warning",
                detail="Competition started without registered teams due to ALLOW_START_WITHOUT_TEAMS=true",
            )
            return
        raise RuntimeGuardError(
            "No teams are registered. Populate teams locally or configure a reachable BACKEND_URL before starting."
        )

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

    def _write_authoritative_owner_to_variant(
        self,
        *,
        host: str,
        series: int,
        variant: str,
        owner_team: str,
    ) -> tuple[bool, str]:
        series_dir = shlex.quote(f"{SETTINGS.remote_series_root}/h{series}")
        service = shlex.quote(
            SETTINGS.container_name_template.format(
                series=series,
                variant=variant,
                variant_lower=variant.lower(),
            )
        )
        container_script = (
            f"printf '%s\\n' {shlex.quote(owner_team)} > /root/king.txt && "
            "chmod 644 /root/king.txt && "
            "chown root:root /root/king.txt"
        )
        full_command = (
            f"cd {series_dir} && "
            f"container_id=\"$({SETTINGS.docker_compose_cmd} ps -q {service} 2>/dev/null | head -n 1)\"; "
            "if [ -z \"$container_id\" ]; then echo CONTAINER_NOT_FOUND; exit 1; fi; "
            f"docker exec -u 0 \"$container_id\" sh -lc {shlex.quote(container_script)}"
        )
        try:
            code, out, err = self.ssh_pool.exec(host, full_command)
            return code == 0, (out or err)
        except Exception as exc:
            return False, str(exc)

    def _reconcile_authoritative_owner(
        self,
        *,
        series: int,
        variant: str,
        owner_team: str,
        snapshots: list[VariantSnapshot],
        poll_cycle: int,
    ) -> None:
        drifted_hosts = sorted(
            snap.node_host
            for snap in snapshots
            if snap.variant == variant and snap.status == "running" and snap.king != owner_team
        )
        if not drifted_hosts:
            return

        with ThreadPoolExecutor(max_workers=len(drifted_hosts)) as pool:
            futures = {
                pool.submit(
                    self._write_authoritative_owner_to_variant,
                    host=host,
                    series=series,
                    variant=variant,
                    owner_team=owner_team,
                ): host
                for host in drifted_hosts
            }
            for future in as_completed(futures):
                host = futures[future]
                ok, output = future.result()
                if ok:
                    self._log_event_and_webhook(
                        event_type="ownership",
                        severity="warning",
                        machine=host,
                        variant=variant,
                        series=series,
                        team_name=owner_team,
                        detail=f"Reconciled {variant} replica to authoritative owner",
                        evidence={"poll_cycle": poll_cycle},
                    )
                    continue
                self._log_event_and_webhook(
                    event_type="ownership",
                    severity="critical",
                    machine=host,
                    variant=variant,
                    series=series,
                    team_name=owner_team,
                    detail=f"Failed to reconcile {variant} replica to authoritative owner",
                    evidence={"poll_cycle": poll_cycle, "output": output[:1000]},
                )

    def start_competition(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] in {"starting", "running", "paused", "rotating", "faulted", "stopping"}:
                return

            self.db.reset_for_new_competition()
            team_names = self._fetch_teams_from_backend()
            if team_names:
                self.db.upsert_team_names(team_names)
            self._ensure_team_roster_available()
            self.db.set_competition_state(status="starting", current_series=0, previous_series=None, fault_reason=None)

            self.db.add_event(
                event_type="lifecycle",
                severity="info",
                series=1,
                detail="Competition started; deploying H1",
            )
            try:
                self._deploy_series_or_raise(series=1)
            except RuntimeGuardError:
                self._rollback_series_deploy(1)
                self.db.set_competition_state(
                    status="stopped",
                    current_series=0,
                    previous_series=None,
                    next_rotation=None,
                    fault_reason="Competition startup failed",
                )
                self._log_event_and_webhook(
                    event_type="lifecycle",
                    severity="critical",
                    series=1,
                    detail="Competition startup failed; referee left in stopped state",
                )
                raise

            self.db.set_competition_state(
                status="running",
                current_series=1,
                previous_series=None,
                started_at=datetime.now(UTC).isoformat(),
                fault_reason=None,
            )
            validated_at = datetime.now(UTC).isoformat()
            self.db.set_competition_state(last_validated_series=1, last_validated_at=validated_at)
            self._arm_rotation_from_now()
            fire_and_forget({"type": "competition_started", "series": 1})

    def stop_competition(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            current_series = int(state["current_series"])
            if state["status"] == "stopped":
                return

            self.poll_once()
            self.db.set_competition_state(status="stopping", fault_reason=None)
            if current_series > 0:
                self._run_compose_parallel(
                    current_series, f"{SETTINGS.docker_compose_cmd} down -v --remove-orphans"
                )

            self._disable_rotation_job()
            self._post_final_scores(current_series)

            self.db.set_competition_state(
                status="stopped",
                current_series=0,
                previous_series=None,
                next_rotation=None,
                fault_reason=None,
            )
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
            self.db.set_competition_state(status="paused", next_rotation=None, fault_reason=None)
            self._disable_rotation_job()
            self.db.add_event(event_type="admin_action", severity="info", detail="Rotation paused")

    def resume_rotation(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] != "paused":
                return
            series = int(state["current_series"])
            if series <= 0:
                raise RuntimeGuardError("Cannot resume without an active series")
            try:
                self._validate_current_series_or_raise(series=series)
            except RuntimeGuardError as exc:
                self.db.set_competition_state(
                    status="faulted",
                    next_rotation=None,
                    fault_reason=str(exc),
                )
                self._disable_rotation_job()
                raise
            self.db.set_competition_state(
                status="running",
                fault_reason=None,
                last_validated_series=series,
                last_validated_at=datetime.now(UTC).isoformat(),
            )
            self._arm_rotation_from_now()
            self.db.add_event(event_type="admin_action", severity="info", detail="Rotation resumed")

    def restart_current_series(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            series = int(state["current_series"])
            if series <= 0:
                return
            self.db.set_competition_state(status="rotating", previous_series=series, fault_reason=None)
            self._run_compose_parallel(
                series, f"{SETTINGS.docker_compose_cmd} down -v --remove-orphans"
            )
            try:
                self._deploy_series_or_raise(series=series)
            except RuntimeGuardError:
                self.db.set_competition_state(
                    status="faulted",
                    next_rotation=None,
                    previous_series=series,
                    fault_reason=f"Restart of current series H{series} failed",
                )
                self._disable_rotation_job()
                self._log_event_and_webhook(
                    event_type="rotation",
                    severity="critical",
                    series=series,
                    detail=f"Restart of current series H{series} failed; competition faulted for manual intervention",
                )
                raise
            self.db.set_competition_state(
                status="running",
                current_series=series,
                previous_series=None,
                fault_reason=None,
                last_validated_series=series,
                last_validated_at=datetime.now(UTC).isoformat(),
            )
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
                self.db.set_competition_state(
                    status="rotating",
                    previous_series=current_series,
                    fault_reason=None,
                )
                self._run_compose_parallel(
                    current_series, f"{SETTINGS.docker_compose_cmd} down -v --remove-orphans"
                )
            else:
                self.db.set_competition_state(
                    status="rotating",
                    previous_series=None,
                    fault_reason=None,
                )

            try:
                self._deploy_series_or_raise(series=target_series)
            except RuntimeGuardError as exc:
                self._rollback_series_deploy(target_series)
                if current_series > 0:
                    try:
                        self._deploy_series_or_raise(series=current_series)
                    except RuntimeGuardError as rollback_exc:
                        self._rollback_series_deploy(current_series)
                        self.db.set_competition_state(
                            status="faulted",
                            current_series=current_series,
                            previous_series=current_series,
                            next_rotation=None,
                            fault_reason=(
                                f"Rotation to H{target_series} failed and rollback to H{current_series} also failed"
                            ),
                        )
                        self._disable_rotation_job()
                        self._log_event_and_webhook(
                            event_type="rotation",
                            severity="critical",
                            series=target_series,
                            detail=(
                                f"Rotation to H{target_series} failed and rollback to H{current_series} "
                                "also failed; competition paused for manual intervention"
                            ),
                            evidence={
                                "rotation_error": str(exc),
                                "rollback_error": str(rollback_exc),
                            },
                        )
                        raise RuntimeGuardError(
                            f"Rotation to H{target_series} failed; rollback to H{current_series} also failed"
                        ) from rollback_exc

                    self.db.set_competition_state(status="running", current_series=current_series)
                    self.db.set_competition_state(
                        previous_series=None,
                        fault_reason=None,
                        last_validated_series=current_series,
                        last_validated_at=datetime.now(UTC).isoformat(),
                    )
                    self._arm_rotation_from_now()
                    self._log_event_and_webhook(
                        event_type="rotation",
                        severity="critical",
                        series=target_series,
                        detail=f"Rotation to H{target_series} failed; automatically rolled back to H{current_series}",
                        evidence={"rotation_error": str(exc)},
                    )
                    return

                self.db.set_competition_state(
                    status="faulted",
                    current_series=current_series,
                    previous_series=current_series,
                    next_rotation=None,
                    fault_reason=f"Rotation to H{target_series} failed without a recoverable current series",
                )
                self._disable_rotation_job()
                self._log_event_and_webhook(
                    event_type="rotation",
                    severity="critical",
                    series=target_series,
                    detail=f"Rotation to H{target_series} failed; competition paused for manual intervention",
                    evidence={"rotation_error": str(exc)},
                )
                raise

            self.db.reset_series_bans()
            self.db.set_competition_state(
                status="running",
                current_series=target_series,
                previous_series=None,
                fault_reason=None,
                last_validated_series=target_series,
                last_validated_at=datetime.now(UTC).isoformat(),
            )
            self._arm_rotation_from_now()
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
        log_structured(
            logger,
            logging.INFO if severity == "info" else logging.WARNING if severity == "warning" else logging.ERROR,
            "event_recorded",
            event_id=event_id,
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

    def _record_claim_observations(
        self,
        *,
        series: int,
        poll_cycle: int,
        snapshots: list[VariantSnapshot],
        winners: dict[str, Any],
        matrix_issues: list[str],
        insufficient_variants: set[str],
    ) -> None:
        by_variant: dict[str, list[VariantSnapshot]] = {variant: [] for variant in SETTINGS.variants}
        for snap in snapshots:
            by_variant.setdefault(snap.variant, []).append(snap)

        observations: list[dict[str, Any]] = []
        for variant, entries in by_variant.items():
            winner = winners.get(variant)
            if matrix_issues:
                selection_reason = "incomplete_snapshot_matrix"
            elif variant in insufficient_variants:
                selection_reason = "insufficient_healthy_replicas"
            elif winner is None:
                running_claims = [
                    entry for entry in entries
                    if entry.status == "running"
                    and entry.king is not None
                    and entry.king.lower() != "unclaimed"
                    and self.poller.is_valid_team_claim(entry.king)
                    and entry.king_mtime_epoch is not None
                ]
                selection_reason = "no_quorum" if running_claims else "no_valid_claims"
            else:
                selection_reason = winner.reason

            claims = [
                {
                    "host": entry.node_host,
                    "status": entry.status,
                    "king": entry.king,
                    "mtime_epoch": entry.king_mtime_epoch,
                }
                for entry in sorted(entries, key=lambda item: item.node_host)
            ]
            log_structured(
                logger,
                logging.INFO,
                "poll_variant_decision",
                poll_cycle=poll_cycle,
                series=series,
                variant=variant,
                selection_reason=selection_reason,
                winner_team=(winner.team_name if winner else None),
                winner_host=(winner.node_host if winner else None),
                winner_mtime_epoch=(winner.mtime_epoch if winner else None),
                supporting_nodes=(winner.supporting_nodes if winner else 0),
                claims=claims,
            )
            for entry in entries:
                observations.append(
                    {
                        "poll_cycle": poll_cycle,
                        "series": series,
                        "node_host": entry.node_host,
                        "variant": entry.variant,
                        "status": entry.status,
                        "king": entry.king,
                        "king_mtime_epoch": entry.king_mtime_epoch,
                        "observed_at": entry.checked_at.isoformat(),
                        "selected": (
                            winner is not None
                            and entry.node_host == winner.node_host
                            and entry.variant == winner.variant
                            and entry.king == winner.team_name
                            and entry.king_mtime_epoch == winner.mtime_epoch
                        ),
                        "selection_reason": selection_reason,
                    }
                )
        self.db.add_claim_observations(observations)

    def _capture_baselines(self, series: int, snapshots: list[VariantSnapshot]) -> None:
        for snap in snapshots:
            shadow_hash = self.poller.extract_sha256_or_missing(snap.sections.get("SHADOW", ""))
            authkeys_hash = self.poller.extract_sha256_or_missing(snap.sections.get("AUTHKEYS", ""))
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

    def _expected_snapshot_pairs(self) -> set[tuple[str, str]]:
        return {(host, variant) for host in SETTINGS.node_hosts for variant in SETTINGS.variants}

    def _snapshot_matrix_issues(self, snapshots: list[VariantSnapshot]) -> list[str]:
        expected = self._expected_snapshot_pairs()
        actual = {(snap.node_host, snap.variant) for snap in snapshots}
        missing = sorted(expected - actual)
        extras = sorted(actual - expected)
        issues: list[str] = []
        if missing:
            rendered = ", ".join(f"{host}/{variant}" for host, variant in missing)
            issues.append(f"missing snapshots: {rendered}")
        if extras:
            rendered = ", ".join(f"{host}/{variant}" for host, variant in extras)
            issues.append(f"unexpected snapshots: {rendered}")
        return issues

    def _running_snapshot_counts_by_variant(self, snapshots: list[VariantSnapshot]) -> dict[str, int]:
        counts = Counter[str]()
        for snap in snapshots:
            if snap.status == "running":
                counts[snap.variant] += 1
        return {variant: counts.get(variant, 0) for variant in SETTINGS.variants}

    def _healthy_running_host_count(self, snapshots: list[VariantSnapshot]) -> int:
        healthy_hosts = {snap.node_host for snap in snapshots if snap.status == "running"}
        return len(healthy_hosts)

    def _evaluate_series_health(
        self,
        *,
        series: int,
        snapshots: list[VariantSnapshot],
        deploy_results: dict[str, tuple[bool, str]],
    ) -> list[str]:
        issues = self._snapshot_matrix_issues(snapshots)
        healthy_hosts: set[str] = set()
        degraded_hosts: set[str] = set()

        for host, (ok, output) in sorted(deploy_results.items()):
            if not ok:
                issues.append(f"{host}: deploy command failed: {output[:200]}")

        for snap in snapshots:
            if snap.status == "degraded":
                degraded_hosts.add(snap.node_host)
                continue
            if snap.status != "running":
                issues.append(f"{snap.node_host}/{snap.variant}: status={snap.status}")
                continue

            king = (snap.king or "").strip().lower()
            if king != "unclaimed":
                issues.append(f"{snap.node_host}/{snap.variant}: king.txt={snap.king!r}")
                continue

            healthy_hosts.add(snap.node_host)

        if len(healthy_hosts) < SETTINGS.min_healthy_nodes:
            issues.append(
                f"only {len(healthy_hosts)} healthy node(s); MIN_HEALTHY_NODES={SETTINGS.min_healthy_nodes}"
            )

        return issues

    def _validate_current_series_or_raise(self, *, series: int) -> list[VariantSnapshot]:
        snapshots, summary = self._validate_series_state(series=series)
        if summary["issues"]:
            raise RuntimeGuardError(
                f"Current series H{series} failed resume validation: " + "; ".join(summary["issues"])
            )
        self.db.set_competition_state(
            last_validated_series=series,
            last_validated_at=datetime.now(UTC).isoformat(),
        )
        return snapshots

    def _validate_series_state(self, *, series: int) -> tuple[list[VariantSnapshot], dict[str, Any]]:
        snapshots, _ = self.poller.run_cycle(series=series)
        self._mark_clock_drift_degraded(series=series, snapshots=snapshots)
        self._apply_container_updates(series, snapshots)

        issues = self._snapshot_matrix_issues(snapshots)
        healthy_hosts = self._healthy_running_host_count(snapshots)
        if healthy_hosts < SETTINGS.min_healthy_nodes:
            issues.append(
                f"only {healthy_hosts} healthy node(s); MIN_HEALTHY_NODES={SETTINGS.min_healthy_nodes}"
            )
        healthy_counts = self._running_snapshot_counts_by_variant(snapshots)
        summary = {
            "current_series": series,
            "valid": not issues,
            "complete_snapshot_matrix": not any(issue.startswith("missing snapshots:") or issue.startswith("unexpected snapshots:") for issue in issues),
            "healthy_nodes": healthy_hosts,
            "total_nodes": len(SETTINGS.node_hosts),
            "min_healthy_nodes": SETTINGS.min_healthy_nodes,
            "healthy_counts_by_variant": healthy_counts,
            "issues": issues,
        }
        return snapshots, summary

    def validate_current_series(self) -> dict[str, Any]:
        with self._lock:
            state = self.db.get_competition()
            series = int(state["current_series"])
            if series <= 0:
                raise RuntimeGuardError("Cannot validate without an active series")
            _, summary = self._validate_series_state(series=series)
            if summary["valid"]:
                self.db.set_competition_state(
                    last_validated_series=series,
                    last_validated_at=datetime.now(UTC).isoformat(),
                )
            return summary

    def recover_current_series(self) -> dict[str, Any]:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] not in {"paused", "faulted"}:
                raise RuntimeGuardError("Recovery redeploy is only allowed from paused or faulted state")
            series = int(state["current_series"])
            if series <= 0:
                raise RuntimeGuardError("Cannot recover without an active series")

            self.db.set_competition_state(status="rotating", previous_series=series, fault_reason=None)
            self._disable_rotation_job()
            self._run_compose_parallel(
                series, f"{SETTINGS.docker_compose_cmd} down -v --remove-orphans"
            )
            try:
                self._deploy_series_or_raise(series=series)
            except RuntimeGuardError as exc:
                self.db.set_competition_state(
                    status="faulted",
                    current_series=series,
                    previous_series=series,
                    next_rotation=None,
                    fault_reason=f"Recovery redeploy for H{series} failed",
                )
                self._log_event_and_webhook(
                    event_type="rotation",
                    severity="critical",
                    series=series,
                    detail=f"Recovery redeploy for H{series} failed; competition remains faulted",
                    evidence={"error": str(exc)},
                )
                raise RuntimeGuardError(f"Recovery redeploy for H{series} failed") from exc

            validated_at = datetime.now(UTC).isoformat()
            self.db.set_competition_state(
                status="paused",
                current_series=series,
                previous_series=None,
                next_rotation=None,
                fault_reason=None,
                last_validated_series=series,
                last_validated_at=validated_at,
            )
            self.db.add_event(
                event_type="admin_action",
                severity="info",
                series=series,
                detail=f"Recovered current series H{series}; runtime remains paused pending resume",
            )
            return {
                "ok": True,
                "competition_status": "paused",
                "current_series": series,
                "fault_reason": None,
                "detail": f"Recovered current series H{series}; runtime remains paused pending resume",
            }

    def _rollback_series_deploy(self, series: int) -> None:
        down_results = self._run_compose_parallel(
            series, f"{SETTINGS.docker_compose_cmd} down -v --remove-orphans"
        )
        for host, (ok, output) in down_results.items():
            if not ok:
                self._log_event_and_webhook(
                    event_type="rotation",
                    severity="critical",
                    machine=host,
                    series=series,
                    detail="Rollback failed on node",
                    evidence={"output": output[:1000]},
                )

    def _deploy_series_or_raise(self, *, series: int) -> list[VariantSnapshot]:
        up_results = self._run_compose_parallel(
            series, f"{SETTINGS.docker_compose_cmd} up -d --force-recreate"
        )
        for host, (ok, output) in up_results.items():
            if not ok:
                self._log_event_and_webhook(
                    event_type="rotation",
                    severity="critical",
                    machine=host,
                    series=series,
                    detail="Deploy failed on node",
                    evidence={"output": output[:1000]},
                )

        deadline = time.monotonic() + SETTINGS.deploy_health_timeout_seconds
        attempt = 0
        baseline_snaps: list[VariantSnapshot] = []
        issues: list[str] = []
        while True:
            attempt += 1
            baseline_snaps, _ = self.poller.run_cycle(series=series)
            self._mark_clock_drift_degraded(series=series, snapshots=baseline_snaps)
            self._apply_container_updates(series, baseline_snaps)
            issues = self._evaluate_series_health(
                series=series,
                snapshots=baseline_snaps,
                deploy_results=up_results,
            )
            if not issues:
                if attempt > 1:
                    log_structured(
                        logger,
                        logging.INFO,
                        "deploy_health_recovered",
                        series=series,
                        attempts=attempt,
                    )
                self._capture_baselines(series=series, snapshots=baseline_snaps)
                return baseline_snaps
            if time.monotonic() >= deadline:
                break
            log_structured(
                logger,
                logging.WARNING,
                "deploy_health_retry",
                series=series,
                attempt=attempt,
                issues=issues,
            )
            time.sleep(SETTINGS.deploy_health_poll_seconds)

        self._log_series_health(series=series, snapshots=baseline_snaps)
        raise RuntimeGuardError(
            f"Series H{series} failed deployment health gate: " + "; ".join(issues)
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

            shadow_hash = self.poller.extract_sha256_or_missing(snap.sections.get("SHADOW", ""))
            authkeys_hash = self.poller.extract_sha256_or_missing(snap.sections.get("AUTHKEYS", ""))
            iptables_sig = self.poller.stable_signature(snap.sections.get("IPTABLES", ""))
            ports_sig = self.poller.stable_signature(snap.sections.get("PORTS", ""))

            key = (snap.node_host, snap.variant)
            hits: list[ViolationHit] = []
            exempted = self._VIOLATION_EXEMPTIONS.get((series, snap.variant), set())

            if baseline.get("ports_sig") and ports_sig and baseline["ports_sig"] != ports_sig:
                hits.append(
                    ViolationHit(
                        12,
                        "service_ports_changed",
                        {"expected_sig": baseline["ports_sig"], "actual_sig": ports_sig},
                    )
                )
            if baseline.get("iptables_sig") and iptables_sig and baseline["iptables_sig"] != iptables_sig:
                hits.append(
                    ViolationHit(
                        13,
                        "iptables_changed",
                        {"expected_sig": baseline["iptables_sig"], "actual_sig": iptables_sig},
                    )
                )
            if (
                baseline.get("shadow_hash") is not None
                and baseline["shadow_hash"] != shadow_hash
            ):
                hits.append(
                    ViolationHit(
                        14,
                        "shadow_changed",
                        {
                            "shadow_expected": baseline.get("shadow_hash"),
                            "shadow_actual": shadow_hash,
                        },
                    )
                )
            if (
                baseline.get("authkeys_hash") is not None
                and baseline["authkeys_hash"] != authkeys_hash
            ):
                hits.append(
                    ViolationHit(
                        15,
                        "authkeys_changed",
                        {
                            "authkeys_expected": baseline.get("authkeys_hash"),
                            "authkeys_actual": authkeys_hash,
                        },
                    )
                )
            if hits:
                bucket = violations.setdefault(key, [])
                for hit in hits:
                    if hit.offense_name not in exempted:
                        bucket.append(hit)

    def poll_once(self) -> None:
        with self._lock:
            state = self.db.get_competition()
            if state["status"] != "running":
                return
            series = int(state["current_series"])
            if series <= 0:
                return

            snapshots, violations = self.poller.run_cycle(series=series)
            self._mark_clock_drift_degraded(series=series, snapshots=snapshots)
            self._merge_baseline_violations(series=series, snapshots=snapshots, violations=violations)
            poll_cycle = self.db.increment_poll_cycle()
            self._apply_container_updates(series, snapshots)

            matrix_issues = self._snapshot_matrix_issues(snapshots)
            if matrix_issues:
                self._log_event_and_webhook(
                    event_type="node_health",
                    severity="critical",
                    series=series,
                    detail="Poll cycle skipped scoring due to incomplete snapshot matrix",
                    evidence={"issues": matrix_issues, "poll_cycle": poll_cycle},
                )

            healthy_counts = self._running_snapshot_counts_by_variant(snapshots)
            by_variant: dict[str, list[VariantSnapshot]] = {variant: [] for variant in SETTINGS.variants}
            for snap in snapshots:
                by_variant.setdefault(snap.variant, []).append(snap)

            insufficient_variants: set[str] = set()
            for variant, entries in by_variant.items():
                healthy_count = healthy_counts.get(variant, 0)
                if healthy_count >= SETTINGS.min_healthy_nodes:
                    continue
                has_valid_claim = any(
                    entry.status == "running"
                    and entry.king is not None
                    and entry.king.lower() != "unclaimed"
                    and self.poller.is_valid_team_claim(entry.king)
                    for entry in entries
                )
                has_unhealthy_replica = any(entry.status != "running" for entry in entries)
                if not has_valid_claim and not has_unhealthy_replica:
                    continue
                insufficient_variants.add(variant)
                self._log_event_and_webhook(
                    event_type="node_health",
                    severity="critical",
                    variant=variant,
                    series=series,
                    detail=f"Scoring skipped for {variant} due to insufficient healthy replicas",
                    evidence={
                        "healthy_nodes": healthy_count,
                        "min_healthy_nodes": SETTINGS.min_healthy_nodes,
                        "poll_cycle": poll_cycle,
                    },
                )

            current_owners = {
                row["variant"]: row
                for row in self.db.list_variant_owners(series=series)
            }
            winners = resolve_earliest_winners(snapshots, current_owners=current_owners)
            self._record_claim_observations(
                series=series,
                poll_cycle=poll_cycle,
                snapshots=snapshots,
                winners=winners,
                matrix_issues=matrix_issues,
                insufficient_variants=insufficient_variants,
            )
            for variant, winner in winners.items():
                if matrix_issues:
                    continue
                healthy_count = healthy_counts.get(variant, 0)
                if variant in insufficient_variants:
                    continue
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

                previous_owner = current_owners.get(variant)
                previous_team = str(previous_owner.get("owner_team")) if previous_owner else None
                if previous_team != winner.team_name:
                    evidence = {
                        "supporting_nodes": winner.supporting_nodes,
                        "healthy_nodes": healthy_count,
                        "accepted_mtime_epoch": winner.mtime_epoch,
                        "source_node_host": winner.node_host,
                        "previous_owner": previous_team,
                        "poll_cycle": poll_cycle,
                    }
                    self.db.set_variant_owner(
                        series=series,
                        variant=variant,
                        owner_team=winner.team_name,
                        accepted_mtime_epoch=winner.mtime_epoch,
                        source_node_host=winner.node_host,
                        evidence=evidence,
                    )
                    current_owners[variant] = {
                        "variant": variant,
                        "owner_team": winner.team_name,
                    }
                    self._log_event_and_webhook(
                        event_type="ownership",
                        severity="info",
                        machine=winner.node_host,
                        variant=variant,
                        series=series,
                        team_name=winner.team_name,
                        detail=f"Authoritative owner for {variant} accepted with quorum",
                        evidence=evidence,
                    )

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
                    detail=f"+{SETTINGS.points_per_cycle} point for {variant} by authoritative quorum ownership",
                    evidence={
                        "mtime_epoch": winner.mtime_epoch,
                        "poll_cycle": poll_cycle,
                        "supporting_nodes": winner.supporting_nodes,
                    },
                )
                self._reconcile_authoritative_owner(
                    series=series,
                    variant=variant,
                    owner_team=winner.team_name,
                    snapshots=snapshots,
                    poll_cycle=poll_cycle,
                )

            # Escalate once per team per cycle.
            snapshot_map = {(s.node_host, s.variant): s for s in snapshots}
            teams_to_escalate: set[str] = set()
            for key, hits in violations.items():
                if not hits:
                    continue
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
                    log_structured(
                        logger,
                        logging.WARNING,
                        "violation_detected",
                        poll_cycle=poll_cycle,
                        team_name=team,
                        machine=node_host,
                        variant=variant,
                        series=series,
                        offense_id=hit.offense_id,
                        offense_name=hit.offense_name,
                        evidence=hit.evidence,
                        action=action,
                    )
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
