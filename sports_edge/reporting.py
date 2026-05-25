from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import MultiAgentRun
from .backtesting import BacktestResult


DEFAULT_REPORT_PATH = Path("reports/performance_report.md")
DEFAULT_REPORT_JSON_PATH = Path("reports/performance_report.json")


class PerformanceReporter:
    def __init__(
        self,
        report_path: Path | str = DEFAULT_REPORT_PATH,
        json_path: Path | str = DEFAULT_REPORT_JSON_PATH,
    ) -> None:
        self.report_path = Path(report_path)
        self.json_path = Path(json_path)

    def write(self, result: BacktestResult) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(self.to_markdown(result), encoding="utf-8")
        self.json_path.write_text(
            json.dumps(
                {
                    "metrics": result.metrics,
                    "forecasts": [item.to_dict() for item in result.forecasts],
                    "trades": [item.to_dict() for item in result.trades],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def write_multi_agent(
        self,
        result: MultiAgentRun,
        report_path: Path | str = "reports/multi_agent_report.md",
        json_path: Path | str = "reports/multi_agent_run.json",
    ) -> None:
        report_file = Path(report_path)
        json_file = Path(json_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(self.to_multi_agent_markdown(result), encoding="utf-8")
        json_file.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def to_markdown(self, result: BacktestResult) -> str:
        metrics = result.metrics
        lines = [
            "# Sports Odds Research Performance Report",
            "",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "",
            "## Guardrails",
            "",
            "- Mode: research-only paper trading.",
            "- Execution: no sportsbook connection, no real-money betting, no automatic order placement.",
            "- Data: bundled historical fixture data for local MVP validation.",
            "",
            "## Summary Metrics",
            "",
            f"- Forecasts: {metrics['forecast_count']}",
            f"- Paper trades: {metrics['paper_trade_count']}",
            f"- Win/loss: {metrics['wins']}/{metrics['losses']}",
            f"- Win rate: {metrics['win_rate']:.1%}",
            f"- Simulated ROI: {metrics['simulated_roi']:.1%}",
            f"- Total PnL: {metrics['total_pnl_units']:.2f} units",
            f"- Max drawdown: {metrics['max_drawdown']:.1%}",
            f"- Brier score: {metrics['brier_score']:.4f}",
            "",
            "## Calibration",
            "",
            "| Bucket | Count | Predicted midpoint | Actual win rate |",
            "|---|---:|---:|---:|",
        ]
        for bucket in metrics["calibration"]:
            actual = "n/a" if bucket["actual_win_rate"] is None else f"{bucket['actual_win_rate']:.1%}"
            lines.append(
                f"| {bucket['label']} | {bucket['count']} | {bucket['predicted_midpoint']:.1%} | {actual} |"
            )
        lines.extend(
            [
                "",
                "## Paper Trades",
                "",
                "| Event | Selection | Odds | Prob | EV | Stake | Outcome | PnL |",
                "|---|---|---:|---:|---:|---:|---|---:|",
            ]
        )
        for trade in result.trades:
            lines.append(
                "| "
                f"{trade.matchup} | {trade.selection} | {trade.american_odds} | "
                f"{trade.fair_probability:.1%} | {trade.expected_value:.1%} | "
                f"{trade.stake_units:.2f} | {trade.outcome} | {trade.pnl_units:.2f} |"
            )
        lines.extend(
            [
                "",
                "## Limitations",
                "",
                "- Fixture data is intentionally small and not predictive of live market performance.",
                "- News sentiment is a transparent handcrafted feature, not a production NLP model.",
                "- Forecast quality must be revalidated with larger historical datasets before any real-world use.",
            ]
        )
        return "\n".join(lines) + "\n"

    def to_multi_agent_markdown(self, result: MultiAgentRun) -> str:
        metrics = result.metrics
        lines = [
            "# Polymarket Multi-Agent Paper Analytics Report",
            "",
            f"Generated: {result.created_at}",
            "",
            "## Guardrails",
            "",
            "- Mode: paper-only research analytics.",
            "- Execution: no wallet, no credentials, no order posting, no automated real-money betting.",
            "- Live mode, when selected, uses public read-only Polymarket APIs for discovery and market data.",
            f"- Source note: {result.source_note}",
            "",
            "## Overall Metrics",
            "",
            f"- Candidates analyzed: {metrics['candidate_count']}",
            f"- Paper bets: {metrics['paper_bet_count']}",
            f"- Watchlist: {metrics['watchlist_count']}",
            f"- Rejected: {metrics['rejected_count']}",
            f"- Starting bankroll: {metrics['starting_bankroll_units']:.2f} coins",
            f"- Ending bankroll: {metrics['ending_bankroll_units']:.2f} coins",
            f"- Staked: {metrics['total_staked_units']:.2f} coins",
            f"- Unallocated deployment budget: {metrics['unallocated_budget_units']:.2f} coins",
            f"- Win/loss: {metrics['wins']}/{metrics['losses']}",
            f"- Win rate: {metrics['win_rate']:.1%}",
            f"- Simulated ROI: {metrics['simulated_roi']:.1%}",
            f"- Brier score: {metrics['brier_score']:.4f}",
            f"- Log loss: {metrics['log_loss']:.4f}",
            f"- Max drawdown: {metrics['max_drawdown']:.1%}",
            "",
            "## Top 10 Paper Bets",
            "",
            "| Rank | Category | Market | Prob | Price | EV | Risk | Stake | Outcome |",
            "|---:|---|---|---:|---:|---:|---|---:|---|",
        ]
        for index, item in enumerate(result.top_bets[:10], start=1):
            candidate = item["candidate"]
            lines.append(
                "| "
                f"{index} | {candidate['category']} | {candidate['market_title']} / {candidate['outcome']} | "
                f"{item['blended_probability']:.1%} | {candidate['price']:.1%} | {item['expected_value']:.1%} | "
                f"{item['risk_tier']} | {item['stake_units']:.2f} | {item.get('outcome', 'PENDING')} |"
            )
        lines.extend(
            [
                "",
                "## Category Stats",
                "",
                "| Category | Candidates | Bets | Watchlist | Rejected | Win rate | Avg odds | Avg EV | PnL |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in result.category_stats:
            lines.append(
                "| "
                f"{row['category']} | {row['candidate_count']} | {row['paper_bet_count']} | "
                f"{row['watchlist_count']} | {row['rejected_count']} | {row['win_rate']:.1%} | "
                f"{row['average_decimal_odds']:.2f} | {row['average_ev']:.1%} | {row['pnl_units']:.2f} |"
            )
        lines.extend(
            [
                "",
                "## Agent Performance",
                "",
                "| Agent | Score | Brier | Confidence | Notes |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for row in result.agent_performance:
            brier = "n/a" if row["brier"] is None else f"{row['brier']:.4f}"
            confidence = "n/a" if row["confidence"] is None else f"{row['confidence']:.1%}"
            lines.append(
                f"| {row['agent']} | {row['score']:.2f} | {brier} | {confidence} | {row['notes']} |"
            )
        lines.extend(
            [
                "",
                "## Mistake Reviews",
                "",
                "| Candidate | Category | Type | PnL | Learning note |",
                "|---|---|---|---:|---|",
            ]
        )
        for mistake in result.mistakes[:20]:
            lines.append(
                "| "
                f"{mistake['candidate_id']} | {mistake['category']} | {mistake['mistake_type']} | "
                f"{mistake['pnl_units']:.2f} | {mistake['learning_note']} |"
            )
        lines.extend(
            [
                "",
                "## API Notes",
                "",
                "- Gamma is used for market/event/tag/sports discovery.",
                "- CLOB orderbook, midpoint, spread, last-trade, and price-history endpoints are the canonical read surface for executable market analytics.",
                "- Data API trade/activity/holders/open-interest endpoints should be used for public market history and participation signals.",
                "- UI scraping is not used for data that official APIs expose.",
                "",
                "## Reliability Note",
                "",
                "This system estimates positive expected value and paper performance. It does not guarantee daily profit and does not execute real-money trades.",
            ]
        )
        return "\n".join(lines) + "\n"


def report_payload(result: BacktestResult) -> dict[str, Any]:
    return {
        "metrics": result.metrics,
        "forecasts": [item.to_dict() for item in result.forecasts],
        "trades": [item.to_dict() for item in result.trades],
    }


def multi_agent_payload(result: MultiAgentRun) -> dict[str, Any]:
    return result.to_dict()
