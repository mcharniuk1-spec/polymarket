from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import replace
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .agents import (
    ACTIVE_CATEGORIES,
    AgentAssessment,
    CategoryExpertAgent,
    DecisionBankrollAgent,
    EvaluationLearningAgent,
    MarketCandidate,
    MarketContextNewsAgent,
    MultiAgentRun,
    OddsModelingAgent,
    iso_z,
    now_utc,
)
from .dashboard_enrichment import enrich_multi_agent_payload
from .external_sources import build_external_data_readiness
from .intelligence import run_intelligence_cycle
from .managed_pipeline import _correlation_pairs, _latest_full_scan_dashboard
from .odds_math import clamp
from .polymarket_client import PolymarketClientError, PolymarketPublicClient, parse_polymarket_list
from .research_scope import normalize_category_id
from .reporting import multi_agent_payload
from .source_registry import SourceRegistry


DEFAULT_OUTPUT_DIR = Path("data/generated/full_scan")
DEFAULT_REPORT_PATH = Path("reports/full_scan_top_100.md")


def run_full_scan(
    *,
    max_pages: int = 30,
    page_size: int = 100,
    top_limit: int = 100,
    scan_date: str | None = None,
    current_day_only: bool = True,
    min_liquidity: float = 1.0,
    max_spread: float = 0.25,
    history_sample_limit: int = 200,
    history_hours: int = 24,
    history_fidelity: int = 60,
    persist: bool = True,
    run_intelligence: bool = True,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    client: PolymarketPublicClient | None = None,
) -> dict[str, Any]:
    scan_started_at = iso_z(now_utc())
    target_date = scan_date or datetime.now(timezone.utc).date().isoformat()
    state_dir = Path(output_dir)
    previous = _read_json(state_dir / "latest_full_scan.json")
    registry = SourceRegistry()
    registry.require_valid()

    market_client = client or PolymarketPublicClient(timeout_seconds=20.0)
    raw_markets, page_summaries, stop_reason = scan_gamma_markets(
        market_client,
        max_pages=max_pages,
        page_size=page_size,
        scan_date=target_date,
        current_day_only=current_day_only,
    )
    candidates, excluded = build_candidates_from_markets(
        raw_markets,
        scan_started_at=scan_started_at,
        min_liquidity=min_liquidity,
        max_spread=max_spread,
    )
    candidates, time_series = enrich_candidates_with_clob_history(
        candidates,
        market_client,
        scan_started_at=scan_started_at,
        sample_limit=history_sample_limit,
        history_hours=history_hours,
        fidelity=history_fidelity,
    )
    multi_agent = run_candidate_agents(candidates, top_limit=top_limit)
    enriched = enrich_multi_agent_payload(multi_agent_payload(multi_agent))
    ranked = sorted(multi_agent.recommendations, key=lambda row: row["rank_score"], reverse=True)
    top_100 = _top_recommendations(ranked, top_limit)
    approved_shortfall = max(top_limit - len(top_100), 0)
    event_groups = build_event_groups(ranked)
    correlations = build_scan_correlations([item["candidate"] for item in ranked])
    monitor = build_monitoring_instructions(top_100, previous)
    source_matrix = build_agent_source_matrix()
    external_readiness = build_external_data_readiness(
        [item["candidate"] for item in ranked],
        registry=registry,
        decision_at=scan_started_at,
    )
    intelligence = (
        run_intelligence_cycle(
            cycle_type="manual",
            source_mode="live",
            target_count=len(candidates),
            persist=False,
            allow_codex=False,
            queue_codex=False,
            dashboard_payload={"multi_agent": enriched},
        )
        if run_intelligence
        else {"status": "skipped", "summary": {"marketCount": 0}, "marketAnalysisResults": []}
    )

    summary = {
        "schema_version": 1,
        "research_only": True,
        "mode": "paper",
        "scanStartedAt": scan_started_at,
        "scanDate": target_date,
        "currentDayOnly": current_day_only,
        "sourceMode": "live",
        "source": "polymarket-public-gamma",
        "timeSeriesSource": "polymarket-public-clob-prices-history",
        "rawMarketCount": len(raw_markets),
        "candidateOutcomeCount": len(candidates),
        "topLimit": top_limit,
        "topRecommendationCount": len(top_100),
        "topRecommendationTargetMet": approved_shortfall == 0,
        "approvedPaperBetShortfall": approved_shortfall,
        "paperBetCount": multi_agent.metrics["paper_bet_count"],
        "watchlistCount": multi_agent.metrics["watchlist_count"],
        "rejectedCount": multi_agent.metrics["rejected_count"],
        "eventGroupCount": len(event_groups),
        "correlationPairCount": sum(len(row["pairs"]) for row in correlations["categories"]),
        "timeSeries": time_series["summary"],
        "externalSourceStatusCounts": external_readiness["sourceStatusSummary"]["statusCounts"],
        "intelligenceStatus": intelligence.get("status"),
        "intelligenceMarketCount": intelligence.get("summary", {}).get("marketCount", 0),
        "stopReason": stop_reason,
        "pageSummaries": page_summaries,
        "filters": {
            "minLiquidity": min_liquidity,
            "maxSpread": max_spread,
            "excludedReasonCounts": dict(excluded["reasonCounts"]),
        },
        "safety": {
            "walletActions": False,
            "orderExecution": False,
            "credentialStorage": False,
            "realMoneyBetting": False,
        },
    }
    payload = {
        "summary": summary,
        "top100": [_compact_recommendation(item, rank=index + 1) for index, item in enumerate(top_100)],
        "eventGroups": event_groups,
        "correlations": correlations,
        "marketCoverage": build_market_coverage([item["candidate"] for item in ranked], event_groups),
        "monitoring": monitor,
        "timeSeries": time_series,
        "agentSourceMatrix": source_matrix,
        "externalDataReadiness": external_readiness,
        "excluded": excluded,
        "multiAgent": {
            "run_id": multi_agent.run_id,
            "created_at": multi_agent.created_at,
            "source_note": multi_agent.source_note,
            "metrics": multi_agent.metrics,
            "category_stats": multi_agent.category_stats,
            "agent_performance": multi_agent.agent_performance,
        },
        "intelligenceSummary": intelligence.get("summary", {}),
        "artifactPaths": {},
    }

    if persist:
        state_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "rawMarkets": state_dir / "raw_gamma_markets.json",
            "latest": state_dir / "latest_full_scan.json",
            "top100": state_dir / "top_100_paper_recommendations.json",
            "events": state_dir / "event_groups.json",
            "coverage": state_dir / "market_coverage.json",
            "correlations": state_dir / "correlation_tables.json",
            "timeSeries": state_dir / "time_series_samples.json",
            "agentSources": state_dir / "agent_source_matrix.json",
            "externalReadiness": state_dir / "external_data_readiness.json",
            "monitoring": state_dir / "monitoring_instructions.json",
            "intelligence": state_dir / "intelligence_analysis.json",
            "currentDashboard": Path("data/generated/production_state/dashboard_latest.json"),
            "report": Path(report_path),
        }
        _write_json(artifacts["rawMarkets"], raw_markets)
        _write_json(artifacts["top100"], payload["top100"])
        _write_json(artifacts["events"], event_groups)
        _write_json(artifacts["coverage"], payload["marketCoverage"])
        _write_json(artifacts["correlations"], correlations)
        _write_json(artifacts["timeSeries"], time_series)
        _write_json(artifacts["agentSources"], source_matrix)
        _write_json(artifacts["externalReadiness"], external_readiness)
        _write_json(artifacts["monitoring"], monitor)
        _write_json(artifacts["intelligence"], intelligence)
        payload["artifactPaths"] = {key: str(path) for key, path in artifacts.items()}
        _write_markdown_report(artifacts["report"], payload)
        _write_json(artifacts["latest"], payload)
        current_dashboard = _latest_full_scan_dashboard(None)
        if current_dashboard:
            _write_json(artifacts["currentDashboard"], current_dashboard)

    return payload


def scan_gamma_markets(
    client: PolymarketPublicClient,
    *,
    max_pages: int,
    page_size: int,
    scan_date: str,
    current_day_only: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    markets: list[dict[str, Any]] = []
    page_summaries = []
    offset = 0
    stop_reason = "max_pages_reached"
    for page_index in range(max(max_pages, 0)):
        batch = client.fetch_gamma_markets(limit=page_size, offset=offset, active=True, closed=False, order="createdAt")
        if not batch:
            stop_reason = "empty_page"
            break
        today_count = sum(1 for row in batch if str(row.get("createdAt", "")).startswith(scan_date))
        filtered_batch = [row for row in batch if str(row.get("createdAt", "")).startswith(scan_date)] if current_day_only else batch
        markets.extend(filtered_batch)
        page_summaries.append(
            {
                "page": page_index + 1,
                "offset": offset,
                "returned": len(batch),
                "kept": len(filtered_batch),
                "createdOnScanDate": today_count,
                "firstCreatedAt": batch[0].get("createdAt"),
                "lastCreatedAt": batch[-1].get("createdAt"),
            }
        )
        offset += len(batch)
        if len(batch) < min(max(page_size, 1), 100):
            stop_reason = "short_page"
            break
        if current_day_only and today_count == 0:
            stop_reason = "crossed_scan_date_boundary"
            break
    return markets, page_summaries, stop_reason


def build_candidates_from_markets(
    markets: list[dict[str, Any]],
    *,
    scan_started_at: str,
    min_liquidity: float,
    max_spread: float,
) -> tuple[list[MarketCandidate], dict[str, Any]]:
    candidates = []
    exclusions = []
    reason_counts: Counter[str] = Counter()
    for market in markets:
        outcomes = parse_polymarket_list(market.get("outcomes"))
        prices = parse_polymarket_list(market.get("outcomePrices") or market.get("outcome_prices"))
        token_ids = parse_polymarket_list(market.get("clobTokenIds") or market.get("clob_token_ids"))
        if not outcomes:
            _exclude_market(exclusions, reason_counts, market, "missing_outcomes")
            continue
        if not prices:
            _exclude_market(exclusions, reason_counts, market, "missing_outcome_prices")
            continue
        for index, outcome in enumerate(outcomes):
            reasons = _eligibility_reasons(market, prices, token_ids, index, min_liquidity, max_spread)
            if reasons:
                for reason in reasons:
                    reason_counts[reason] += 1
                exclusions.append(_excluded_row(market, reason=",".join(reasons), outcome=str(outcome)))
                continue
            price = _safe_float(prices[index])
            token_id = str(token_ids[index])
            spread = _gamma_spread(market)
            question = str(market.get("question") or market.get("title") or "Polymarket market")
            event = _primary_event(market)
            category = _normalize_category(market, question, event)
            if category is None:
                reason_counts["out_of_scope_category"] += 1
                exclusions.append(_excluded_row(market, reason="out_of_scope_category", outcome=str(outcome)))
                continue
            candidate_id = _candidate_id(market, index, token_id, str(outcome))
            candidates.append(
                MarketCandidate(
                    candidate_id=candidate_id,
                    event_id=_event_id(market, event),
                    category=category,
                    subcategory=_subcategory(market, event),
                    market_title=question,
                    outcome=str(outcome),
                    price=round(price, 4),
                    spread=spread,
                    liquidity=_liquidity(market),
                    volume_24h=_volume_24h(market),
                    end_time=str(market.get("endDate") or market.get("end_date") or event.get("endDate") or ""),
                    source="polymarket-full-scan-gamma",
                    source_url=_polymarket_url(market, event),
                    actors=_actors_from_question(question),
                    news_items=_metadata_news(market, event, scan_started_at),
                    stats=_stats(market, price),
                    odds_history=_gamma_history(market, price, index, scan_started_at),
                    resolution_notes=str(market.get("resolutionSource") or event.get("resolutionSource") or market.get("description") or "")[:280],
                    resolved_outcome=None,
                    published_at=str(market.get("createdAt") or event.get("createdAt") or ""),
                    updated_at=str(market.get("updatedAt") or event.get("updatedAt") or ""),
                    token_id=token_id,
                )
            )
    return candidates, {"reasonCounts": reason_counts, "examples": exclusions[:200], "totalExcludedOutcomes": len(exclusions)}


def enrich_candidates_with_clob_history(
    candidates: list[MarketCandidate],
    client: PolymarketPublicClient,
    *,
    scan_started_at: str,
    sample_limit: int,
    history_hours: int,
    fidelity: int,
) -> tuple[list[MarketCandidate], dict[str, Any]]:
    """Attach observed CLOB price history to a bounded, high-value sample.

    The full scan can contain thousands of outcome tokens, so this intentionally
    samples by liquidity/volume instead of making an unbounded request fan-out.
    """
    if sample_limit <= 0 or not candidates:
        return candidates, _time_series_payload(
            summary={
                "requestedSampleLimit": max(sample_limit, 0),
                "sampledCandidateCount": 0,
                "observedHistoryCount": 0,
                "fallbackHistoryCount": len(candidates),
                "historyHours": history_hours,
                "fidelityMinutes": fidelity,
                "status": "skipped",
            },
            samples=[],
            errors=[],
        )

    end_dt = _parse_iso(scan_started_at) or now_utc()
    start_ts = int((end_dt - timedelta(hours=max(history_hours, 1))).timestamp())
    end_ts = int(end_dt.timestamp())
    selected = _history_sample_indices(candidates, sample_limit)
    enriched = list(candidates)
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    observed_count = 0

    for index in selected:
        candidate = candidates[index]
        token_id = candidate.token_id
        if not token_id:
            errors.append({"candidate_id": candidate.candidate_id, "reason": "missing_token_id"})
            continue
        try:
            payload = client.fetch_price_history(token_id, start_ts=start_ts, end_ts=end_ts, fidelity=fidelity)
        except PolymarketClientError as exc:
            errors.append({"candidate_id": candidate.candidate_id, "token_id": token_id, "reason": str(exc)[:180]})
            continue
        history = _clob_history_points(payload, fallback_price=candidate.price, scan_started_at=scan_started_at)
        if len(history) < 2:
            errors.append({"candidate_id": candidate.candidate_id, "token_id": token_id, "reason": "insufficient_history_points"})
            continue
        stats = dict(candidate.stats)
        stats.update(_history_stats(history, candidate.price))
        enriched[index] = replace(candidate, odds_history=history, stats=stats)
        observed_count += 1
        samples.append(
            {
                "candidate_id": candidate.candidate_id,
                "event_id": candidate.event_id,
                "category": candidate.category,
                "subcategory": candidate.subcategory,
                "market_title": candidate.market_title,
                "outcome": candidate.outcome,
                "token_id": token_id,
                "point_count": len(history),
                "first_time": history[0]["time"],
                "last_time": history[-1]["time"],
                "first_price": history[0]["price"],
                "last_price": history[-1]["price"],
                "min_price": min(float(point["price"]) for point in history),
                "max_price": max(float(point["price"]) for point in history),
            }
        )

    summary = {
        "requestedSampleLimit": sample_limit,
        "sampledCandidateCount": len(selected),
        "observedHistoryCount": observed_count,
        "fallbackHistoryCount": max(len(candidates) - observed_count, 0),
        "historyHours": history_hours,
        "fidelityMinutes": fidelity,
        "startTs": start_ts,
        "endTs": end_ts,
        "errorCount": len(errors),
        "status": "success" if observed_count else "fallback_only",
    }
    return enriched, _time_series_payload(summary=summary, samples=samples, errors=errors[:200])


def _time_series_payload(*, summary: dict[str, Any], samples: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "research_only": True,
        "source": "polymarket-public-clob-prices-history",
        "summary": summary,
        "samples": samples,
        "errors": errors,
    }


def _history_sample_indices(candidates: list[MarketCandidate], sample_limit: int) -> list[int]:
    by_category: dict[str, list[tuple[int, MarketCandidate]]] = {category: [] for category in ACTIVE_CATEGORIES}
    for index, candidate in enumerate(candidates):
        by_category.setdefault(candidate.category, []).append((index, candidate))
    selected: list[int] = []
    seen_tokens: set[str] = set()
    per_category_floor = max(5, sample_limit // max(len(ACTIVE_CATEGORIES), 1) // 2)
    for rows in by_category.values():
        for index, candidate in sorted(rows, key=lambda row: _history_priority(row[1]), reverse=True)[:per_category_floor]:
            if candidate.token_id and candidate.token_id not in seen_tokens and len(selected) < sample_limit:
                selected.append(index)
                seen_tokens.add(candidate.token_id)
    for index, candidate in sorted(enumerate(candidates), key=lambda row: _history_priority(row[1]), reverse=True):
        if len(selected) >= sample_limit:
            break
        if candidate.token_id and candidate.token_id not in seen_tokens:
            selected.append(index)
            seen_tokens.add(candidate.token_id)
    return selected


def _history_priority(candidate: MarketCandidate) -> tuple[float, float, float, float]:
    near_binary_center = 1.0 - abs(candidate.price - 0.5)
    return (candidate.liquidity, candidate.volume_24h, near_binary_center, -candidate.spread)


def _clob_history_points(payload: dict[str, Any], *, fallback_price: float, scan_started_at: str) -> list[dict[str, Any]]:
    raw_history = payload.get("history") or payload.get("prices") or payload.get("data") or []
    points = []
    if isinstance(raw_history, list):
        for row in raw_history:
            if not isinstance(row, dict):
                continue
            raw_price = row.get("p", row.get("price", row.get("value")))
            raw_time = row.get("t", row.get("time", row.get("timestamp")))
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if not 0.0 <= price <= 1.0:
                continue
            points.append(
                {
                    "time": _history_time(raw_time),
                    "price": round(price, 4),
                    "source": "clob-prices-history",
                }
            )
    points = sorted(points, key=lambda point: point["time"])
    points = _dedupe_history(points)
    if points and abs(float(points[-1]["price"]) - fallback_price) > 0.0005:
        points.append({"time": scan_started_at, "price": round(fallback_price, 4), "source": "gamma-current"})
    return _downsample_history(points, max_points=96)


def _history_time(value: Any) -> str:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    text = str(value or "").strip()
    if text:
        return text
    return iso_z(now_utc())


def _dedupe_history(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for point in points:
        key = str(point["time"])
        if key in seen:
            deduped[-1] = point
            continue
        seen.add(key)
        deduped.append(point)
    return deduped


def _downsample_history(points: list[dict[str, Any]], *, max_points: int) -> list[dict[str, Any]]:
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    sampled = [points[min(int(index * step), len(points) - 1)] for index in range(max_points - 1)]
    sampled.append(points[-1])
    return _dedupe_history(sampled)


def _history_stats(history: list[dict[str, Any]], current_price: float) -> dict[str, float]:
    prices = [float(point["price"]) for point in history]
    return {
        "observed_history_points": float(len(history)),
        "observed_history_first_price": round(prices[0], 4),
        "observed_history_latest_price": round(prices[-1], 4),
        "observed_history_min_price": round(min(prices), 4),
        "observed_history_max_price": round(max(prices), 4),
        "observed_history_delta": round(prices[-1] - prices[0], 4),
        "observed_history_current_gap": round(current_price - prices[-1], 4),
    }


def run_candidate_agents(candidates: list[MarketCandidate], *, top_limit: int) -> MultiAgentRun:
    odds_agent = OddsModelingAgent()
    context_agent = MarketContextNewsAgent()
    category_agent = CategoryExpertAgent()
    decision_agent = DecisionBankrollAgent(bankroll=100.0, deployment_budget=100.0, target_bet_count=top_limit)
    evaluation_agent = EvaluationLearningAgent()
    assessments: dict[str, dict[str, AgentAssessment]] = {}
    for candidate in candidates:
        odds = odds_agent.assess(candidate)
        context = context_agent.assess(candidate)
        category = category_agent.assess(candidate, odds, context)
        assessments[candidate.candidate_id] = {"odds": odds, "context": context, "category": category}
    recommendations = decision_agent.build_recommendations(candidates, assessments)
    recommendations.sort(key=lambda item: item["rank_score"], reverse=True)
    _apply_mutually_exclusive_guardrails(recommendations)
    decision_agent.reallocate_paper_budget(recommendations)
    evaluation = evaluation_agent.evaluate(recommendations)
    ranked_paper_bets = [item for item in recommendations if item["decision"] == "PAPER_BET"]
    recommendations_by_date = sorted(
        recommendations,
        key=lambda item: str(item.get("candidate", {}).get("published_at") or item.get("candidate", {}).get("updated_at") or ""),
        reverse=True,
    )
    return MultiAgentRun(
        run_id=f"full-scan-{iso_z(now_utc())}",
        created_at=iso_z(now_utc()),
        mode="paper",
        source_mode="live_full_scan",
        source_note=f"full Gamma scan produced {len(candidates)} eligible outcome candidates; top_limit={top_limit}",
        candidates=[candidate.to_dict() for candidate in candidates],
        recommendations=recommendations_by_date,
        paper_bets=[item for item in recommendations_by_date if item["decision"] == "PAPER_BET"],
        watchlist=[item for item in recommendations_by_date if item["decision"] == "WATCHLIST"],
        rejected=[item for item in recommendations_by_date if item["decision"] == "REJECTED"],
        top_bets=ranked_paper_bets[:top_limit],
        category_stats=_category_stats(recommendations),
        agent_performance=evaluation["agent_performance"],
        metrics=evaluation["metrics"],
        bankroll_curve=evaluation["bankroll_curve"],
        mistakes=evaluation["mistakes"],
    )


def build_event_groups(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in recommendations:
        groups.setdefault(str(item["candidate"]["event_id"]), []).append(item)
    rows = []
    for event_id, items in groups.items():
        ranked = sorted(items, key=lambda row: row["rank_score"], reverse=True)
        first = ranked[0]["candidate"]
        rows.append(
            {
                "event_id": event_id,
                "event_title": _event_title(first),
                "category": first["category"],
                "subcategory": first["subcategory"],
                "market_count": len({item["candidate"]["candidate_id"] for item in items}),
                "sub_bet_count": len(items),
                "paper_bet_count": sum(1 for item in items if item["decision"] == "PAPER_BET"),
                "watchlist_count": sum(1 for item in items if item["decision"] == "WATCHLIST"),
                "best_rank_score": max(float(item["rank_score"]) for item in items),
                "average_expected_value": round(mean([float(item["expected_value"]) for item in items]), 4),
                "total_stake_units": round(sum(float(item["stake_units"]) for item in items), 4),
                "top_sub_bets": [_compact_recommendation(item, rank=index + 1) for index, item in enumerate(ranked[:8])],
            }
        )
    return sorted(rows, key=lambda row: (row["total_stake_units"], row["best_rank_score"]), reverse=True)


def _apply_mutually_exclusive_guardrails(recommendations: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in recommendations:
        candidate = item["candidate"]
        key = (str(candidate.get("event_id")), str(candidate.get("market_title", "")).strip().lower())
        groups.setdefault(key, []).append(item)
    for siblings in groups.values():
        paper_siblings = [item for item in siblings if item["decision"] == "PAPER_BET" and float(item.get("stake_units", 0.0)) > 0.0]
        if len(paper_siblings) <= 1:
            continue
        paper_siblings.sort(key=lambda row: (float(row["rank_score"]), float(row["expected_value"]), float(row["confidence"])), reverse=True)
        kept = paper_siblings[0]["candidate"]["candidate_id"]
        for item in paper_siblings[1:]:
            item["decision"] = "WATCHLIST"
            item["stake_units"] = 0.0
            item["reason"] = f"Watchlist: mutually exclusive sibling {kept} kept the paper stake."
            item.setdefault("failure_conditions", []).append("mutually_exclusive_sibling_has_stronger_rank")


def build_scan_correlations(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    categories = []
    for category in ACTIVE_CATEGORIES:
        rows = [candidate for candidate in candidates if candidate.get("category") == category]
        pairs = _correlation_pairs(rows)[:250]
        categories.append(
            {
                "category": category,
                "marketCount": len(rows),
                "pairs": pairs,
                "topPairs": pairs[:25],
                "sparse": len(pairs) == 0,
            }
        )
    return {"schema_version": 1, "updatedAt": iso_z(now_utc()), "categories": categories}


def build_market_coverage(candidates: list[dict[str, Any]], event_groups: list[dict[str, Any]]) -> dict[str, Any]:
    categories = []
    for category in ACTIVE_CATEGORIES:
        rows = [candidate for candidate in candidates if candidate.get("category") == category]
        subcategories: Counter[str] = Counter(str(candidate.get("subcategory") or "unknown") for candidate in rows)
        source_types: Counter[str] = Counter(
            "observed_clob_history" if _has_observed_history(candidate) else "gamma_snapshot_or_change_fields"
            for candidate in rows
        )
        category_events = [event for event in event_groups if event.get("category") == category]
        categories.append(
            {
                "category": category,
                "candidateOutcomeCount": len(rows),
                "eventGroupCount": len(category_events),
                "subcategories": [
                    {"subcategory": name, "candidateOutcomeCount": count}
                    for name, count in subcategories.most_common(25)
                ],
                "timeSeriesCoverage": dict(source_types),
                "topEvents": [
                    {
                        "event_id": event["event_id"],
                        "event_title": event["event_title"],
                        "sub_bet_count": event["sub_bet_count"],
                        "paper_bet_count": event["paper_bet_count"],
                        "watchlist_count": event["watchlist_count"],
                        "best_rank_score": event["best_rank_score"],
                    }
                    for event in category_events[:15]
                ],
            }
        )
    return {
        "schema_version": 1,
        "updatedAt": iso_z(now_utc()),
        "research_only": True,
        "categories": categories,
    }


def _has_observed_history(candidate: dict[str, Any]) -> bool:
    stats = candidate.get("stats") or {}
    return float(stats.get("observed_history_points") or 0.0) >= 2.0


def build_agent_source_matrix() -> dict[str, Any]:
    registry = SourceRegistry()
    rows = []
    for category in ACTIVE_CATEGORIES:
        sources = registry.for_category(category, include_global=True, include_polymarket=True, allowed_only=False)
        allowed = [source for source in sources if source.allowed_by_default]
        category_allowed = [source for source in allowed if source.category == category]
        global_allowed = [source for source in allowed if source.category == "global"]
        polymarket_allowed = [source for source in allowed if source.category == "polymarket"]
        rows.append(
            {
                "category": category,
                "agents": {
                    "polymarket_ingestion_agent": {
                        "uses": [_source_row(source, "market metadata and current prices") for source in polymarket_allowed],
                        "purpose": "market discovery, metadata, outcomes, prices, liquidity, spread, token ids, CLOB price history",
                    },
                    "time_series_feature_agent": {
                        "uses": [
                            _source_row(source, "observed time-series and market microstructure")
                            for source in polymarket_allowed
                            if source.id in {"polymarket-clob", "polymarket-data-api", "polymarket-gamma"}
                        ],
                        "purpose": "price-history, public activity/trades where available, volatility, drift, and liquidity/spread features",
                    },
                    "external_series_agent": {
                        "uses": [
                            _source_row(source, "category-linked external time-series and entity stats")
                            for source in sources
                            if _external_series_source(source)
                        ],
                        "purpose": (
                            "entity-linked macroeconomic, political, stock, company, and trade time-series; "
                            "registered now, fetched only when public/API access and as-of storage are implemented"
                        ),
                    },
                    "global_news_context_agent": {
                        "uses": [_source_row(source, "global event context and contradiction check") for source in global_allowed],
                        "purpose": "broad public context, official feeds, cross-category event confirmation, contradiction checks",
                    },
                    "category_news_agent": {
                        "uses": [_source_row(source, "category-specific official/statistical evidence") for source in category_allowed],
                        "purpose": "category-specific official/statistical evidence and settlement-source corroboration",
                    },
                    "single_bet_news_agent": {
                        "uses": [
                            _source_row(source, "single-candidate query and evidence attachment")
                            for source in [*polymarket_allowed, *global_allowed, *category_allowed]
                        ],
                        "purpose": "candidate-level query plan attached to each paper decision; requires primary/high sources before strengthening",
                    },
                    "model_ensemble_agent": {
                        "uses": [_source_row(source, "model features and calibration inputs") for source in polymarket_allowed],
                        "purpose": "market-implied probability, observed history, spread, liquidity, volume, correlation and calibration inputs",
                    },
                    "decision_bankroll_agent": {
                        "uses": [],
                        "purpose": "consumes model/news/exposure outputs only; does not fetch or execute anything",
                    },
                },
            }
        )
    return {
        "schema_version": 1,
        "updatedAt": iso_z(now_utc()),
        "research_only": True,
        "registryPath": str(SourceRegistry().path),
        "rows": rows,
    }


def _source_row(source: Any, evidence_role: str) -> dict[str, Any]:
    row = source.to_dict()
    currently_fetched = source.id in {"polymarket-gamma", "polymarket-clob"}
    client_available = source.id == "polymarket-data-api"
    row.update(
        {
            "currently_fetched": currently_fetched,
            "live_fetch": currently_fetched,
            "evidence_role": evidence_role,
            "source_scope": _source_scope(source),
            "adapter_status": _adapter_status(source, currently_fetched, client_available),
            "query_execution": "implemented" if currently_fetched else "planned_or_manual",
        }
    )
    if client_available:
        row["query_execution"] = "client_available_not_wired_into_full_scan"
    return row


def _external_series_source(source: Any) -> bool:
    source_type = str(source.source_type)
    source_id = str(source.id)
    if source.category in {"macro", "macroeconomics", "stocks_trade"} and "api" in source_type:
        return True
    if source.category in {"geopolitics", "politics"} and any(token in source_type for token in ("api", "conflict", "official_site", "feed", "government")):
        return True
    if source.category == "global" and any(token in source_type for token in ("trade", "company")):
        return True
    return source_id in {"global-sec-edgar-companyfacts", "global-wto-timeseries", "global-un-comtrade"}


def _source_scope(source: Any) -> str:
    if source.id in {"polymarket-gamma", "polymarket-clob"}:
        return "implemented_polymarket_market_data"
    if source.id == "polymarket-data-api":
        return "client_available_public_activity"
    if _external_series_source(source):
        return "registered_external_time_series"
    if source.category in {"global", "geopolitics", "politics", "macro", "macroeconomics", "stocks_trade"}:
        return "registered_context_source"
    return "registered_source"


def _adapter_status(source: Any, currently_fetched: bool, client_available: bool) -> str:
    if currently_fetched:
        return "implemented_in_full_scan"
    if client_available:
        return "client_available_not_wired"
    if not source.allowed_by_default:
        return "blocked_until_access_or_license_review"
    if _external_series_source(source):
        return "registered_needs_fetcher_and_asof_storage"
    return "registered_planned_or_manual"


def build_monitoring_instructions(top_recommendations: list[dict[str, Any]], previous: dict[str, Any] | None) -> dict[str, Any]:
    previous_by_id = {
        item.get("candidate_id"): item
        for item in (previous or {}).get("top100", [])
        if item.get("candidate_id")
    }
    rows = []
    for rank, item in enumerate(top_recommendations, start=1):
        candidate = item["candidate"]
        previous_item = previous_by_id.get(candidate["candidate_id"], {})
        previous_price = previous_item.get("market_price")
        price_delta = None if previous_price is None else round(float(candidate["price"]) - float(previous_price), 4)
        rows.append(
            {
                "rank": rank,
                "candidate_id": candidate["candidate_id"],
                "event_id": candidate["event_id"],
                "market_title": candidate["market_title"],
                "outcome": candidate["outcome"],
                "category": candidate["category"],
                "decision": item["decision"],
                "market_price": candidate["price"],
                "forecast_probability": item["blended_probability"],
                "expected_value": item["expected_value"],
                "stake_units": item["stake_units"],
                "price_delta_since_previous_scan": price_delta,
                "monitor_triggers": [
                    "re-rank if market price moves by at least 3 percentage points",
                    "downgrade if spread widens above 25 percentage points or liquidity falls to zero",
                    "recheck official settlement wording before any paper allocation remains active",
                    "attach new Tier 1/Tier 2 source evidence before strengthening a news-driven conclusion",
                    "group exposure with sibling markets from the same event before changing paper stake",
                ],
                "next_run_learning": [
                    "compare current forecast with next observed price and event siblings",
                    "separate odds movement, source/news changes, liquidity/spread changes, and wording risk",
                    "keep pending markets out of supervised model training until resolved outcome is available",
                ],
            }
        )
    return {
        "schema_version": 1,
        "research_only": True,
        "nextRun": "Run this full scan again in the next scheduled paper round or after the collector has fresh snapshots.",
        "rounds": ["06:00_morning", "12:00_midday", "18:00_evening", "22:00_late"],
        "rows": rows,
    }


def _top_recommendations(recommendations: list[dict[str, Any]], top_limit: int) -> list[dict[str, Any]]:
    selected = []
    seen: set[str] = set()
    approved_paper_bets = [
        item for item in recommendations if item["decision"] == "PAPER_BET" and float(item.get("stake_units", 0.0)) > 0.0
    ]
    for item in approved_paper_bets:
        candidate_id = str(item.get("candidate", {}).get("candidate_id", ""))
        if candidate_id in seen:
            continue
        selected.append(item)
        seen.add(candidate_id)
        if len(selected) >= top_limit:
            break
    return selected


def _compact_recommendation(item: dict[str, Any], *, rank: int) -> dict[str, Any]:
    candidate = item["candidate"]
    assessments = item.get("assessments", {})
    return {
        "rank": rank,
        "candidate_id": candidate["candidate_id"],
        "event_id": candidate["event_id"],
        "category": candidate["category"],
        "subcategory": candidate["subcategory"],
        "market_title": candidate["market_title"],
        "outcome": candidate["outcome"],
        "source_url": candidate["source_url"],
        "published_at": candidate.get("published_at"),
        "end_time": candidate.get("end_time"),
        "token_id": candidate.get("token_id"),
        "decision": item["decision"],
        "reason": item["reason"],
        "market_price": candidate["price"],
        "forecast_probability": item["blended_probability"],
        "confidence": item["confidence"],
        "edge": item["edge"],
        "expected_value": item["expected_value"],
        "risk_tier": item["risk_tier"],
        "stake_units": item["stake_units"],
        "rank_score": item["rank_score"],
        "model_probabilities": {
            key: assessment.get("probability")
            for key, assessment in assessments.items()
        },
        "main_drivers": [
            assessments.get("odds_modeling", {}).get("rationale", ""),
            assessments.get("market_context_news", {}).get("rationale", ""),
            assessments.get("category_expert", {}).get("rationale", ""),
        ],
        "failure_conditions": item.get("failure_conditions", [])[:8],
    }


def _eligibility_reasons(
    market: dict[str, Any],
    prices: list[Any],
    token_ids: list[Any],
    index: int,
    min_liquidity: float,
    max_spread: float,
) -> list[str]:
    reasons = []
    if market.get("active") is False:
        reasons.append("inactive")
    if market.get("closed") is True:
        reasons.append("closed")
    if market.get("archived") is True:
        reasons.append("archived")
    if market.get("enableOrderBook") is False:
        reasons.append("orderbook_disabled")
    if market.get("acceptingOrders") is False:
        reasons.append("not_accepting_orders")
    try:
        price = float(prices[index])
    except (IndexError, TypeError, ValueError):
        reasons.append("missing_price_for_outcome")
        price = 0.0
    if not 0.02 <= price <= 0.98:
        reasons.append("price_outside_model_range")
    if index >= len(token_ids) or not str(token_ids[index]).strip():
        reasons.append("missing_token_id")
    liquidity = _liquidity(market)
    if liquidity < min_liquidity:
        reasons.append("below_min_liquidity")
    spread = _gamma_spread(market)
    if spread > max_spread:
        reasons.append("spread_above_threshold")
    return reasons


def _exclude_market(exclusions: list[dict[str, Any]], reason_counts: Counter[str], market: dict[str, Any], reason: str) -> None:
    reason_counts[reason] += 1
    exclusions.append(_excluded_row(market, reason=reason))


def _excluded_row(market: dict[str, Any], *, reason: str, outcome: str | None = None) -> dict[str, Any]:
    return {
        "reason": reason,
        "market_id": market.get("id"),
        "condition_id": market.get("conditionId"),
        "question": market.get("question"),
        "outcome": outcome,
        "createdAt": market.get("createdAt"),
        "liquidity": _liquidity(market),
        "spread": _gamma_spread(market),
    }


def _candidate_id(market: dict[str, Any], outcome_index: int, token_id: str, outcome: str) -> str:
    slug = str(market.get("slug") or market.get("marketSlug") or market.get("id") or "market")
    digest = hashlib.sha1(f"{slug}:{token_id}:{outcome}".encode("utf-8")).hexdigest()[:10]
    return f"full-{slug}-{outcome_index}-{digest}"


def _primary_event(market: dict[str, Any]) -> dict[str, Any]:
    events = market.get("events")
    if isinstance(events, list) and events and isinstance(events[0], dict):
        return events[0]
    return {}


def _event_id(market: dict[str, Any], event: dict[str, Any]) -> str:
    return str(event.get("id") or event.get("slug") or market.get("conditionId") or market.get("id") or "unknown-event")


def _event_title(candidate: dict[str, Any]) -> str:
    return f"{candidate.get('category')} / {candidate.get('subcategory')} / {candidate.get('event_id')}"


def _subcategory(market: dict[str, Any], event: dict[str, Any]) -> str:
    series = event.get("series")
    if isinstance(series, list) and series and isinstance(series[0], dict):
        return str(series[0].get("title") or series[0].get("slug") or "polymarket-series")
    return str(market.get("groupItemTitle") or market.get("marketType") or event.get("title") or "polymarket")


def _normalize_category(market: dict[str, Any], question: str, event: dict[str, Any]) -> str | None:
    series = event.get("series")
    series_text = ""
    if isinstance(series, list):
        series_text = " ".join(str(row.get("title") or row.get("slug") or "") for row in series if isinstance(row, dict))
    raw = " ".join(
        [
            str(market.get("category") or ""),
            str(market.get("tags") or ""),
            str(event.get("title") or ""),
            series_text,
            question,
        ]
    ).lower()
    if normalized := normalize_category_id(str(market.get("category") or "")):
        return normalized
    words = set(re.findall(r"[a-z0-9]+", raw))
    phrases = {
        "league of legends",
        "counter strike",
        "counter-strike",
        "j league",
        "j2 league",
        "premier league",
        "champions league",
        "t20 blast",
        "world cup",
        "grand slam",
        "pro a",
    }
    sports_words = {
        "nba",
        "wnba",
        "nfl",
        "mlb",
        "nhl",
        "ncaa",
        "sports",
        "soccer",
        "football",
        "tennis",
        "atp",
        "wta",
        "itf",
        "ufc",
        "mma",
        "cricket",
        "rugby",
        "basketball",
        "bbl",
        "lnb",
        "bsl",
        "euroleague",
        "eurocup",
        "esports",
        "dota",
        "valorant",
        "cs2",
        "fifa",
    }
    weather_words = {
        "weather",
        "hurricane",
        "temperature",
        "rain",
        "snow",
        "storm",
        "wind",
        "precipitation",
        "heat",
        "cold",
        "wildfire",
    }
    crypto_words = {
        "crypto",
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "solana",
        "sol",
        "xrp",
        "doge",
        "dogecoin",
        "bnb",
        "hyperliquid",
        "hype",
        "litecoin",
        "ltc",
        "cardano",
        "ada",
        "chainlink",
        "link",
        "sui",
        "tron",
        "trx",
    }
    macro_words = {
        "fed",
        "inflation",
        "economy",
        "economic",
        "finance",
        "macro",
        "cpi",
        "jobs",
        "treasury",
        "gdp",
        "rates",
        "spy",
        "wti",
        "oil",
        "gold",
        "aapl",
        "msft",
        "tsla",
        "meta",
        "amzn",
        "nvda",
        "googl",
        "google",
        "alphabet",
    }
    stocks_trade_words = {
        "stock",
        "stocks",
        "equity",
        "equities",
        "shares",
        "spy",
        "s&p",
        "sp500",
        "nasdaq",
        "dow",
        "sec",
        "filing",
        "earnings",
        "aapl",
        "msft",
        "tsla",
        "meta",
        "amzn",
        "nvda",
        "googl",
        "google",
        "alphabet",
        "trade",
        "tariff",
        "tariffs",
        "wto",
        "customs",
        "imports",
        "exports",
    }
    politics_words = {
        "election",
        "elections",
        "politic",
        "politics",
        "geopolitic",
        "geopolitics",
        "war",
        "ceasefire",
        "sanctions",
        "ukraine",
        "israel",
        "china",
        "trump",
        "biden",
        "nato",
        "congress",
    }
    if words & crypto_words:
        return None
    if words & sports_words or any(phrase in raw for phrase in phrases):
        return None
    if words & weather_words:
        return None
    if words & stocks_trade_words or "s&p 500" in raw:
        return "stocks_trade"
    if words & macro_words or "treasury yield" in raw:
        return "macroeconomics"
    if words & politics_words:
        return "politics"
    return None


def _polymarket_url(market: dict[str, Any], event: dict[str, Any]) -> str:
    slug = event.get("slug") or market.get("slug") or market.get("marketSlug")
    return f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"


def _actors_from_question(question: str) -> list[str]:
    words = [word.strip("?,.():;\"'") for word in question.split()]
    actors = [word for word in words if word[:1].isupper() and len(word) > 2]
    return actors[:8] or ["Market participants"]


def _metadata_news(market: dict[str, Any], event: dict[str, Any], fetched_at: str) -> list[dict[str, Any]]:
    description = str(market.get("description") or event.get("description") or market.get("question") or "Market metadata reviewed")
    source = str(market.get("resolutionSource") or event.get("resolutionSource") or "polymarket-market-metadata")
    return [
        {
            "time": str(market.get("updatedAt") or event.get("updatedAt") or fetched_at),
            "source": "polymarket-market-metadata",
            "headline": description[:220],
            "impact": 0.0,
            "credibility": 0.55,
        },
        {
            "time": fetched_at,
            "source": source,
            "headline": f"Resolution source reviewed: {source}"[:220],
            "impact": 0.0,
            "credibility": 0.62 if source.startswith("http") else 0.45,
        },
    ]


def _stats(market: dict[str, Any], price: float) -> dict[str, float]:
    description = str(market.get("description") or "")
    return {
        "actor_strength": round(clamp((price - 0.5) * 2.0, -1.0, 1.0), 4),
        "source_depth": round(clamp(len(description) / 1200.0, 0.0, 1.0), 4),
        "liquidity_depth": round(clamp(_liquidity(market) / 100000.0, 0.0, 1.0), 4),
        "volume_shock": round(clamp(_volume_24h(market) / 100000.0, 0.0, 1.0), 4),
        "ambiguity": 0.35 if len(description) < 120 else 0.18,
    }


def _gamma_history(market: dict[str, Any], price: float, index: int, scan_started_at: str) -> list[dict[str, Any]]:
    one_hour = _safe_float(market.get("oneHourPriceChange"))
    one_day = _safe_float(market.get("oneDayPriceChange"))
    one_week = _safe_float(market.get("oneWeekPriceChange"))
    start = str(market.get("createdAt") or scan_started_at)
    mid = str(market.get("updatedAt") or scan_started_at)
    wobble = ((index % 5) - 2) / 1000.0
    points = [
        {"time": start, "price": round(clamp(price - one_week - wobble, 0.01, 0.99), 4), "source": "gamma-one-week-change"},
        {"time": start, "price": round(clamp(price - one_day, 0.01, 0.99), 4), "source": "gamma-one-day-change"},
        {"time": mid, "price": round(clamp(price - one_hour, 0.01, 0.99), 4), "source": "gamma-one-hour-change"},
        {"time": scan_started_at, "price": round(clamp(price, 0.01, 0.99), 4), "source": "gamma-current-price"},
    ]
    if len({point["price"] for point in points}) == 1:
        points[0]["price"] = round(clamp(price - wobble, 0.01, 0.99), 4)
    return points


def _liquidity(market: dict[str, Any]) -> float:
    return _safe_float(market.get("liquidityNum") or market.get("liquidityClob") or market.get("liquidity") or 0.0)


def _volume_24h(market: dict[str, Any]) -> float:
    return _safe_float(market.get("volume24hr") or market.get("volume24hrClob") or market.get("volume") or 0.0)


def _gamma_spread(market: dict[str, Any]) -> float:
    spread = _safe_float(market.get("spread"), default=-1.0)
    if spread >= 0:
        return round(spread, 4)
    bid = _safe_float(market.get("bestBid"), default=-1.0)
    ask = _safe_float(market.get("bestAsk"), default=-1.0)
    if ask >= bid >= 0:
        return round(max(ask - bid, 0.0), 4)
    return 1.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _category_stats(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for category in ACTIVE_CATEGORIES:
        group = [item for item in recommendations if item["candidate"]["category"] == category]
        if not group:
            continue
        bets = [item for item in group if item["decision"] == "PAPER_BET" and float(item["stake_units"]) > 0.0]
        rows.append(
            {
                "category": category,
                "candidate_count": len(group),
                "paper_bet_count": len(bets),
                "watchlist_count": sum(1 for item in group if item["decision"] == "WATCHLIST"),
                "rejected_count": sum(1 for item in group if item["decision"] == "REJECTED"),
                "win_rate": 0.0,
                "total_staked_units": round(sum(float(item["stake_units"]) for item in bets), 4),
                "pnl_units": 0.0,
                "average_ev": round(mean([item["expected_value"] for item in group]), 4),
                "average_spread": round(mean([item["candidate"]["spread"] for item in group]), 4),
                "average_decimal_odds": round(mean([item["candidate"]["decimal_odds"] for item in group]), 4),
                "top_pick_ids": [item["candidate"]["candidate_id"] for item in bets[:3]],
            }
        )
    return rows


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# Polymarket Full-Scan Top Approved Paper Bets",
        "",
        f"Generated: {summary['scanStartedAt']}",
        "",
        "## Guardrails",
        "",
        "- Research-only and paper-only.",
        "- No wallet, no credential storage, no order posting, and no real-money execution.",
        "",
        "## Scan Summary",
        "",
        f"- Raw markets scanned: {summary['rawMarketCount']}",
        f"- Eligible outcome candidates: {summary['candidateOutcomeCount']}",
        f"- Event groups: {summary['eventGroupCount']}",
        f"- Approved paper-bet recommendations: {summary['topRecommendationCount']} / {summary['topLimit']}",
        f"- Approval target met: {'yes' if summary['topRecommendationTargetMet'] else 'no'}",
        f"- Approved paper-bet shortfall: {summary['approvedPaperBetShortfall']}",
        f"- Paper-bet decisions with stake: {summary['paperBetCount']}",
        f"- CLOB histories observed: {summary['timeSeries']['observedHistoryCount']} / {summary['timeSeries']['sampledCandidateCount']} sampled",
        f"- Gamma-derived fallback histories: {summary['timeSeries']['fallbackHistoryCount']}",
        f"- Intelligence status: {summary['intelligenceStatus']} across {summary['intelligenceMarketCount']} markets",
        f"- Stop reason: {summary['stopReason']}",
        "",
        "## Market Coverage",
        "",
        "| Category | Outcomes | Event groups | Top subcategories | Time-series coverage |",
        "|---|---:|---:|---|---|",
    ]
    for category in payload.get("marketCoverage", {}).get("categories", []):
        subcats = ", ".join(
            f"{row['subcategory']} ({row['candidateOutcomeCount']})"
            for row in category.get("subcategories", [])[:4]
        )
        coverage = ", ".join(
            f"{key}: {value}"
            for key, value in category.get("timeSeriesCoverage", {}).items()
        )
        lines.append(
            "| "
            f"{category['category']} | {category['candidateOutcomeCount']} | {category['eventGroupCount']} | "
            f"{subcats or '-'} | {coverage or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Agent Source Matrix",
            "",
            "| Category | Currently fetched | Planned/context sources |",
            "|---|---|---|",
        ]
    )
    for row in payload.get("agentSourceMatrix", {}).get("rows", []):
        fetched = []
        planned = []
        for agent in row.get("agents", {}).values():
            for source in agent.get("uses", []):
                label = f"{source['id']} ({source['reliability_tier']})"
                if source.get("currently_fetched"):
                    fetched.append(label)
                else:
                    planned.append(label)
        lines.append(f"| {row['category']} | {_unique_join(fetched) or '-'} | {_unique_join(planned) or '-'} |")
    readiness = payload.get("externalDataReadiness", {})
    lines.extend(
        [
            "",
            "## External Data Readiness",
            "",
            "| Category | Candidates | Implemented | Planned/as-of needed | Blocked/access review |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in readiness.get("categoryReadiness", []):
        counts = row.get("sourceStatusCounts", {})
        planned_count = int(counts.get("registered_needs_fetcher_and_asof_storage", 0)) + int(counts.get("client_available_not_wired", 0))
        lines.append(
            "| "
            f"{row['category']} | {row['candidateCount']} | {counts.get('implemented', 0)} | "
            f"{planned_count} | {counts.get('blocked_until_access_or_license_review', 0)} |"
    )
    entities = readiness.get("detectedEntities", {})
    country_terms = ", ".join(f"{row['name']} ({row['count']})" for row in entities.get("countries", [])[:12])
    political_terms = ", ".join(f"{row['name']} ({row['count']})" for row in entities.get("politicalTrends", [])[:12])
    macro_terms = ", ".join(f"{row['name']} ({row['count']})" for row in entities.get("macroTrends", [])[:12])
    company_terms = ", ".join(f"{row['name']} ({row['count']})" for row in entities.get("companiesAndCommodities", [])[:12])
    trade_terms = ", ".join(f"{row['name']} ({row['count']})" for row in entities.get("tradeSignals", [])[:12])
    lines.extend(
        [
            "",
            f"- Country/political entities detected: {country_terms or '-'}",
            f"- Political trends detected: {political_terms or '-'}",
            f"- Macro trends detected: {macro_terms or '-'}",
            f"- Companies/commodities detected: {company_terms or '-'}",
            f"- Trade signals detected: {trade_terms or '-'}",
            "- Modeling rule: same-event/sibling correlations are exposure constraints, not causal instruments.",
            "- External source rule: no registered source strengthens a paper forecast until fetched with source id, URL, and as-of timestamps.",
        ]
    )
    lines.extend(
        [
        "",
        "## Top Approved Paper Bets",
        "",
        "| Rank | Decision | Category | Market / Outcome | Forecast | Price | EV | Confidence | Stake | Why |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in payload["top100"]:
        lines.append(
            "| "
            f"{row['rank']} | {row['decision']} | {row['category']} | {row['market_title']} / {row['outcome']} | "
            f"{row['forecast_probability']:.1%} | {row['market_price']:.1%} | {row['expected_value']:.1%} | "
            f"{row['confidence']:.1%} | {row['stake_units']:.2f} | {row['reason']} |"
        )
    lines.extend(
        [
            "",
            "## Next Monitoring Round",
            "",
            "- Re-run the full scan in the next morning/evening paper round.",
            "- Re-rank when price moves by at least 3 percentage points.",
            "- Downgrade markets with zero liquidity, wide spread, missing source evidence, or ambiguous settlement wording.",
            "- Do not train supervised models on pending live markets until resolution labels are known.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unique_join(values: list[str]) -> str:
    seen: set[str] = set()
    rows = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        rows.append(value)
    return ", ".join(rows[:8])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a public read-only Polymarket full scan and top-100 paper ranking")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--top-limit", type=int, default=100)
    parser.add_argument("--scan-date", default=None)
    parser.add_argument("--all-active", action="store_true", help="Do not stop/filter by current UTC date")
    parser.add_argument("--min-liquidity", type=float, default=1.0)
    parser.add_argument("--max-spread", type=float, default=0.25)
    parser.add_argument("--history-sample-limit", type=int, default=200)
    parser.add_argument("--history-hours", type=int, default=24)
    parser.add_argument("--history-fidelity", type=int, default=60)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--no-intelligence", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = run_full_scan(
            max_pages=args.max_pages,
            page_size=args.page_size,
            top_limit=args.top_limit,
            scan_date=args.scan_date,
            current_day_only=not args.all_active,
            min_liquidity=args.min_liquidity,
            max_spread=args.max_spread,
            history_sample_limit=args.history_sample_limit,
            history_hours=args.history_hours,
            history_fidelity=args.history_fidelity,
            persist=not args.no_persist,
            run_intelligence=not args.no_intelligence,
        )
    except PolymarketClientError as exc:
        print(json.dumps({"ok": False, "research_only": True, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **payload["summary"], "artifactPaths": payload.get("artifactPaths", {})}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
