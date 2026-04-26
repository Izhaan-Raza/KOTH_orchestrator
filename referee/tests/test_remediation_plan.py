"""
Remediation plan unit tests — the 10 tests specified in
docs/architecture/production-remediation-design.md §Test Plan.

These tests are isolated (in-memory/temp DB, mocked SSH and scheduler) and do
not require real nodes, Docker, or HAProxy.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if "paramiko" not in sys.modules:
    fake_paramiko = types.SimpleNamespace(
        SSHClient=object,
        RejectPolicy=object,
        AutoAddPolicy=object,
    )
    sys.modules["paramiko"] = fake_paramiko

from db import Database
from config import SETTINGS
from poller import VariantSnapshot
from scheduler import RefereeRuntime, RuntimeGuardError


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class DummySSH:
    def exec(self, host: str, command: str):
        return 0, "OK", ""

    def close(self) -> None:
        pass


class DummyScheduler:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.started = False

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.jobs.clear()

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def get_jobs(self):
        return [types.SimpleNamespace(id=jid) for jid in sorted(self.jobs)]

    def add_job(self, func, trigger, id, replace_existing, max_instances, **kwargs) -> None:
        self.jobs[id] = {"trigger": trigger, **kwargs}

    def remove_job(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)


def _override_settings(testcase: unittest.TestCase, **overrides) -> None:
    originals = {k: getattr(SETTINGS, k) for k in overrides}
    for k, v in overrides.items():
        object.__setattr__(SETTINGS, k, v)
    testcase.addCleanup(lambda: [object.__setattr__(SETTINGS, k, v) for k, v in originals.items()])


def _make_runtime(testcase: unittest.TestCase) -> tuple[RefereeRuntime, Database]:
    fd, raw_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(raw_path)
    db = Database(db_path)
    db.initialize()
    testcase.addCleanup(lambda: db_path.exists() and db_path.unlink())
    testcase.addCleanup(db.close)
    rt = RefereeRuntime(db, DummySSH())
    rt.scheduler = DummyScheduler()
    return rt, db


def _snap(
    *,
    host: str,
    variant: str = "A",
    king: str | None = "unclaimed",
    mtime: int | None = 1000,
    status: str = "running",
    epoch: int = 1000,
) -> VariantSnapshot:
    return VariantSnapshot(
        node_host=host,
        variant=variant,
        king=king,
        king_mtime_epoch=mtime,
        status=status,
        sections={"NODE_EPOCH": str(epoch)},
        checked_at=datetime.now(UTC),
    )


HOSTS = ("192.168.0.70", "192.168.0.103", "192.168.0.106")


def _full_matrix(king: str = "unclaimed", status: str = "running") -> list[VariantSnapshot]:
    return [
        _snap(host=h, variant=v, king=king, status=status)
        for h in HOSTS
        for v in ("A", "B", "C")
    ]


# ---------------------------------------------------------------------------
# Test 1 — Pause demonstrably freezes scoring
# ---------------------------------------------------------------------------
class TestPauseBlocksScoring(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_pause_blocks_scoring(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="paused", current_series=1)
        rt.poller.run_cycle = Mock(return_value=(_full_matrix("Team Alpha"), {}))

        rt.poll_once()

        self.assertEqual(db.get_team("Team Alpha")["total_points"], 0.0)
        self.assertEqual(db.get_competition()["poll_cycle"], 0,
                         "poll_cycle must not advance when paused")
        rt.poller.run_cycle.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — Quorum loss blocks variant scoring
# ---------------------------------------------------------------------------
class TestQuorumLossBlocksVariantScoring(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_quorum_loss_blocks_variant_scoring(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)

        # Only 1 of 3 nodes is 'running' for variant A — below min_healthy_nodes=2
        snapshots = [
            _snap(host=HOSTS[0], variant="A", king="Team Alpha", mtime=900),
            _snap(host=HOSTS[1], variant="A", king=None, mtime=None, status="failed"),
            _snap(host=HOSTS[2], variant="A", king=None, mtime=None, status="failed"),
            *[_snap(host=h, variant=v) for h in HOSTS for v in ("B", "C")],
        ]
        rt.poller.run_cycle = Mock(return_value=(snapshots, {}))

        rt.poll_once()

        self.assertEqual(db.get_team("Team Alpha")["total_points"], 0.0,
                         "No points should be awarded below quorum")
        events = db.list_events(limit=30)
        self.assertTrue(any("insufficient healthy replicas" in e["detail"] for e in events))


# ---------------------------------------------------------------------------
# Test 3 — Referee restart recreates rotation job from DB next_rotation
# ---------------------------------------------------------------------------
class TestRestartRestoresRotationJobFromDB(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_restart_recreates_rotation_job_from_db(self):
        rt, db = _make_runtime(self)
        future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        db.set_competition_state(
            status="running",
            current_series=1,
            next_rotation=future_time,
        )
        # Patch _sync_haproxy_active_series so start_scheduler doesn't fail
        rt._sync_haproxy_active_series = Mock()

        rt.start_scheduler()

        job = rt.scheduler.get_job("rotate")
        self.assertIsNotNone(job, "rotate job must be scheduled after restart")
        self.assertEqual(job["run_date"].isoformat(), future_time)


# ---------------------------------------------------------------------------
# Test 4 — Partial probe synthesises missing variants as unreachable
# ---------------------------------------------------------------------------
class TestPartialProbeSynthesesMissingVariantAsUnreachable(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_partial_probe_generates_incomplete_matrix_event(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)

        # Only deliver 6 of 9 expected snapshots (node[2] missing entirely)
        partial = [_snap(host=h, variant=v) for h in HOSTS[:2] for v in ("A", "B", "C")]
        rt.poller.run_cycle = Mock(return_value=(partial, {}))

        rt.poll_once()

        events = db.list_events(limit=30)
        self.assertTrue(
            any("incomplete snapshot matrix" in e["detail"] for e in events),
            "Should log incomplete matrix event when a node's variants are missing",
        )
        # Scoring must also be suppressed
        self.assertEqual(db.get_team("Team Alpha")["total_points"], 0.0)


# ---------------------------------------------------------------------------
# Test 5 — Failed rotation rolls back to previous series
# ---------------------------------------------------------------------------
class TestFailedRotationRollsBackToPreviousSeries(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
            deploy_health_timeout_seconds=1,
            deploy_health_poll_seconds=0,
            total_series=8,
        )

    def test_failed_rotation_rolls_back(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)
        rt.poll_once = Mock()

        # Target deploy returns empty snapshots (health gate fails)
        # Rollback deploy (current=1) returns healthy snapshots
        healthy = _full_matrix()

        call_count = {"n": 0}

        def run_cycle(series):
            call_count["n"] += 1
            if series == 2:
                return [], {}
            return healthy, {}

        rt.poller.run_cycle = Mock(side_effect=lambda series, **_: run_cycle(series))

        with patch("scheduler.fire_and_forget", lambda p: None), \
             patch("scheduler.time.sleep", return_value=None), \
             patch("scheduler.time.monotonic", side_effect=[0, 2, 0, 0, 0]):
            rt.rotate_to_series(2)

        state = db.get_competition()
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["current_series"], 1,
                         "Should roll back to H1 after H2 deploy fails")
        events = db.list_events(limit=30)
        self.assertTrue(
            any("rolled back to H1" in e["detail"] for e in events)
        )


# ---------------------------------------------------------------------------
# Test 6 — Resume requires revalidation before returning to 'running'
# ---------------------------------------------------------------------------
class TestResumeRequiresRevalidation(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_resume_calls_validate_before_running(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="paused", current_series=2)

        validate_called = []
        original_validate = rt._validate_current_series_or_raise

        def spy_validate(*, series):
            validate_called.append(series)
            return original_validate(series=series)

        rt._validate_current_series_or_raise = spy_validate
        rt.poller.run_cycle = Mock(return_value=(_full_matrix(), {}))
        rt._sync_haproxy_active_series = Mock()
        rt._arm_rotation_from_now = Mock()

        rt.resume_rotation()

        self.assertTrue(validate_called, "validate must be called during resume")
        self.assertEqual(db.get_competition()["status"], "running")

    def test_resume_faults_if_validation_fails(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="paused", current_series=2)

        # Poller returns empty snapshots → validation fails (no healthy nodes)
        rt.poller.run_cycle = Mock(return_value=([], {}))

        with self.assertRaises(RuntimeGuardError):
            rt.resume_rotation()

        self.assertEqual(db.get_competition()["status"], "faulted")


# ---------------------------------------------------------------------------
# Test 7 — restart_current_series uses health gate → faults on failure
# ---------------------------------------------------------------------------
class TestRestartCurrentSeriesUsesHealthGate(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
            deploy_health_timeout_seconds=1,
            deploy_health_poll_seconds=0,
        )

    def test_restart_faults_when_health_gate_fails(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=3)

        rt._run_compose_parallel = Mock(return_value={})
        # Health probe always returns no snapshots → health gate fails
        rt.poller.run_cycle = Mock(return_value=([], {}))

        with patch("scheduler.fire_and_forget", lambda p: None), \
             patch("scheduler.time.sleep", return_value=None), \
             patch("scheduler.time.monotonic", side_effect=[0, 2]):
            with self.assertRaises(RuntimeGuardError):
                rt.restart_current_series()

        state = db.get_competition()
        self.assertEqual(state["status"], "faulted")


# ---------------------------------------------------------------------------
# Test 8 — faulted state blocks resume (only paused→running is allowed)
# ---------------------------------------------------------------------------
class TestFaultedStateBlocksResume(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_faulted_state_blocks_resume(self):
        rt, db = _make_runtime(self)
        db.set_competition_state(status="faulted", current_series=1)
        rt.poller.run_cycle = Mock(return_value=(_full_matrix(), {}))

        # resume_rotation should silently return (only allows paused→running)
        rt.resume_rotation()

        state = db.get_competition()
        self.assertEqual(state["status"], "faulted",
                         "Status must remain faulted — resume only works from paused")


# ---------------------------------------------------------------------------
# Test 9 — next_rotation is stored as absolute ISO timestamp, not relative
# ---------------------------------------------------------------------------
class TestRotationUsesAbsoluteNextRotationTime(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
            rotation_interval_seconds=3600,
        )

    def test_next_rotation_stored_as_absolute_datetime(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)

        before = datetime.now(UTC)
        next_rotation_iso = rt._arm_rotation_from_now()
        after = datetime.now(UTC)

        parsed = datetime.fromisoformat(next_rotation_iso)
        # Must be ~3600 s in the future, not a relative offset
        self.assertGreater(parsed, before + timedelta(seconds=3590))
        self.assertLess(parsed, after + timedelta(seconds=3610))

        stored = db.get_competition()["next_rotation"]
        self.assertEqual(stored, next_rotation_iso,
                         "Stored next_rotation must match returned ISO string")


# ---------------------------------------------------------------------------
# Test 10 — variant_ownership row is written after quorum winner accepted
# ---------------------------------------------------------------------------
class TestAuthoritativeOwnerPersistedPerVariant(unittest.TestCase):
    def setUp(self):
        _override_settings(
            self,
            node_hosts=HOSTS,
            node_priority=HOSTS,
            variants=("A", "B", "C"),
            min_healthy_nodes=2,
        )

    def test_variant_ownership_row_written_after_quorum_win(self):
        rt, db = _make_runtime(self)
        db.upsert_team_names(["Team Alpha"])
        db.set_competition_state(status="running", current_series=1)

        snapshots = [
            _snap(host=HOSTS[0], variant="A", king="Team Alpha", mtime=1000),
            _snap(host=HOSTS[1], variant="A", king="Team Alpha", mtime=1005),
            _snap(host=HOSTS[2], variant="A", king="unclaimed", mtime=1010),
            *[_snap(host=h, variant=v) for h in HOSTS for v in ("B", "C")],
        ]
        rt.poller.run_cycle = Mock(return_value=(snapshots, {}))
        rt._reconcile_authoritative_owner = Mock()

        rt.poll_once()

        owner = db.get_variant_owner(series=1, variant="A")
        self.assertIsNotNone(owner, "variant_ownership row must exist after quorum win")
        self.assertEqual(owner["owner_team"], "Team Alpha")
        self.assertEqual(owner["accepted_mtime_epoch"], 1000,
                         "Must record the earliest accepted mtime across quorum nodes")


if __name__ == "__main__":
    unittest.main()
