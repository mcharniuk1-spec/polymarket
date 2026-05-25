from __future__ import annotations

from dataclasses import dataclass

from .odds_math import american_to_decimal, clamp


RESEARCH_ONLY_MODE = "paper"


@dataclass(frozen=True)
class RiskDecision:
    decision: str
    stake_units: float
    reason: str


class RiskControl:
    """Paper-trading guardrails. No real-money execution exists here."""

    def __init__(
        self,
        min_ev: float = 0.005,
        min_confidence: float = 0.05,
        max_stake_units: float = 1.5,
        max_daily_units: float = 5.0,
    ) -> None:
        self.min_ev = min_ev
        self.min_confidence = min_confidence
        self.max_stake_units = max_stake_units
        self.max_daily_units = max_daily_units

    def evaluate(
        self,
        fair_probability: float,
        expected_value: float,
        confidence: float,
        american_odds: int,
        current_day_exposure: float,
    ) -> RiskDecision:
        if expected_value < self.min_ev:
            return RiskDecision("NO_PLAY", 0.0, "EV below paper-trade threshold")
        if confidence < self.min_confidence:
            return RiskDecision("NO_PLAY", 0.0, "Confidence below paper-trade threshold")
        if current_day_exposure >= self.max_daily_units:
            return RiskDecision("NO_PLAY", 0.0, "Daily simulated exposure cap reached")

        decimal_odds = american_to_decimal(american_odds)
        kelly_fraction = (fair_probability * decimal_odds - 1.0) / max(decimal_odds - 1.0, 0.01)
        stake = clamp(kelly_fraction * 4.0, 0.25, self.max_stake_units)
        stake = min(stake, self.max_daily_units - current_day_exposure)
        return RiskDecision("PAPER_TRADE", round(stake, 2), "Research-only paper trade accepted")
