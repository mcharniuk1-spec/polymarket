from __future__ import annotations

import time
from typing import Any

from .agents import MultiAgentPipeline
from .backtesting import Backtester
from .dashboard_enrichment import enrich_multi_agent_payload
from .odds_ingestion import OddsIngestion
from .odds_movement import OddsMovementAnalyzer
from .reporting import PerformanceReporter, multi_agent_payload, report_payload


CACHE_TTL_SECONDS = 15 * 60
_CACHE: dict[tuple[str, int], tuple[float, dict[str, Any], str]] = {}


def build_dashboard_payload(source_mode: str = "fixture", target_count: int = 300, *, use_cache: bool = True) -> dict[str, Any]:
    key = (source_mode, target_count)
    now = time.time()
    cached = _CACHE.get(key)
    if use_cache and cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    backtest_result = Backtester().run(write_log=False)
    multi_agent_result = MultiAgentPipeline().run(source_mode=source_mode, target_count=target_count)
    all_snapshots = []
    for snapshots in OddsIngestion().by_event().values():
        all_snapshots.extend(snapshots)

    payload = report_payload(backtest_result)
    payload["odds_history"] = OddsMovementAnalyzer.history_rows(all_snapshots)
    payload["multi_agent"] = enrich_multi_agent_payload(multi_agent_payload(multi_agent_result))
    payload["refresh_policy"] = {
        "browser_interval_seconds": CACHE_TTL_SECONDS,
        "server_cache_seconds": CACHE_TTL_SECONDS,
        "source_mode": source_mode,
        "target_count": target_count,
        "live_fetch_default": False,
    }
    report_text = PerformanceReporter().to_markdown(backtest_result)
    _CACHE[key] = (now, payload, report_text)
    return payload


def build_report_text(source_mode: str = "fixture", target_count: int = 300) -> str:
    key = (source_mode, target_count)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[2]
    build_dashboard_payload(source_mode=source_mode, target_count=target_count, use_cache=True)
    return _CACHE[key][2]
