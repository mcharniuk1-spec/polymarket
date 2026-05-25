from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Forecast, TradeRecord
from .odds_ingestion import OddsIngestion
from .odds_math import profit_for_result
from .synthesis import FinalSynthesis


DEFAULT_PAPER_LOG_PATH = Path("data/paper_trades.jsonl")


@dataclass(frozen=True)
class BacktestResult:
    forecasts: list[Forecast]
    trades: list[TradeRecord]
    metrics: dict[str, Any]


class Backtester:
    def __init__(
        self,
        synthesis: FinalSynthesis | None = None,
        odds: OddsIngestion | None = None,
        paper_log_path: Path | str = DEFAULT_PAPER_LOG_PATH,
        starting_bankroll_units: float = 100.0,
    ) -> None:
        self.synthesis = synthesis or FinalSynthesis()
        self.odds = odds or OddsIngestion()
        self.paper_log_path = Path(paper_log_path)
        self.starting_bankroll_units = starting_bankroll_units

    def run(self, write_log: bool = True) -> BacktestResult:
        forecasts = self.synthesis.build_forecasts()
        events = self.odds.by_event()
        trades: list[TradeRecord] = []
        bankroll = self.starting_bankroll_units
        peak = bankroll
        max_drawdown = 0.0

        for forecast in forecasts:
            if forecast.decision != "PAPER_TRADE":
                continue
            event_snapshots = events[forecast.event_id]
            winner = event_snapshots[0].winner
            won = forecast.selection == winner
            pnl = round(profit_for_result(forecast.stake_units, forecast.american_odds, won), 4)
            bankroll = round(bankroll + pnl, 4)
            peak = max(peak, bankroll)
            drawdown = round((peak - bankroll) / peak, 4) if peak else 0.0
            max_drawdown = max(max_drawdown, drawdown)
            trades.append(
                TradeRecord(
                    decision_id=f"{forecast.event_id}:{forecast.selection}",
                    created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    mode="paper",
                    event_id=forecast.event_id,
                    league=forecast.league,
                    matchup=forecast.matchup,
                    selection=forecast.selection,
                    side=forecast.side,
                    american_odds=forecast.american_odds,
                    implied_probability=forecast.implied_probability,
                    fair_probability=forecast.fair_probability,
                    confidence=forecast.confidence,
                    expected_value=forecast.expected_value,
                    stake_units=forecast.stake_units,
                    outcome="WIN" if won else "LOSS",
                    pnl_units=pnl,
                    bankroll_after=bankroll,
                    reason=forecast.reason,
                )
            )

        metrics = self._metrics(forecasts, trades, bankroll, max_drawdown)
        if write_log:
            self.write_paper_log(trades)
        return BacktestResult(forecasts=forecasts, trades=trades, metrics=metrics)

    def write_paper_log(self, trades: list[TradeRecord]) -> None:
        self.paper_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.paper_log_path.open("w", encoding="utf-8") as handle:
            for trade in trades:
                handle.write(json.dumps(trade.to_dict(), sort_keys=True) + "\n")

    def _metrics(
        self,
        forecasts: list[Forecast],
        trades: list[TradeRecord],
        bankroll: float,
        max_drawdown: float,
    ) -> dict[str, Any]:
        total_staked = round(sum(item.stake_units for item in trades), 4)
        total_pnl = round(sum(item.pnl_units for item in trades), 4)
        wins = sum(1 for item in trades if item.outcome == "WIN")
        losses = sum(1 for item in trades if item.outcome == "LOSS")
        roi = round(total_pnl / total_staked, 4) if total_staked else 0.0
        brier = self._brier_score(trades)
        calibration = self._calibration_buckets(trades)
        return {
            "research_only": True,
            "forecast_count": len(forecasts),
            "paper_trade_count": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(trades), 4) if trades else 0.0,
            "total_staked_units": total_staked,
            "total_pnl_units": total_pnl,
            "simulated_roi": roi,
            "ending_bankroll_units": bankroll,
            "max_drawdown": round(max_drawdown, 4),
            "brier_score": brier,
            "calibration": calibration,
            "bankroll_curve": [
                {"decision_id": item.decision_id, "bankroll_after": item.bankroll_after}
                for item in trades
            ],
        }

    @staticmethod
    def _brier_score(trades: list[TradeRecord]) -> float:
        if not trades:
            return 0.0
        total = 0.0
        for trade in trades:
            actual = 1.0 if trade.outcome == "WIN" else 0.0
            total += (trade.fair_probability - actual) ** 2
        return round(total / len(trades), 4)

    @staticmethod
    def _calibration_buckets(trades: list[TradeRecord]) -> list[dict[str, Any]]:
        buckets = [
            {"label": "0.50-0.55", "low": 0.50, "high": 0.55, "count": 0, "wins": 0},
            {"label": "0.55-0.60", "low": 0.55, "high": 0.60, "count": 0, "wins": 0},
            {"label": "0.60-0.65", "low": 0.60, "high": 0.65, "count": 0, "wins": 0},
            {"label": "0.65+", "low": 0.65, "high": 1.01, "count": 0, "wins": 0},
        ]
        for trade in trades:
            for bucket in buckets:
                if bucket["low"] <= trade.fair_probability < bucket["high"]:
                    bucket["count"] += 1
                    if trade.outcome == "WIN":
                        bucket["wins"] += 1
                    break
        return [
            {
                "label": bucket["label"],
                "count": bucket["count"],
                "predicted_midpoint": round((bucket["low"] + min(bucket["high"], 1.0)) / 2, 3),
                "actual_win_rate": round(bucket["wins"] / bucket["count"], 4) if bucket["count"] else None,
            }
            for bucket in buckets
        ]
