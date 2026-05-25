from __future__ import annotations

from statistics import pstdev

from .models import OddsSnapshot
from .odds_math import american_to_implied_probability, clamp


class OddsMovementAnalyzer:
    @staticmethod
    def movement_for_selection(
        snapshots: list[OddsSnapshot],
        selection: str,
        latest: OddsSnapshot,
    ) -> dict[str, float | int]:
        history = [item for item in snapshots if item.selection == selection]
        history.sort(key=lambda item: item.snapshot_time)
        if not history:
            return {
                "opening_odds": latest.american_odds,
                "latest_odds": latest.american_odds,
                "closing_odds": latest.american_odds,
                "probability_delta": 0.0,
                "volatility": 0.0,
                "movement_score": 0.0,
            }

        opening = history[0]
        closing = next((item for item in reversed(history) if item.is_closing), history[-1])
        implied_values = [american_to_implied_probability(item.american_odds) for item in history]
        open_prob = american_to_implied_probability(opening.american_odds)
        latest_prob = american_to_implied_probability(latest.american_odds)
        probability_delta = latest_prob - open_prob
        volatility = pstdev(implied_values) if len(implied_values) > 1 else 0.0
        movement_score = clamp((probability_delta * 4.0) - (volatility * 0.7), -1.0, 1.0)
        return {
            "opening_odds": opening.american_odds,
            "latest_odds": latest.american_odds,
            "closing_odds": closing.american_odds,
            "probability_delta": probability_delta,
            "volatility": volatility,
            "movement_score": movement_score,
        }

    @staticmethod
    def history_rows(snapshots: list[OddsSnapshot]) -> list[dict[str, object]]:
        return [
            {
                "event_id": item.event_id,
                "selection": item.selection,
                "snapshot_time": item.snapshot_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "american_odds": item.american_odds,
                "is_closing": item.is_closing,
            }
            for item in sorted(snapshots, key=lambda row: (row.event_id, row.selection, row.snapshot_time))
        ]
