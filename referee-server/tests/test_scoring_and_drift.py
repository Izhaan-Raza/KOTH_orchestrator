from __future__ import annotations

import importlib
import os
import tempfile
import types
import unittest
from datetime import UTC, datetime, timedelta
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from pathlib import Path
import sys
import itertools
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if "paramiko" not in sys.modules:
    fake_paramiko = types.SimpleNamespace(
        SSHClient=object,
        RejectPolicy=object,
        AutoAddPolicy=object,
    )
    sys.modules["paramiko"] = fake_paramiko

from poller import VariantSnapshot
from poller import Poller
from poller import ViolationHit
from scheduler import RefereeRuntime, RuntimeGuardError
from scorer import resolve_earliest_winners
from db import Database
from config import SETTINGS


class DummySSH:
    def __init__(self) -> None:
        self.commands: list[tuple[str, str]] = []

    def exec(self, host: str, command: str):
        self.commands.append((host, command))
        return 0, "OK", ""

    def close(self) -> None:
        return


class DummyScheduler:
    def __init__(self):
        self.jobs: dict[str, dict[str, object]] = {}
        self.started = False

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        _ = wait
        self.jobs.clear()

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def get_jobs(self):
        return [types.SimpleNamespace(id=job_id) for job_id in sorted(self.jobs)]

    def add_job(self, func, trigger, id, replace_existing, max_instances, **kwargs) -> None:
        _ = func, replace_existing, max_instances
        self.jobs[id] = {"trigger": trigger, **kwargs}

    def remove_job(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)


class DummyTemplates:
    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def TemplateResponse(self, *args, **kwargs):
        _ = args, kwargs
        return HTMLResponse("<html><body>ok</body></html>")


def _override_runtime_settings(testcase: unittest.TestCase) -> None:
    overrides = {
        "node_hosts": ("192.168.0.102", "192.168.0.103", "192.168.0.106"),
        "node_priority": ("192.168.0.102", "192.168.0.103", "192.168.0.106"),
        "variants": ("A", "B", "C"),
        "min_healthy_nodes": 2,
    }
    originals = {name: getattr(SETTINGS, name) for name in overrides}
    for name, value in overrides.items():
        object.__setattr__(SETTINGS, name, value)

    def restore() -> None:
        for name, value in originals.items():
            object.__setattr__(SETTINGS, name, value)

    testcase.addCleanup(restore)


def _snapshot(
    *,
    node_host: str,
    variant: str = "A",
    king: str | None = "Team Alpha",
    king_mtime_epoch: int | None = 1000,
    status: str = "running",
    node_epoch: int | None = 1000,
) -> VariantSnapshot:
    sections = {}
    if node_epoch is not None:
        sections["NODE_EPOCH"] = str(node_epoch)
    return VariantSnapshot(
        node_host=node_host,
        variant=variant,
        king=king,
        king_mtime_epoch=king_mtime_epoch,
        status=status,
        sections=sections,
        checked_at=datetime.now(UTC),
    )


class ScoringAndDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        _override_runtime_settings(self)

    def test_resolve_winner_excludes_degraded_and_uses_node_priority_tie_break(self) -> None:
        snapshots = [
            _snapshot(node_host="192.168.0.106", king="Team A", king_mtime_epoch=900, status="degraded"),
            _snapshot(node_host="192.168.0.102", king="Team A", king_mtime_epoch=1000, status="running"),
            _snapshot(node_host="192.168.0.103", king="Team A", king_mtime_epoch=1000, status="running"),
        ]

        winners = resolve_earliest_winners(snapshots)
        self.assertEqual(winners["A"].team_name, "Team A")
        self.assertEqual(winners["A"].node_host, "192.168.0.102")
        self.assertEqual(winners["A"].supporting_nodes, 2)

    def test_resolve_winner_skips_malformed_claims(self) -> None:
        snapshots = [
            _snapshot(node_host="192.168.0.102", king="Bad\x01Team", king_mtime_epoch=900),
            _snapshot(node_host="192.168.0.103", king="Good Team", king_mtime_epoch=950),
            _snapshot(node_host="192.168.0.106", king="Good Team", king_mtime_epoch=960),
        ]

        winners = resolve_earliest_winners(snapshots)
        self.assertEqual(winners["A"].team_name, "Good Team")

    def test_resolve_winner_requires_quorum_for_new_owner(self) -> None:
        snapshots = [
            _snapshot(node_host="192.168.0.102", king="Team Alpha", king_mtime_epoch=900),
            _snapshot(node_host="192.168.0.103", king="Team Beta", king_mtime_epoch=850),
            _snapshot(node_host="192.168.0.106", king="unclaimed", king_mtime_epoch=1000),
        ]

        winners = resolve_earliest_winners(snapshots)
        self.assertEqual(winners, {})

    def test_existing_authoritative_owner_wins_when_it_keeps_quorum(self) -> None:
        snapshots = [
            _snapshot(node_host="192.168.0.102", king="Team Alpha", king_mtime_epoch=1000),
            _snapshot(node_host="192.168.0.103", king="Team Alpha", king_mtime_epoch=1010),
            _snapshot(node_host="192.168.0.106", king="Team Beta", king_mtime_epoch=900),
        ]

        winners = resolve_earliest_winners(
            snapshots,
            current_owners={"A": {"owner_team": "Team Alpha"}},
        )
        self.assertEqual(winners["A"].team_name, "Team Alpha")
        self.assertEqual(winners["A"].supporting_nodes, 2)

    def test_mark_clock_drift_degraded(self) -> None:
        runtime = object.__new__(RefereeRuntime)
        runtime._log_event_and_webhook = Mock()

        snapshots = [
            _snapshot(node_host="192.168.0.102", node_epoch=1000),
            _snapshot(node_host="192.168.0.103", node_epoch=1001),
            _snapshot(node_host="192.168.0.106", node_epoch=1010),
        ]

        degraded = RefereeRuntime._mark_clock_drift_degraded(runtime, series=1, snapshots=snapshots)
        self.assertEqual(degraded, {"192.168.0.106"})
        self.assertEqual(snapshots[2].status, "degraded")
        runtime._log_event_and_webhook.assert_called_once()


class RuntimeSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        _override_runtime_settings(self)

    def make_runtime(self) -> tuple[RefereeRuntime, Database]:
        fd, raw_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_path = Path(raw_path)

        db = Database(db_path)
        db.initialize()
        self.addCleanup(lambda: db_path.exists() and db_path.unlink())
        self.addCleanup(db.close)
        runtime = RefereeRuntime(db, DummySSH())
        return runtime, db

    def test_start_competition_requires_team_roster(self) -> None:
        runtime, db = self.make_runtime()
        runtime._run_compose_parallel = Mock(return_value={})
        runtime.poller.run_cycle = Mock(return_value=([], {}))

        with self.assertRaises(RuntimeGuardError):
            runtime.start_competition()

        self.assertEqual(db.get_competition()["status"], "stopped")
        self.assertEqual(db.team_count(), 0)

    def test_start_competition_with_existing_teams_enters_running(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        runtime._run_compose_parallel = Mock(return_value={})
        runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
                ],
                {},
            )
        )

        runtime.start_competition()

        state = db.get_competition()
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["current_series"], 1)

    def test_start_competition_rolls_back_failed_deploy(self) -> None:
        runtime, db = self.make_runtime()
        original_timeout = SETTINGS.deploy_health_timeout_seconds
        object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", 1)
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", original_timeout))
        db.upsert_team_names(["Team Alpha"])

        def compose(series: int, command: str):
            if "up -d" in command:
                return {"192.168.0.102": (False, "boom")}
            if "down -v" in command:
                return {"192.168.0.102": (True, "rolled back")}
            return {}

        runtime._run_compose_parallel = Mock(side_effect=compose)
        runtime.poller.run_cycle = Mock(return_value=([], {}))

        with patch("scheduler.fire_and_forget", lambda payload: None), patch(
            "scheduler.time.sleep",
            return_value=None,
        ), patch("scheduler.time.monotonic", side_effect=[0, 0, 2, 2]):
            with self.assertRaises(RuntimeGuardError):
                runtime.start_competition()

        state = db.get_competition()
        self.assertEqual(state["status"], "stopped")
        self.assertTrue(
            any(
                event["detail"] == "Competition startup failed; referee left in stopped state"
                for event in db.list_events(limit=20)
            )
        )

    def test_rotate_to_series_pauses_on_failed_health_gate(self) -> None:
        runtime, db = self.make_runtime()
        original_timeout = SETTINGS.deploy_health_timeout_seconds
        object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", 1)
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", original_timeout))
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)
        runtime.poll_once = Mock()
        runtime._run_compose_parallel = Mock(
            side_effect=[
                {},
                {
                    "192.168.0.102": (False, "boom"),
                    "192.168.0.103": (False, "boom"),
                    "192.168.0.106": (False, "boom"),
                },
                {},
                {
                    "192.168.0.102": (False, "still-broken"),
                    "192.168.0.103": (False, "still-broken"),
                    "192.168.0.106": (False, "still-broken"),
                },
                {},
            ]
        )
        runtime.poller.run_cycle = Mock(side_effect=itertools.repeat(([], {})))

        with patch("scheduler.fire_and_forget", lambda payload: None), patch(
            "scheduler.time.sleep",
            return_value=None,
        ), patch("scheduler.time.monotonic", side_effect=[0, 2, 0, 2]):
            with self.assertRaises(RuntimeGuardError):
                runtime.rotate_to_series(2)

        state = db.get_competition()
        self.assertEqual(state["status"], "faulted")
        self.assertEqual(state["current_series"], 1)
        self.assertIn("rollback to H1 also failed", state["fault_reason"])

    def test_rotate_to_series_rolls_back_previous_series_after_failed_target_deploy(self) -> None:
        runtime, db = self.make_runtime()
        original_timeout = SETTINGS.deploy_health_timeout_seconds
        object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", 1)
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", original_timeout))
        db.upsert_team_names(["Team Alpha"])
        db.increment_team_offense("Team Alpha")
        db.increment_team_offense("Team Alpha")
        db.set_competition_state(status="running", current_series=1)
        runtime.poll_once = Mock()
        runtime._run_compose_parallel = Mock(
            side_effect=[
                {},
                {
                    "192.168.0.102": (False, "boom"),
                    "192.168.0.103": (False, "boom"),
                    "192.168.0.106": (False, "boom"),
                },
                {},
                {},
            ]
        )
        healthy_snapshots = [
            _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
        ]
        runtime.poller.run_cycle = Mock(side_effect=[([], {}), (healthy_snapshots, {}), (healthy_snapshots, {})])

        with patch("scheduler.fire_and_forget", lambda payload: None), patch(
            "scheduler.time.sleep",
            return_value=None,
        ), patch("scheduler.time.monotonic", side_effect=[0, 2, 0]):
            runtime.rotate_to_series(2)

        state = db.get_competition()
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["current_series"], 1)
        self.assertTrue(state["next_rotation"])
        self.assertEqual(db.get_team("Team Alpha")["status"], "series_banned")
        self.assertTrue(
            any(
                event["detail"] == "Rotation to H2 failed; automatically rolled back to H1"
                for event in db.list_events(limit=20)
            )
        )

    def test_degraded_node_does_not_block_rotation_when_quorum_holds(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)
        runtime.poll_once = Mock()
        runtime._run_compose_parallel = Mock(side_effect=[{}, {}, {}])
        runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed", node_epoch=1000),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed", node_epoch=1000),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed", node_epoch=1000),
                    _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed", node_epoch=1001),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed", node_epoch=1001),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed", node_epoch=1001),
                    _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed", node_epoch=1010),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed", node_epoch=1010),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed", node_epoch=1010),
                ],
                {},
            )
        )

        runtime.rotate_to_series(2)

        state = db.get_competition()
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["current_series"], 2)

    def test_deploy_series_or_raise_retries_until_health_recovers(self) -> None:
        runtime, db = self.make_runtime()
        original_timeout = SETTINGS.deploy_health_timeout_seconds
        object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", 1)
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", original_timeout))
        runtime._run_compose_parallel = Mock(return_value={})
        bad_snapshots = [
            _snapshot(node_host="192.168.0.102", variant="A", king=None, king_mtime_epoch=None, status="failed"),
            _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="A", king=None, king_mtime_epoch=None, status="failed"),
            _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
        ]
        good_snapshots = [
            _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
        ]
        runtime.poller.run_cycle = Mock(side_effect=[(bad_snapshots, {}), (good_snapshots, {}), (good_snapshots, {})])
        with patch("scheduler.fire_and_forget", lambda payload: None), patch(
            "scheduler.time.sleep",
            return_value=None,
        ), patch("scheduler.time.monotonic", side_effect=[0, 0]):
            result = runtime._deploy_series_or_raise(series=2)
        self.assertEqual(len(result), 9)
        self.assertEqual(runtime.poller.run_cycle.call_count, 3)

    def test_baseline_violation_detects_missing_to_present_authkeys(self) -> None:
        runtime, db = self.make_runtime()
        runtime._capture_baselines(
            1,
            [
                VariantSnapshot(
                    node_host="192.168.0.102",
                    variant="A",
                    king="unclaimed",
                    king_mtime_epoch=1,
                    status="running",
                    sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": "ok"},
                    checked_at=datetime.now(UTC),
                )
            ],
        )

        violations: dict[tuple[str, str], list[object]] = {}
        runtime._merge_baseline_violations(
            series=1,
            snapshots=[
                VariantSnapshot(
                    node_host="192.168.0.102",
                    variant="A",
                    king="Team Alpha",
                    king_mtime_epoch=2,
                    status="running",
                    sections={
                        "AUTHKEYS": f"{'a' * 64}  /root/.ssh/authorized_keys",
                        "SHADOW": "",
                        "IPTABLES": "ok",
                        "PORTS": "ok",
                    },
                    checked_at=datetime.now(UTC),
                )
            ],
            violations=violations,
        )

        hits = violations[("192.168.0.102", "A")]
        self.assertEqual(hits[0].offense_name, "authkeys_changed")

    def test_h1b_authkeys_change_is_exempt_from_baseline_violation(self) -> None:
        runtime, db = self.make_runtime()
        runtime._capture_baselines(
            1,
            [
                VariantSnapshot(
                    node_host="192.168.0.102",
                    variant="B",
                    king="unclaimed",
                    king_mtime_epoch=1,
                    status="running",
                    sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": "ok"},
                    checked_at=datetime.now(UTC),
                )
            ],
        )

        violations: dict[tuple[str, str], list[object]] = {}
        runtime._merge_baseline_violations(
            series=1,
            snapshots=[
                VariantSnapshot(
                    node_host="192.168.0.102",
                    variant="B",
                    king="Team Alpha",
                    king_mtime_epoch=2,
                    status="running",
                    sections={
                        "AUTHKEYS": f"{'a' * 64}  /root/.ssh/authorized_keys",
                        "SHADOW": "",
                        "IPTABLES": "ok",
                        "PORTS": "ok",
                    },
                    checked_at=datetime.now(UTC),
                )
            ],
            violations=violations,
        )

        self.assertEqual(violations.get(("192.168.0.102", "B")), [])

    def test_h7b_shadow_change_is_exempt_from_baseline_violation(self) -> None:
        runtime, db = self.make_runtime()
        runtime._capture_baselines(
            7,
            [
                VariantSnapshot(
                    node_host="192.168.0.102",
                    variant="B",
                    king="unclaimed",
                    king_mtime_epoch=1,
                    status="running",
                    sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": "ok"},
                    checked_at=datetime.now(UTC),
                )
            ],
        )

        violations: dict[tuple[str, str], list[object]] = {}
        runtime._merge_baseline_violations(
            series=7,
            snapshots=[
                VariantSnapshot(
                    node_host="192.168.0.102",
                    variant="B",
                    king="Team Alpha",
                    king_mtime_epoch=2,
                    status="running",
                    sections={
                        "AUTHKEYS": "",
                        "SHADOW": f"{'b' * 64}  /etc/shadow",
                        "IPTABLES": "ok",
                        "PORTS": "ok",
                    },
                    checked_at=datetime.now(UTC),
                )
            ],
            violations=violations,
        )

        self.assertEqual(violations.get(("192.168.0.102", "B")), [])

    def test_baseline_snapshots_without_hits_do_not_escalate_team(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)

        snapshots = [
            VariantSnapshot(
                node_host=node_host,
                variant=variant,
                king="Team Alpha" if variant == "A" and node_host != "192.168.0.106" else "unclaimed",
                king_mtime_epoch=1000,
                status="running",
                sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": "ok", "NODE_EPOCH": "1000"},
                checked_at=datetime.now(UTC),
            )
            for node_host in SETTINGS.node_hosts
            for variant in SETTINGS.variants
        ]
        runtime._capture_baselines(1, snapshots)
        runtime.poller.run_cycle = Mock(return_value=(snapshots, {}))

        runtime.poll_once()

        team = db.get_team("Team Alpha")
        self.assertEqual(team["offense_count"], 0)
        self.assertEqual(team["status"], "active")

    def test_repeated_violation_only_escalates_once_until_cleared(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=2)
        baseline_ports = "\n".join(
            [
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process",
                "LISTEN 0 128 *:8080 *:* users:((\"java\",pid=1,fd=123))",
            ]
        )
        violating_ports = "\n".join(
            [
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process",
                "LISTEN 0 128 *:8080 *:* users:((\"java\",pid=1,fd=123))",
                "LISTEN 0 128 *:9005 *:* users:((\"java\",pid=1,fd=124))",
            ]
        )

        baseline = [
            VariantSnapshot(
                node_host=node_host,
                variant=variant,
                king="unclaimed",
                king_mtime_epoch=1000,
                status="running",
                sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": baseline_ports, "ROOT_DIR": "700", "KING_STAT": "1000 644 root:root regular file", "KING": "unclaimed", "NODE_EPOCH": "1000"},
                checked_at=datetime.now(UTC),
            )
            for node_host in SETTINGS.node_hosts
            for variant in SETTINGS.variants
        ]
        runtime._capture_baselines(2, baseline)

        violating = [
            VariantSnapshot(
                node_host=node_host,
                variant=variant,
                king="Team Alpha" if variant == "C" and node_host == "192.168.0.103" else "unclaimed",
                king_mtime_epoch=1000,
                status="running",
                sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": violating_ports if variant == "C" and node_host == "192.168.0.103" else baseline_ports, "ROOT_DIR": "700", "KING_STAT": "1000 644 root:root regular file", "KING": "Team Alpha" if variant == "C" and node_host == "192.168.0.103" else "unclaimed", "NODE_EPOCH": "1000"},
                checked_at=datetime.now(UTC),
            )
            for node_host in SETTINGS.node_hosts
            for variant in SETTINGS.variants
        ]
        clean = [
            VariantSnapshot(
                node_host=node_host,
                variant=variant,
                king="unclaimed",
                king_mtime_epoch=1000,
                status="running",
                sections={"AUTHKEYS": "", "SHADOW": "", "IPTABLES": "ok", "PORTS": baseline_ports, "ROOT_DIR": "700", "KING_STAT": "1000 644 root:root regular file", "KING": "unclaimed", "NODE_EPOCH": "1000"},
                checked_at=datetime.now(UTC),
            )
            for node_host in SETTINGS.node_hosts
            for variant in SETTINGS.variants
        ]

        runtime.poller.run_cycle = Mock(side_effect=[(violating, {}), (violating, {}), (clean, {}), (violating, {})])

        runtime.poll_once()
        self.assertEqual(db.get_team("Team Alpha")["offense_count"], 1)
        self.assertEqual(len(db.list_violations()), 1)

        runtime.poll_once()
        self.assertEqual(db.get_team("Team Alpha")["offense_count"], 1)
        self.assertEqual(len(db.list_violations()), 1)

        runtime.poll_once()
        self.assertEqual(db.get_team("Team Alpha")["offense_count"], 1)

        runtime.poll_once()
        self.assertEqual(db.get_team("Team Alpha")["offense_count"], 2)
        self.assertEqual(len(db.list_violations()), 2)
    def test_deleted_king_violation_falls_back_to_current_owner(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=2)
        db.set_variant_owner(
            series=2,
            variant="C",
            owner_team="Team Alpha",
            accepted_mtime_epoch=1000,
            source_node_host="192.168.0.103",
            evidence={},
        )
        snapshots = [
            _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed", king_mtime_epoch=1),
            _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed", king_mtime_epoch=1),
            _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed", king_mtime_epoch=1),
            _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed", king_mtime_epoch=1),
            _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed", king_mtime_epoch=1),
            _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed", king_mtime_epoch=1),
            VariantSnapshot(
                node_host="192.168.0.102",
                variant="C",
                king=None,
                king_mtime_epoch=None,
                status="failed",
                sections={"KING": "FILE_MISSING", "KING_STAT": "STAT_FAIL", "ROOT_DIR": "700", "NODE_EPOCH": "1000"},
                checked_at=datetime.now(UTC),
            ),
            _snapshot(node_host="192.168.0.103", variant="C", king="Team Alpha", king_mtime_epoch=1000),
            _snapshot(node_host="192.168.0.106", variant="C", king="Team Alpha", king_mtime_epoch=1010),
        ]
        runtime.poller.run_cycle = Mock(
            return_value=(
                snapshots,
                {("192.168.0.102", "C"): [ViolationHit(4, "king_deleted", {"king": "FILE_MISSING"})]},
            )
        )

        runtime.poll_once()

        team = db.get_team("Team Alpha")
        self.assertEqual(team["offense_count"], 1)
        violations = db.list_violations()
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["offense_name"], "king_deleted")
    def test_pause_blocks_scoring(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="paused", current_series=1)
        runtime.poller.run_cycle = Mock(
            return_value=(
                [_snapshot(node_host="192.168.0.102", king="Team Alpha", king_mtime_epoch=1)],
                {},
            )
        )

        runtime.poll_once()

        self.assertEqual(db.get_team("Team Alpha")["total_points"], 0)
        self.assertEqual(db.get_competition()["poll_cycle"], 0)

    def test_quorum_loss_blocks_scoring(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)
        runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="Team Alpha", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="A", king=None, king_mtime_epoch=None, status="unreachable"),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="A", king=None, king_mtime_epoch=None, status="unreachable"),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed", king_mtime_epoch=1),
                ],
                {},
            )
        )

        runtime.poll_once()

        self.assertEqual(db.get_team("Team Alpha")["total_points"], 0)
        self.assertTrue(
            any(
                "insufficient healthy replicas" in event["detail"]
                for event in db.list_events(limit=20)
            )
        )

    def test_single_node_earliest_claim_does_not_override_authoritative_owner(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha", "Team Beta"])
        db.set_competition_state(status="running", current_series=1)
        db.set_variant_owner(
            series=1,
            variant="A",
            owner_team="Team Alpha",
            accepted_mtime_epoch=1000,
            source_node_host="192.168.0.102",
            evidence={"source": "test"},
        )
        runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="Team Alpha", king_mtime_epoch=1000),
                    _snapshot(node_host="192.168.0.103", variant="A", king="Team Alpha", king_mtime_epoch=1010),
                    _snapshot(node_host="192.168.0.106", variant="A", king="Team Beta", king_mtime_epoch=900),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed", king_mtime_epoch=1),
                ],
                {},
            )
        )

        runtime.poll_once()

        self.assertEqual(db.get_team("Team Alpha")["total_points"], 1.0)
        self.assertEqual(db.get_team("Team Beta")["total_points"], 0.0)
        owner = db.get_variant_owner(series=1, variant="A")
        self.assertEqual(owner["owner_team"], "Team Alpha")

    def test_authoritative_owner_is_reconciled_to_divergent_healthy_replica(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha", "Team Beta"])
        db.set_competition_state(status="running", current_series=1)
        db.set_variant_owner(
            series=1,
            variant="A",
            owner_team="Team Alpha",
            accepted_mtime_epoch=1000,
            source_node_host="192.168.0.102",
            evidence={"source": "test"},
        )
        runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="Team Alpha", king_mtime_epoch=1000),
                    _snapshot(node_host="192.168.0.103", variant="A", king="Team Alpha", king_mtime_epoch=1010),
                    _snapshot(node_host="192.168.0.106", variant="A", king="Team Beta", king_mtime_epoch=900),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed", king_mtime_epoch=1),
                ],
                {},
            )
        )

        runtime.poll_once()

        ssh = runtime.ssh_pool
        self.assertEqual(len(ssh.commands), 1)
        host, command = ssh.commands[0]
        self.assertEqual(host, "192.168.0.106")
        self.assertIn("Team Alpha", command)
        self.assertTrue(
            any(
                event["detail"] == "Reconciled A replica to authoritative owner"
                for event in db.list_events(limit=20)
            )
        )

    def test_resume_requires_validated_current_series(self) -> None:
        runtime, db = self.make_runtime()
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="paused", current_series=1)
        runtime.poller.run_cycle = Mock(return_value=([], {}))

        with self.assertRaises(RuntimeGuardError):
            runtime.resume_rotation()

        state = db.get_competition()
        self.assertEqual(state["status"], "faulted")
        self.assertIn("failed resume validation", state["fault_reason"])

    def test_start_scheduler_restores_rotation_job_from_db(self) -> None:
        runtime, db = self.make_runtime()
        future_rotation = datetime.now(UTC) + timedelta(minutes=5)
        db.set_competition_state(status="running", current_series=1, next_rotation=future_rotation.isoformat())
        runtime.scheduler = DummyScheduler()

        runtime.start_scheduler()

        self.assertIn("poll", runtime.scheduler.jobs)
        self.assertIn("rotate", runtime.scheduler.jobs)
        self.assertEqual(runtime.scheduler.jobs["rotate"]["trigger"], "date")
        self.assertEqual(runtime.scheduler.jobs["rotate"]["run_date"], future_rotation)

    def test_runtime_endpoint_model_fields_persist_validation_state(self) -> None:
        runtime, db = self.make_runtime()
        validated_at = datetime.now(UTC).isoformat()
        db.set_competition_state(
            status="faulted",
            current_series=2,
            previous_series=1,
            fault_reason="rotation failed",
            last_validated_series=1,
            last_validated_at=validated_at,
        )

        state = db.get_competition()
        self.assertEqual(state["status"], "faulted")
        self.assertEqual(state["previous_series"], 1)
        self.assertEqual(state["fault_reason"], "rotation failed")
        self.assertEqual(state["last_validated_series"], 1)
        self.assertEqual(state["last_validated_at"], validated_at)

    def test_validate_current_series_returns_summary(self) -> None:
        runtime, db = self.make_runtime()
        db.set_competition_state(status="paused", current_series=1)
        runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
                ],
                {},
            )
        )

        summary = runtime.validate_current_series()

        self.assertTrue(summary["valid"])
        self.assertTrue(summary["complete_snapshot_matrix"])
        self.assertEqual(summary["healthy_nodes"], 3)
        self.assertEqual(summary["total_nodes"], 3)
        self.assertEqual(summary["min_healthy_nodes"], 2)
        self.assertEqual(summary["healthy_counts_by_variant"]["A"], 3)
        state = db.get_competition()
        self.assertEqual(state["last_validated_series"], 1)
        self.assertIsNotNone(state["last_validated_at"])

    def test_recover_current_series_redeploys_faulted_series_and_leaves_paused(self) -> None:
        runtime, db = self.make_runtime()
        db.set_competition_state(status="faulted", current_series=2, fault_reason="broken")
        runtime._run_compose_parallel = Mock(return_value={})
        healthy_snapshots = [
            _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
        ]
        runtime.poller.run_cycle = Mock(return_value=(healthy_snapshots, {}))

        result = runtime.recover_current_series()

        self.assertTrue(result["ok"])
        self.assertEqual(result["competition_status"], "paused")
        state = db.get_competition()
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["current_series"], 2)
        self.assertIsNone(state["fault_reason"])
        self.assertEqual(state["last_validated_series"], 2)

    def test_recover_current_series_failure_remains_faulted(self) -> None:
        runtime, db = self.make_runtime()
        original_timeout = SETTINGS.deploy_health_timeout_seconds
        object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", 1)
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "deploy_health_timeout_seconds", original_timeout))
        db.set_competition_state(status="faulted", current_series=2, fault_reason="broken")

        def compose(series: int, command: str):
            if "up -d" in command:
                return {"192.168.0.102": (False, "boom")}
            return {}

        runtime._run_compose_parallel = Mock(side_effect=compose)
        runtime.poller.run_cycle = Mock(return_value=([], {}))

        with patch("scheduler.fire_and_forget", lambda payload: None), patch(
            "scheduler.time.sleep",
            return_value=None,
        ), patch("scheduler.time.monotonic", side_effect=[0, 0, 2, 2]):
            with self.assertRaises(RuntimeGuardError):
                runtime.recover_current_series()

        state = db.get_competition()
        self.assertEqual(state["status"], "faulted")
        self.assertIn("Recovery redeploy for H2 failed", state["fault_reason"])


class PollerCompletenessTests(unittest.TestCase):
    def setUp(self) -> None:
        _override_runtime_settings(self)

    def test_partial_output_synthesizes_missing_variants_as_failed(self) -> None:
        class PartialSSH:
            def exec(self, host: str, command: str):
                _ = command
                return (
                    1,
                    "\n".join(
                        [
                            "===VARIANT:A===",
                            "===KING===",
                            "Team Alpha",
                            "===KING_STAT===",
                            "1000 644 root:root regular file",
                            "===END_VARIANT===",
                        ]
                    ),
                    "simulated failure",
                )

        poller = Poller(PartialSSH())

        snapshots, violations = poller.run_cycle(series=1)

        self.assertEqual(len(snapshots), len(SETTINGS.node_hosts) * len(SETTINGS.variants))
        self.assertEqual({snap.variant for snap in snapshots}, {"A", "B", "C"})
        self.assertEqual({snap.node_host for snap in snapshots}, set(SETTINGS.node_hosts))
        self.assertEqual(
            {snap.variant for snap in snapshots if snap.status == "failed"},
            {"B", "C"},
        )
        self.assertEqual(violations, {})

    def test_watchdog_detection_does_not_flag_one_shot_king_write_command(self) -> None:
        poller = Poller(DummySSH())
        snap = VariantSnapshot(
            node_host="192.168.0.102",
            variant="C",
            king="Team Alpha",
            king_mtime_epoch=1000,
            status="running",
            sections={
                "KING_STAT": "1000 644 root:root regular file",
                "KING": "Team Alpha",
                "ROOT_DIR": "700",
                "IMMUTABLE": "",
                "CRON": "",
                "PROCS": "root  42  0.0  bash -p -c 'echo Team Alpha > /root/king.txt'",
            },
            checked_at=datetime.now(UTC),
        )

        hits = poller._detect_violations(snap)

        self.assertFalse(any(hit.offense_name == "watchdog_process" for hit in hits))

    def test_probe_command_uses_root_exec_and_separates_king_section(self) -> None:
        poller = Poller(DummySSH())

        command = poller._build_probe_command(series=2)

        self.assertIn('docker exec -u 0 "$container_id" sh -lc', command)
        self.assertIn('printf "\\n";', command)

    def test_normalize_king_strips_inline_section_marker(self) -> None:
        self.assertEqual(Poller._normalize_king("unclaimed===KING_STAT==="), "unclaimed")

    def test_stable_ports_signature_ignores_docker_dns_stub_port(self) -> None:
        poller = Poller(DummySSH())
        first = """State  Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0 4096 127.0.0.11:38271 0.0.0.0:*
LISTEN 0 1 [::ffff:127.0.0.1]:8005 *:*
LISTEN 0 100 *:8080 *:*
"""
        second = """State  Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0 4096 127.0.0.11:46209 0.0.0.0:*
LISTEN 0 100 *:8080 *:*
LISTEN 0 1 [::ffff:127.0.0.1]:8005 *:*
"""
        changed = """State  Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0 4096 127.0.0.11:46209 0.0.0.0:*
LISTEN 0 100 *:8081 *:*
LISTEN 0 1 [::ffff:127.0.0.1]:8005 *:*
"""
        self.assertEqual(
            poller.stable_ports_signature(first),
            poller.stable_ports_signature(second),
        )
        self.assertNotEqual(
            poller.stable_ports_signature(first),
            poller.stable_ports_signature(changed),
        )

class ConfigLoadingTests(unittest.TestCase):
    def test_dotenv_is_loaded_from_module_directory(self) -> None:
        config_path = Path(__file__).resolve().parent.parent / "config.py"
        env_path = config_path.with_name(".env")
        original = env_path.read_text(encoding="utf-8") if env_path.exists() else None
        env_path.write_text("ADMIN_API_KEY=from-dotenv\n", encoding="utf-8")
        self.addCleanup(
            lambda: env_path.write_text(original, encoding="utf-8")
            if original is not None
            else env_path.exists() and env_path.unlink()
        )

        with patch.dict(os.environ, {}, clear=True):
            sys.modules.pop("config", None)
            config = importlib.import_module("config")
            importlib.reload(config)
            self.assertEqual(config.SETTINGS.admin_api_key, "from-dotenv")
            self.assertFalse(config.SETTINGS.allow_unsafe_no_admin_api_key)


class ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        _override_runtime_settings(self)
        original_admin_key = SETTINGS.admin_api_key
        object.__setattr__(SETTINGS, "admin_api_key", "test-admin-key")
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "admin_api_key", original_admin_key))

        fd, raw_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_path = Path(raw_path)
        self.addCleanup(lambda: db_path.exists() and db_path.unlink())

        db = Database(db_path)
        db.initialize()
        self.addCleanup(db.close)
        runtime = RefereeRuntime(db, DummySSH())
        runtime.scheduler = DummyScheduler()
        runtime.start_scheduler = Mock()
        runtime.shutdown = Mock()

        sys.modules.pop("app", None)
        with patch("fastapi.templating.Jinja2Templates", DummyTemplates):
            app_module = importlib.import_module("app")
        self.app_module = app_module
        self.original_db = app_module.db
        self.original_runtime = app_module.runtime
        self.original_ssh_pool = app_module.ssh_pool
        app_module.db = db
        app_module.runtime = runtime
        app_module.ssh_pool = runtime.ssh_pool
        self.addCleanup(self._restore_app_globals)

        self.client = TestClient(app_module.app)
        self.addCleanup(self.client.close)
        self.participant_client = TestClient(app_module.participant_app)
        self.addCleanup(self.participant_client.close)

    def _restore_app_globals(self) -> None:
        self.app_module.db = self.original_db
        self.app_module.runtime = self.original_runtime
        self.app_module.ssh_pool = self.original_ssh_pool

    def test_runtime_endpoint_returns_extended_state(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        validated_at = datetime.now(UTC).isoformat()
        self.app_module.db.set_competition_state(
            status="faulted",
            current_series=3,
            previous_series=2,
            fault_reason="rotation failed",
            last_validated_series=2,
            last_validated_at=validated_at,
        )
        self.app_module.runtime.scheduler.add_job(
            lambda: None,
            "interval",
            id="poll",
            replace_existing=True,
            max_instances=1,
            seconds=30,
        )
        self.app_module.runtime.scheduler.add_job(
            lambda: None,
            "date",
            id="rotate",
            replace_existing=True,
            max_instances=1,
            run_date=datetime.now(UTC) + timedelta(minutes=1),
        )

        response = self.client.get("/api/runtime")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["competition_status"], "faulted")
        self.assertEqual(payload["current_series"], 3)
        self.assertEqual(payload["previous_series"], 2)
        self.assertEqual(payload["fault_reason"], "rotation failed")
        self.assertEqual(payload["last_validated_series"], 2)
        self.assertIn("poll", payload["active_jobs"])
        self.assertIn("rotate", payload["active_jobs"])

    def test_status_endpoint_filters_stale_container_hosts(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        valid_host = self.app_module.SETTINGS.node_hosts[0]
        self.app_module.db.upsert_container_status(
            machine_host="10.0.0.9",
            variant="A",
            container_id="stale",
            series=5,
            status="running",
            king="unclaimed",
            king_mtime_epoch=1,
            last_checked=datetime.now(UTC).isoformat(),
        )
        self.app_module.db.upsert_container_status(
            machine_host=valid_host,
            variant="A",
            container_id="fresh",
            series=5,
            status="running",
            king="unclaimed",
            king_mtime_epoch=1,
            last_checked=datetime.now(UTC).isoformat(),
        )
        self.app_module.db.set_competition_state(status="running", current_series=5)

        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        hosts = {item["machine_host"] for item in response.json()["containers"]}
        self.assertNotIn("10.0.0.9", hosts)
        self.assertEqual(hosts, {valid_host})

    def test_runtime_endpoint_requires_admin_key(self) -> None:
        response = self.client.get("/api/runtime")
        self.assertEqual(response.status_code, 401)

    def test_status_endpoint_requires_admin_key(self) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 401)

    def test_poll_endpoint_requires_admin_key_and_cannot_award_points(self) -> None:
        self.app_module.db.upsert_team_names(["Team Alpha"])
        self.app_module.db.set_competition_state(status="running", current_series=1)
        self.app_module.runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="Team Alpha", king_mtime_epoch=1000),
                    _snapshot(node_host="192.168.0.103", variant="A", king="Team Alpha", king_mtime_epoch=1010),
                    _snapshot(node_host="192.168.0.106", variant="A", king="Team Alpha", king_mtime_epoch=1020),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed", king_mtime_epoch=1),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed", king_mtime_epoch=1),
                ],
                {},
            )
        )
        self.app_module.runtime.poll_once = Mock(wraps=self.app_module.runtime.poll_once)

        response = self.client.post("/api/poll")

        self.assertEqual(response.status_code, 401)
        self.app_module.runtime.poll_once.assert_not_called()
        self.assertEqual(self.app_module.db.get_team("Team Alpha")["total_points"], 0.0)
        self.assertEqual(self.app_module.db.get_competition()["poll_cycle"], 0)
        with self.app_module.db._lock:  # noqa: SLF001 - test verifies DB side effects
            point_count = self.app_module.db._conn.execute("SELECT COUNT(*) FROM point_events").fetchone()[0]
        self.assertEqual(point_count, 0)

    def test_dashboard_route_renders_template(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_participant_dashboard_route_renders_template(self) -> None:
        response = self.participant_client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_lb_endpoint_parses_frontend_backend_haproxy_config(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        cfg = """
frontend h1a
  bind *:10001
  default_backend h1a_nodes
backend h1a_nodes
  balance roundrobin
  server n1 192.168.0.70:10001 check
  server n2 192.168.0.103:10001 check
  server n3 192.168.0.106:10001 check
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            haproxy_cfg = Path(tmpdir) / "haproxy.cfg"
            haproxy_cfg.write_text(cfg, encoding="utf-8")
            previous_path = self.app_module.HAPROXY_CONFIG_PATH
            self.app_module.HAPROXY_CONFIG_PATH = haproxy_cfg
            try:
                response = self.client.get("/api/lb")
            finally:
                self.app_module.HAPROXY_CONFIG_PATH = previous_path

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["configured"])
        self.assertEqual(len(payload["services"]), 1)
        self.assertEqual(payload["services"][0]["name"], "h1a")
        self.assertEqual(payload["services"][0]["bind_port"], 10001)
        self.assertEqual(len(payload["services"][0]["servers"]), 3)

    def test_lb_endpoint_requires_admin_key(self) -> None:
        response = self.client.get("/api/lb")
        self.assertEqual(response.status_code, 401)

    def test_routing_and_telemetry_endpoints_require_admin_key(self) -> None:
        self.assertEqual(self.client.get("/api/routing").status_code, 401)
        self.assertEqual(self.client.get("/api/telemetry").status_code, 401)

    def test_routing_endpoint_returns_active_listener_view(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        payload = self.app_module.RoutingStatusResponse(
            configured=True,
            current_series=6,
            services=[
                self.app_module.RoutingServiceResponse(
                    name="p10050",
                    bind_port=10050,
                    variant="A",
                    inbound_connections=12,
                    backend_connections=9,
                    routing_text="n1 192.168.0.70:10050 [UP] -> n2 192.168.0.103:10050 [UP]",
                    servers=[
                        self.app_module.RoutingServerResponse(
                            name="n1",
                            host="192.168.0.70",
                            port=10050,
                            status="UP",
                            check_status="L4OK",
                            active_connections=5,
                            last_change_seconds=12,
                        ),
                        self.app_module.RoutingServerResponse(
                            name="n2",
                            host="192.168.0.103",
                            port=10050,
                            status="UP",
                            check_status="L4OK",
                            active_connections=4,
                            last_change_seconds=12,
                        ),
                    ],
                )
            ],
            total_inbound_connections=12,
            total_backend_connections=9,
            note=None,
        )

        with patch.object(self.app_module, "_routing_status", return_value=payload):
            response = self.client.get("/api/routing")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["current_series"], 6)
        self.assertEqual(body["services"][0]["variant"], "A")
        self.assertEqual(body["services"][0]["servers"][0]["status"], "UP")

    def test_telemetry_endpoint_returns_host_and_container_data(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        payload = self.app_module.TelemetryStatusResponse(
            current_series=2,
            generated_at=datetime.now(UTC),
            hosts=[
                self.app_module.HostTelemetryResponse(
                    host="192.168.0.12",
                    role="lb",
                    reachable=True,
                    loadavg_1m=0.15,
                    loadavg_5m=0.20,
                    loadavg_15m=0.25,
                    mem_used_mb=1024,
                    mem_total_mb=4096,
                    mem_percent=25.0,
                    disk_used_gb=40.0,
                    disk_total_gb=128.0,
                    disk_percent=31.3,
                    uptime_seconds=3600,
                    docker_status="active",
                    haproxy_status="active",
                    referee_status="active",
                    error=None,
                )
            ],
            containers=[
                self.app_module.ContainerTelemetryResponse(
                    machine_host="192.168.0.70",
                    variant="A",
                    container_id="H2A_Node1",
                    series=2,
                    status="running",
                    health="healthy",
                    king="Team Alpha",
                    cpu_percent=1.2,
                    memory_usage="12MiB / 4GiB",
                    memory_percent=0.3,
                    pids=7,
                    restart_count=1,
                    started_at="2026-04-18T12:00:00Z",
                    finished_at=None,
                    exit_code=0,
                    oom_killed=False,
                    uptime_seconds=120,
                    downtime_seconds=8,
                    error=None,
                )
            ],
            note=None,
        )

        with patch.object(self.app_module, "_telemetry_status", return_value=payload):
            response = self.client.get("/api/telemetry")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["current_series"], 2)
        self.assertEqual(body["hosts"][0]["haproxy_status"], "active")
        self.assertEqual(body["containers"][0]["container_id"], "H2A_Node1")

    def test_logs_and_claims_endpoints_require_admin_key(self) -> None:
        self.assertEqual(self.client.get("/api/logs/referee").status_code, 401)
        self.assertEqual(self.client.get("/api/logs/haproxy").status_code, 401)
        self.assertEqual(self.client.get("/api/claims").status_code, 401)

    def test_teams_and_events_endpoints_require_admin_key(self) -> None:
        self.assertEqual(self.client.get("/api/teams").status_code, 401)
        self.assertEqual(self.client.get("/api/events").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/teams", json={"name": "Team Alpha"}).status_code, 401)

    def test_recover_validate_endpoint_requires_admin_key(self) -> None:
        response = self.client.post("/api/recover/validate")
        self.assertEqual(response.status_code, 401)

    def test_recover_validate_endpoint_returns_summary(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        self.app_module.db.set_competition_state(status="paused", current_series=1)
        self.app_module.runtime.poller.run_cycle = Mock(
            return_value=(
                [
                    _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
                    _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
                ],
                {},
            )
        )

        response = self.client.post(
            "/api/recover/validate",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["valid"])
        self.assertTrue(payload["complete_snapshot_matrix"])
        self.assertEqual(payload["healthy_nodes"], 3)
        self.assertEqual(payload["total_nodes"], 3)
        self.assertEqual(payload["min_healthy_nodes"], 2)
        self.assertEqual(payload["healthy_counts_by_variant"]["A"], 3)

    def test_claims_endpoint_returns_observations(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        self.app_module.db.add_claim_observations(
            [
                {
                    "poll_cycle": 7,
                    "series": 5,
                    "node_host": "192.168.0.70",
                    "variant": "A",
                    "status": "running",
                    "king": "Team Alpha",
                    "king_mtime_epoch": 1234,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "selected": True,
                    "selection_reason": "earliest_quorum",
                }
            ]
        )

        response = self.client.get("/api/claims?limit=10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertTrue(payload[0]["selected"])
        self.assertEqual(payload[0]["selection_reason"], "earliest_quorum")

    def test_log_endpoints_return_tail(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        with tempfile.TemporaryDirectory() as tmpdir:
            referee_log = Path(tmpdir) / "referee.log"
            haproxy_log = Path(tmpdir) / "haproxy.log"
            referee_log.write_text("a\nb\nc\n", encoding="utf-8")
            haproxy_log.write_text("x\ny\n", encoding="utf-8")
            original_referee = self.app_module.SETTINGS.referee_log_path
            original_haproxy = self.app_module.SETTINGS.haproxy_log_path
            object.__setattr__(self.app_module.SETTINGS, "referee_log_path", referee_log)
            object.__setattr__(self.app_module.SETTINGS, "haproxy_log_path", haproxy_log)
            try:
                referee_response = self.client.get("/api/logs/referee?lines=2")
                haproxy_response = self.client.get("/api/logs/haproxy?lines=1")
            finally:
                object.__setattr__(self.app_module.SETTINGS, "referee_log_path", original_referee)
                object.__setattr__(self.app_module.SETTINGS, "haproxy_log_path", original_haproxy)

        self.assertEqual(referee_response.status_code, 200)
        self.assertEqual(referee_response.json()["lines"], ["b", "c"])
        self.assertEqual(haproxy_response.status_code, 200)
        self.assertEqual(haproxy_response.json()["lines"], ["y"])

    def test_team_admin_endpoint_rejects_invalid_claim_names(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)

        response = self.client.post("/api/admin/teams", json={"name": "unclaimed"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("valid claim", response.json()["detail"])

    def test_team_admin_endpoints_create_ban_and_unban(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)

        create_response = self.client.post("/api/admin/teams", json={"name": "Team Alpha"})
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["status"], "active")

        ban_response = self.client.post("/api/admin/teams/Team%20Alpha/ban")
        self.assertEqual(ban_response.status_code, 200)
        self.assertEqual(ban_response.json()["status"], "banned")

        self.app_module.db.increment_team_offense("Team Alpha")
        unban_response = self.client.post("/api/admin/teams/Team%20Alpha/unban")
        self.assertEqual(unban_response.status_code, 200)
        self.assertEqual(unban_response.json()["status"], "active")
        self.assertEqual(unban_response.json()["offense_count"], 0)

    def test_public_dashboard_endpoint_returns_derived_defaults(self) -> None:
        self.app_module.db.set_competition_state(status="running", current_series=2)
        cfg = """
listen p10010
  bind *:10010
  server n1 192.168.0.70:10010 check
listen p10011
  bind *:10011
  server n1 192.168.0.70:10011 check
listen p10012
  bind *:10012
  server n1 192.168.0.70:10012 check
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            haproxy_cfg = Path(tmpdir) / "haproxy.cfg"
            haproxy_cfg.write_text(cfg, encoding="utf-8")
            previous_path = self.app_module.HAPROXY_CONFIG_PATH
            self.app_module.HAPROXY_CONFIG_PATH = haproxy_cfg
            try:
                response = self.participant_client.get(
                    "/api/public/dashboard",
                    headers={"host": "172.21.0.13:9000"},
                )
            finally:
                self.app_module.HAPROXY_CONFIG_PATH = previous_path

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["competition_status"], "running")
        self.assertEqual(payload["current_series"], 2)
        self.assertEqual(payload["orchestrator_host"], "172.21.0.13")
        self.assertEqual(payload["port_ranges"], "10010-10012")
        self.assertEqual(payload["headline"], "Current Access Window")

    def test_admin_public_config_and_notifications_flow(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)

        config_response = self.client.put(
            "/api/admin/public/config",
            json={
                "orchestrator_host": "172.21.0.13",
                "port_ranges": "10010-10012",
                "headline": "Join Here",
                "subheadline": "Use these ports for the active wave.",
            },
        )
        self.assertEqual(config_response.status_code, 200)
        self.assertEqual(config_response.json()["orchestrator_host"], "172.21.0.13")

        create_response = self.client.post(
            "/api/admin/public/notifications",
            json={"message": "H2 is live now", "severity": "warning"},
        )
        self.assertEqual(create_response.status_code, 200)
        notification_id = create_response.json()["id"]

        list_response = self.client.get("/api/admin/public/notifications")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        public_response = self.participant_client.get("/api/public/dashboard")
        self.assertEqual(public_response.status_code, 200)
        public_payload = public_response.json()
        self.assertEqual(public_payload["orchestrator_host"], "172.21.0.13")
        self.assertEqual(public_payload["port_ranges"], "10010-10012")
        self.assertEqual(public_payload["notifications"][0]["message"], "H2 is live now")

        delete_response = self.client.delete(f"/api/admin/public/notifications/{notification_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["ok"], True)

    def test_recover_redeploy_endpoint_returns_paused_recovery_result(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        self.app_module.db.set_competition_state(status="faulted", current_series=2, fault_reason="broken")
        self.app_module.runtime._run_compose_parallel = Mock(return_value={})
        healthy_snapshots = [
            _snapshot(node_host="192.168.0.102", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.102", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.103", variant="C", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="A", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="B", king="unclaimed"),
            _snapshot(node_host="192.168.0.106", variant="C", king="unclaimed"),
        ]
        self.app_module.runtime.poller.run_cycle = Mock(return_value=(healthy_snapshots, {}))

        response = self.client.post(
            "/api/recover/redeploy",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["competition_status"], "paused")
        self.assertEqual(payload["current_series"], 2)
        self.assertIsNone(payload["fault_reason"])

    def test_recover_redeploy_endpoint_surfaces_guard_error(self) -> None:
        self.app_module.app.dependency_overrides[self.app_module.require_admin_api_key] = lambda: None
        self.addCleanup(self.app_module.app.dependency_overrides.clear)
        self.app_module.db.set_competition_state(status="running", current_series=2)

        response = self.client.post(
            "/api/recover/redeploy",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("paused or faulted", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
