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


def resolve_earliest_winners(snapshots: list[VariantSnapshot]) -> dict[str, VariantWinner]:
    winners: dict[str, VariantWinner] = {}

    by_variant: dict[str, list[VariantSnapshot]] = {v: [] for v in SETTINGS.variants}
    for snap in snapshots:
        by_variant.setdefault(snap.variant, []).append(snap)

    priority_idx = {host: idx for idx, host in enumerate(SETTINGS.node_priority)}

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

        candidates.sort(
            key=lambda s: (
                s.king_mtime_epoch,
                priority_idx.get(s.node_host, 999),
                s.node_host,
            )
        )
        chosen = candidates[0]
        winners[variant] = VariantWinner(
            variant=variant,
            team_name=chosen.king,
            mtime_epoch=chosen.king_mtime_epoch,
            node_host=chosen.node_host,
        )

    return winners
