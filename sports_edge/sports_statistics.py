from __future__ import annotations

import csv
import math
from pathlib import Path

from .models import OddsSnapshot, TeamStats
from .odds_math import clamp


DEFAULT_STATS_PATH = Path("data/team_stats.csv")


class SportsStatistics:
    def __init__(self, path: Path | str = DEFAULT_STATS_PATH) -> None:
        self.path = Path(path)
        self._stats: dict[str, TeamStats] | None = None

    def load(self) -> dict[str, TeamStats]:
        if self._stats is not None:
            return self._stats
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            self._stats = {
                row["team"]: TeamStats.from_row(row)
                for row in csv.DictReader(handle)
            }
        return self._stats

    def selection_probability(self, snapshot: OddsSnapshot) -> float:
        stats = self.load()
        home = stats[snapshot.home_team]
        away = stats[snapshot.away_team]
        rating_diff = home.adjusted_rating - away.adjusted_rating
        home_probability = 1.0 / (1.0 + math.exp(-(rating_diff / 18.0)))
        if snapshot.selection == snapshot.home_team:
            return clamp(home_probability, 0.05, 0.95)
        return clamp(1.0 - home_probability, 0.05, 0.95)

    def edge_for_selection(self, snapshot: OddsSnapshot) -> float:
        stats_probability = self.selection_probability(snapshot)
        return clamp((stats_probability - 0.5) * 2.0, -1.0, 1.0)
