from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .models import OddsSnapshot
from .odds_math import american_to_implied_probability


DEFAULT_ODDS_PATH = Path("data/historical_odds.csv")


class OddsIngestion:
    def __init__(self, path: Path | str = DEFAULT_ODDS_PATH) -> None:
        self.path = Path(path)

    def load(self) -> list[OddsSnapshot]:
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return [OddsSnapshot.from_row(row) for row in csv.DictReader(handle)]

    def by_event(self) -> dict[str, list[OddsSnapshot]]:
        grouped: dict[str, list[OddsSnapshot]] = defaultdict(list)
        for snapshot in self.load():
            grouped[snapshot.event_id].append(snapshot)
        for snapshots in grouped.values():
            snapshots.sort(key=lambda item: (item.snapshot_time, item.selection))
        return dict(grouped)

    @staticmethod
    def decision_snapshots(snapshots: list[OddsSnapshot]) -> list[OddsSnapshot]:
        non_closing = [snapshot for snapshot in snapshots if not snapshot.is_closing]
        if not non_closing:
            return []
        latest_time = max(snapshot.snapshot_time for snapshot in non_closing)
        return [snapshot for snapshot in non_closing if snapshot.snapshot_time == latest_time]

    @staticmethod
    def normalize_market_probabilities(snapshots: list[OddsSnapshot]) -> dict[str, float]:
        raw = {
            snapshot.selection: american_to_implied_probability(snapshot.american_odds)
            for snapshot in snapshots
        }
        total = sum(raw.values())
        if total <= 0:
            return {selection: 0.5 for selection in raw}
        return {selection: probability / total for selection, probability in raw.items()}
