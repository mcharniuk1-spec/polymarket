from __future__ import annotations

from .market_news import MarketNewsContext
from .models import Forecast, OddsSnapshot
from .odds_ingestion import OddsIngestion
from .odds_math import american_to_implied_probability, clamp, expected_value
from .odds_movement import OddsMovementAnalyzer
from .risk_control import RiskControl
from .sports_statistics import SportsStatistics


class FinalSynthesis:
    def __init__(
        self,
        odds: OddsIngestion | None = None,
        news: MarketNewsContext | None = None,
        stats: SportsStatistics | None = None,
        movement: OddsMovementAnalyzer | None = None,
        risk: RiskControl | None = None,
    ) -> None:
        self.odds = odds or OddsIngestion()
        self.news = news or MarketNewsContext()
        self.stats = stats or SportsStatistics()
        self.movement = movement or OddsMovementAnalyzer()
        self.risk = risk or RiskControl()

    def build_forecasts(self) -> list[Forecast]:
        events = self.odds.by_event()
        news_by_event = self.news.by_event()
        forecasts: list[Forecast] = []

        for event_id, snapshots in sorted(events.items()):
            decision_snapshots = self.odds.decision_snapshots(snapshots)
            if not decision_snapshots:
                continue
            market_probabilities = self.odds.normalize_market_probabilities(decision_snapshots)
            event_news = news_by_event.get(event_id, [])
            day_exposure = 0.0
            event_forecasts: list[Forecast] = []

            for snapshot in decision_snapshots:
                forecast = self._forecast_snapshot(
                    snapshot=snapshot,
                    all_snapshots=snapshots,
                    market_probability=market_probabilities[snapshot.selection],
                    event_news=event_news,
                    current_day_exposure=day_exposure,
                )
                event_forecasts.append(forecast)

            playable = [item for item in event_forecasts if item.expected_value > 0]
            if playable:
                best = max(playable, key=lambda item: (item.expected_value, item.confidence))
                risk_decision = self.risk.evaluate(
                    fair_probability=best.fair_probability,
                    expected_value=best.expected_value,
                    confidence=best.confidence,
                    american_odds=best.american_odds,
                    current_day_exposure=day_exposure,
                )
                day_exposure += risk_decision.stake_units
                event_forecasts = [
                    self._with_decision(item, risk_decision.decision, risk_decision.stake_units, risk_decision.reason)
                    if item.selection == best.selection
                    else self._with_decision(item, "NO_PLAY", 0.0, "Lower EV than selected side")
                    for item in event_forecasts
                ]
            else:
                event_forecasts = [
                    self._with_decision(item, "NO_PLAY", 0.0, "No positive expected value side")
                    for item in event_forecasts
                ]

            forecasts.extend(event_forecasts)

        return forecasts

    def _forecast_snapshot(
        self,
        snapshot: OddsSnapshot,
        all_snapshots: list[OddsSnapshot],
        market_probability: float,
        event_news: list,
        current_day_exposure: float,
    ) -> Forecast:
        stats_probability = self.stats.selection_probability(snapshot)
        stats_edge = self.stats.edge_for_selection(snapshot)
        news_score = MarketNewsContext.score_for_selection(event_news, snapshot.selection)
        movement = self.movement.movement_for_selection(all_snapshots, snapshot.selection, snapshot)
        movement_score = float(movement["movement_score"])

        raw_probability = (
            (market_probability * 0.48)
            + (stats_probability * 0.34)
            + ((0.5 + (news_score * 0.12)) * 0.10)
            + ((0.5 + (movement_score * 0.10)) * 0.08)
        )
        fair_probability = clamp(raw_probability, 0.03, 0.97)
        implied = american_to_implied_probability(snapshot.american_odds)
        ev = expected_value(fair_probability, snapshot.american_odds)
        confidence = clamp(abs(fair_probability - implied) * 1.6 + abs(fair_probability - 0.5) * 0.45, 0.0, 1.0)
        risk_decision = self.risk.evaluate(
            fair_probability=fair_probability,
            expected_value=ev,
            confidence=confidence,
            american_odds=snapshot.american_odds,
            current_day_exposure=current_day_exposure,
        )

        return Forecast(
            event_id=snapshot.event_id,
            sport=snapshot.sport,
            league=snapshot.league,
            event_date=snapshot.event_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            matchup=f"{snapshot.away_team} at {snapshot.home_team}",
            selection=snapshot.selection,
            side=snapshot.side,
            american_odds=snapshot.american_odds,
            implied_probability=round(implied, 4),
            fair_probability=round(fair_probability, 4),
            confidence=round(confidence, 4),
            expected_value=round(ev, 4),
            movement_score=round(movement_score, 4),
            news_score=round(news_score, 4),
            stats_edge=round(stats_edge, 4),
            decision=risk_decision.decision,
            stake_units=risk_decision.stake_units,
            reason=risk_decision.reason,
        )

    @staticmethod
    def _with_decision(forecast: Forecast, decision: str, stake_units: float, reason: str) -> Forecast:
        return Forecast(
            event_id=forecast.event_id,
            sport=forecast.sport,
            league=forecast.league,
            event_date=forecast.event_date,
            matchup=forecast.matchup,
            selection=forecast.selection,
            side=forecast.side,
            american_odds=forecast.american_odds,
            implied_probability=forecast.implied_probability,
            fair_probability=forecast.fair_probability,
            confidence=forecast.confidence,
            expected_value=forecast.expected_value,
            movement_score=forecast.movement_score,
            news_score=forecast.news_score,
            stats_edge=forecast.stats_edge,
            decision=decision,
            stake_units=stake_units,
            reason=reason,
        )
