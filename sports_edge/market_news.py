from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .models import NewsItem
from .odds_math import clamp


DEFAULT_NEWS_PATH = Path("data/market_news.csv")


class MarketNewsContext:
    def __init__(self, path: Path | str = DEFAULT_NEWS_PATH) -> None:
        self.path = Path(path)

    def load(self) -> list[NewsItem]:
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            return [NewsItem.from_row(row) for row in csv.DictReader(handle)]

    def by_event(self) -> dict[str, list[NewsItem]]:
        grouped: dict[str, list[NewsItem]] = defaultdict(list)
        for item in self.load():
            grouped[item.event_id].append(item)
        for items in grouped.values():
            items.sort(key=lambda item: item.published_at)
        return dict(grouped)

    @staticmethod
    def score_for_selection(items: list[NewsItem], selection: str) -> float:
        score = 0.0
        for item in items:
            if item.target_team == selection:
                direction = 1.0
            elif item.target_team:
                direction = -0.45
            else:
                direction = 0.25
            score += item.sentiment * item.impact_score * direction
        return clamp(score, -1.0, 1.0)
