from __future__ import annotations

import time
from typing import Any

from .agents import MultiAgentPipeline
from .dashboard_enrichment import enrich_multi_agent_payload
from .reporting import PerformanceReporter, multi_agent_payload
from .research_scope import ACTIVE_CATEGORIES


CACHE_TTL_SECONDS = 15 * 60
_CACHE: dict[tuple[str, int], tuple[float, dict[str, Any], str]] = {}


def build_dashboard_payload(source_mode: str = "fixture", target_count: int = 300, *, use_cache: bool = True) -> dict[str, Any]:
    key = (source_mode, target_count)
    now = time.time()
    cached = _CACHE.get(key)
    if use_cache and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    multi_agent_result = MultiAgentPipeline().run(source_mode=source_mode, target_count=target_count)
    multi_agent = enrich_multi_agent_payload(multi_agent_payload(multi_agent_result))
    payload = {
        "research_only": True,
        "paper_trading_only": True,
        "active_sections": list(ACTIVE_CATEGORIES),
        "scope_notice": (
            "Dashboard payload is limited to macroeconomics, politics, and stocks/trade. "
            "Legacy sports backtest root fields are disabled."
        ),
        "legacySportsDisabled": True,
        "metrics": _scoped_root_metrics(multi_agent.get("metrics", {})),
        "forecasts": [],
        "trades": [],
        "odds_history": [],
        "multi_agent": multi_agent,
    }
    payload["refresh_policy"] = {
        "browser_interval_seconds": CACHE_TTL_SECONDS,
        "server_cache_seconds": CACHE_TTL_SECONDS,
        "source_mode": source_mode,
        "target_count": target_count,
        "live_fetch_default": False,
    }
    report_text = PerformanceReporter().to_multi_agent_markdown(multi_agent_result)
    _CACHE[key] = (now, payload, report_text)
    return payload


def build_report_text(source_mode: str = "fixture", target_count: int = 300) -> str:
    key = (source_mode, target_count)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[2]
    build_dashboard_payload(source_mode=source_mode, target_count=target_count, use_cache=True)
    return _CACHE[key][2]


def _scoped_root_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "research_only": True,
        "paper_trading_only": True,
        "active_sections": list(ACTIVE_CATEGORIES),
        "legacy_sports_disabled": True,
        "forecast_count": 0,
        "paper_trade_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "simulated_roi": 0.0,
        "total_staked_units": float(metrics.get("total_staked_units") or 0.0),
        "total_pnl_units": 0.0,
        "ending_bankroll_units": float(metrics.get("ending_bankroll_units") or 100.0),
        "max_drawdown": float(metrics.get("max_drawdown") or 0.0),
        "brier_score": float(metrics.get("brier_score") or 0.0),
        "calibration": [],
        "candidate_count": int(metrics.get("candidate_count") or 0),
        "paper_bet_count": int(metrics.get("paper_bet_count") or 0),
        "watchlist_count": int(metrics.get("watchlist_count") or 0),
        "rejected_count": int(metrics.get("rejected_count") or 0),
        "deployment_budget_units": float(metrics.get("deployment_budget_units") or 100.0),
        "unallocated_budget_units": float(metrics.get("unallocated_budget_units") or 0.0),
    }
