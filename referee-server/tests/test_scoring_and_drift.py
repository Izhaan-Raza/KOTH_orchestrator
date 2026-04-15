from __future__ import annotations

import types
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if "paramiko" not in sys.modules:
    fake_paramiko = types.SimpleNamespace(
        SSHClient=object,
        RejectPolicy=object,
        AutoAddPolicy=object,
    )
    sys.modules["paramiko"] = fake_paramiko

from poller import VariantSnapshot
from scheduler import RefereeRuntime
from scorer import resolve_earliest_winners


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
    def test_resolve_winner_excludes_degraded_and_uses_node_priority_tie_break(self) -> None:
        snapshots = [
            _snapshot(node_host="10.0.0.13", king="Team C", king_mtime_epoch=900, status="degraded"),
            _snapshot(node_host="10.0.0.11", king="Team A", king_mtime_epoch=1000, status="running"),
            _snapshot(node_host="10.0.0.12", king="Team B", king_mtime_epoch=1000, status="running"),
        ]

        winners = resolve_earliest_winners(snapshots)
        self.assertEqual(winners["A"].team_name, "Team A")
        self.assertEqual(winners["A"].node_host, "10.0.0.11")

    def test_resolve_winner_skips_malformed_claims(self) -> None:
        snapshots = [
            _snapshot(node_host="10.0.0.11", king="Bad\x01Team", king_mtime_epoch=900),
            _snapshot(node_host="10.0.0.12", king="Good Team", king_mtime_epoch=950),
        ]

        winners = resolve_earliest_winners(snapshots)
        self.assertEqual(winners["A"].team_name, "Good Team")

    def test_mark_clock_drift_degraded(self) -> None:
        runtime = object.__new__(RefereeRuntime)
        runtime._log_event_and_webhook = Mock()

        snapshots = [
            _snapshot(node_host="10.0.0.11", node_epoch=1000),
            _snapshot(node_host="10.0.0.12", node_epoch=1001),
            _snapshot(node_host="10.0.0.13", node_epoch=1010),
        ]

        degraded = RefereeRuntime._mark_clock_drift_degraded(runtime, series=1, snapshots=snapshots)
        self.assertEqual(degraded, {"10.0.0.13"})
        self.assertEqual(snapshots[2].status, "degraded")
        runtime._log_event_and_webhook.assert_called_once()


if __name__ == "__main__":
    unittest.main()
