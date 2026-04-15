from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from db import Database


@dataclass
class EnforcementResult:
    team_name: str
    offense_count: int
    action: str


class Enforcer:
    def __init__(self, db: Database):
        self._db = db

    def escalate_team(self, team_name: str) -> EnforcementResult:
        offense_count, status = self._db.increment_team_offense(team_name)
        if status == "warned":
            action = "warning"
        elif status == "series_banned":
            action = "series_ban"
        else:
            action = "full_ban"
        return EnforcementResult(team_name=team_name, offense_count=offense_count, action=action)

    def record_violation(
        self,
        *,
        team_name: str,
        machine: str,
        variant: str,
        series: int,
        offense_id: int,
        offense_name: str,
        evidence: dict[str, Any],
        action: str,
    ) -> None:
        self._db.record_violation(
            team_name=team_name,
            machine=machine,
            variant=variant,
            series=series,
            offense_id=offense_id,
            offense_name=offense_name,
            evidence=evidence,
            action_taken=action,
        )

        self._db.add_event(
            event_type="violation",
            severity="warning" if action == "warning" else "critical",
            machine=machine,
            variant=variant,
            series=series,
            team_name=team_name,
            detail=f"Violation {offense_id} ({offense_name}) -> {action}",
            evidence=evidence,
        )
