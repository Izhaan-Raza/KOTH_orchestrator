from __future__ import annotations

from dataclasses import dataclass

from config import SETTINGS
from poller import Poller, VariantSnapshot


@dataclass
class VariantWinner:
    variant: str
    team_name: str
    mtime_epoch: int
    node_host: str
    supporting_nodes: int


def resolve_earliest_winners(
    snapshots: list[VariantSnapshot],
    *,
    current_owners: dict[str, dict[str, object]] | None = None,
) -> dict[str, VariantWinner]:
    winners: dict[str, VariantWinner] = {}

    by_variant: dict[str, list[VariantSnapshot]] = {v: [] for v in SETTINGS.variants}
    for snap in snapshots:
        by_variant.setdefault(snap.variant, []).append(snap)

    priority_idx = {host: idx for idx, host in enumerate(SETTINGS.node_priority)}

    def sort_key(snap: VariantSnapshot) -> tuple[int, int, str]:
        return (
            snap.king_mtime_epoch or 0,
            priority_idx.get(snap.node_host, 999),
            snap.node_host,
        )

    for variant, entries in by_variant.items():
        candidates: list[VariantSnapshot] = []
        for entry in entries:
            if entry.status != "running":
                continue
            if entry.king is None:
                continue
            if entry.king.lower() == "unclaimed":
                continue
            if not Poller.is_valid_team_claim(entry.king):
                continue
            if entry.king_mtime_epoch is None:
                continue
            candidates.append(entry)

        if not candidates:
            continue

        by_team: dict[str, list[VariantSnapshot]] = {}
        for candidate in candidates:
            by_team.setdefault(candidate.king, []).append(candidate)

        current_owner_team = None
        if current_owners:
            current_owner = current_owners.get(variant)
            if current_owner:
                current_owner_team = str(current_owner.get("owner_team") or "")

        if current_owner_team:
            supporting = by_team.get(current_owner_team, [])
            if len(supporting) >= SETTINGS.min_healthy_nodes:
                chosen = min(supporting, key=sort_key)
                winners[variant] = VariantWinner(
                    variant=variant,
                    team_name=chosen.king,
                    mtime_epoch=chosen.king_mtime_epoch,
                    node_host=chosen.node_host,
                    supporting_nodes=len(supporting),
                )
                continue

        quorum_candidates: list[tuple[VariantSnapshot, int]] = []
        for team_name, team_snaps in by_team.items():
            if len(team_snaps) < SETTINGS.min_healthy_nodes:
                continue
            quorum_candidates.append((min(team_snaps, key=sort_key), len(team_snaps)))

        if not quorum_candidates:
            continue

        chosen, supporting_nodes = min(quorum_candidates, key=lambda item: sort_key(item[0]))
        winners[variant] = VariantWinner(
            variant=variant,
            team_name=chosen.king,
            mtime_epoch=chosen.king_mtime_epoch,
            node_host=chosen.node_host,
            supporting_nodes=supporting_nodes,
        )

    return winners
