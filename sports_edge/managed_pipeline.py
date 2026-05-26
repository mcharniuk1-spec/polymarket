from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from .agents import ACTIVE_CATEGORIES
from .dashboard_data import build_dashboard_payload
from .intelligence import run_intelligence_cycle
from .odds_math import clamp
from .state_store import JsonStateStore, default_store


RUN_HISTORY_KEY = "run_history.json"
AGENT_STATE_KEY = "agent_decisions.json"
MODEL_STATE_KEY = "model_state.json"
CORRELATION_KEY = "correlation_matrices.json"
LATEST_INTELLIGENCE_KEY = "latest_intelligence.json"
LATEST_DASHBOARD_KEY = "dashboard_latest.json"

QUESTION_ARCHETYPES: dict[str, list[dict[str, Any]]] = {
    "sports": [
        {"id": "sports_game_winner", "label": "Daily game winner", "keywords": ["beat", "winner", "fixture"]},
        {"id": "sports_threshold", "label": "Daily team/player threshold", "keywords": ["threshold", "points", "player", "team"]},
        {"id": "sports_advancement", "label": "Daily standings/advancement", "keywords": ["advance", "standings", "league"]},
    ],
    "geopolitics": [
        {"id": "geopolitics_ceasefire", "label": "Ceasefire/escalation", "keywords": ["ceasefire", "escalation", "breakthrough"]},
        {"id": "geopolitics_election_legal", "label": "Election/legal deadline", "keywords": ["election", "poll", "legal", "deadline"]},
        {"id": "geopolitics_policy", "label": "Sanctions/policy action", "keywords": ["sanctions", "policy", "diplomacy"]},
    ],
    "crypto": [
        {"id": "crypto_btc_threshold", "label": "BTC threshold", "keywords": ["bitcoin", "btc"]},
        {"id": "crypto_major_token", "label": "ETH/SOL/token threshold", "keywords": ["ethereum", "solana", "token"]},
        {"id": "crypto_flow_regulatory", "label": "ETF/volume/regulatory", "keywords": ["etf", "volume", "sec", "policy"]},
    ],
    "macro": [
        {"id": "macro_rates_yields", "label": "Rates/yields", "keywords": ["fed", "rates", "yields", "treasury"]},
        {"id": "macro_inflation_jobs", "label": "Inflation/jobs/oil/gold", "keywords": ["cpi", "inflation", "unemployment", "oil", "gold"]},
        {"id": "macro_release", "label": "Scheduled economic release", "keywords": ["release", "consensus", "window"]},
    ],
    "weather": [
        {"id": "weather_temperature", "label": "Temperature threshold", "keywords": ["temperature", "heat", "cold"]},
        {"id": "weather_precip_wind", "label": "Precipitation/wind/hurricane", "keywords": ["rainfall", "snowfall", "wind", "hurricane"]},
        {"id": "weather_alert", "label": "Official alert/disaster", "keywords": ["alert", "wildfire", "disaster"]},
    ],
    "culture": [
        {"id": "culture_box_streaming", "label": "Box office/streaming", "keywords": ["box office", "streaming"]},
        {"id": "culture_awards_event", "label": "Awards/event", "keywords": ["awards", "event"]},
        {"id": "culture_tech_social", "label": "Tech/social milestone", "keywords": ["tech", "launch", "social"]},
    ],
}

FEATURE_KEYS = (
    "bias",
    "price",
    "spread",
    "liquidity_depth",
    "volume_depth",
    "price_delta",
    "volatility",
    "source_depth",
    "ambiguity",
    "expected_value",
    "agent_confidence",
)


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_managed_cycle(
    *,
    cycle_type: str = "scheduled_15m",
    source_mode: str = "live",
    target_count: int = 300,
    global_review: bool = False,
    store: JsonStateStore | None = None,
) -> dict[str, Any]:
    state_store = store or default_store()
    dashboard_payload = build_dashboard_payload(source_mode=source_mode, target_count=target_count, use_cache=False)
    source_note = dashboard_payload.get("multi_agent", {}).get("source_note", "")
    live_data_confirmed = source_mode == "live" and "fixture fallback" not in source_note.lower() and "bundled deterministic" not in source_note.lower()
    intelligence = run_intelligence_cycle(
        cycle_type=cycle_type,
        source_mode=source_mode,
        target_count=target_count,
        persist=False,
        allow_codex=False,
        queue_codex=True,
        dashboard_payload=dashboard_payload,
    )
    _attach_public_lifecycle_times(intelligence, dashboard_payload)
    previous_history = state_store.read_json(RUN_HISTORY_KEY, {"runs": []})
    previous_runs = previous_history.get("runs", []) if isinstance(previous_history, dict) else []
    previous_id = previous_runs[-1]["id"] if previous_runs else None
    snapshot = {
        "id": intelligence["id"],
        "createdAt": intelligence["createdAt"],
        "cycleStartedAt": intelligence["cycleStartedAt"],
        "cycleType": cycle_type,
        "sourceMode": source_mode,
        "sourceNote": source_note,
        "liveDataConfirmed": live_data_confirmed,
        "targetCount": target_count,
        "globalReview": global_review,
        "previousRunId": previous_id,
        "status": intelligence["status"],
        "dashboard": dashboard_payload,
        "intelligence": intelligence,
    }
    state_store.write_json(f"collection_runs/{intelligence['id']}.json", snapshot)

    run_history = _append_run_history(previous_runs, snapshot)
    history_write = state_store.write_json(RUN_HISTORY_KEY, {"schema_version": 1, "runs": run_history})
    current_snapshots = {snapshot["id"]: snapshot}
    agent_report = run_agent_replay(store=state_store, extra_snapshots=current_snapshots, run_history=run_history)
    ml_report = run_ml_update(store=state_store, global_review=global_review, extra_snapshots=current_snapshots, run_history=run_history)
    intelligence["chronology"] = {
        "previousRunId": previous_id,
        "currentRunId": intelligence["id"],
        "runIndex": len(run_history),
        "processedAgentRuns": agent_report["processedRunCount"],
        "gapCount": len(_run_gaps(run_history)),
        "storage": history_write,
    }
    intelligence["modelState"] = ml_report["modelState"]
    intelligence["correlations"] = ml_report["correlations"]
    _attach_multi_model_forecasts(intelligence, dashboard_payload, ml_report)
    state_store.write_json(LATEST_INTELLIGENCE_KEY, intelligence)
    state_store.write_json(LATEST_DASHBOARD_KEY, dashboard_payload)
    return {
        "ok": True,
        "research_only": True,
        "refreshed_at": iso_now(),
        "id": intelligence["id"],
        "previous_run_id": previous_id,
        "run_index": len(run_history),
        "sourceMode": source_mode,
        "source_note": source_note,
        "live_data_confirmed": live_data_confirmed,
        "cycleType": cycle_type,
        "candidate_count": dashboard_payload["multi_agent"]["metrics"]["candidate_count"],
        "paper_bet_count": dashboard_payload["multi_agent"]["metrics"]["paper_bet_count"],
        "intelligence_status": intelligence["status"],
        "intelligence_market_count": intelligence["summary"]["marketCount"],
        "agent_processed_run_count": agent_report["processedRunCount"],
        "agent_decision_count": agent_report["decisionCount"],
        "model_update_count": ml_report["updatedModelCount"],
        "correlation_rows": ml_report["correlationRowCount"],
        "storage_mode": history_write.get("storageMode"),
        "storage_durable": history_write.get("durable"),
        "codex_queue_status": intelligence.get("codexQueue", {}).get("status"),
        "codex_queue_pending_count": intelligence.get("codexQueue", {}).get("pendingCount"),
    }


def _attach_public_lifecycle_times(intelligence: dict[str, Any], dashboard_payload: dict[str, Any]) -> None:
    gathered_at = intelligence.get("cycleStartedAt") or intelligence.get("createdAt") or iso_now()
    estimated_at = intelligence.get("createdAt") or gathered_at
    recommendations = dashboard_payload.get("multi_agent", {}).get("recommendations", [])
    by_candidate_id = {
        item.get("candidate", {}).get("candidate_id"): item
        for item in recommendations
        if item.get("candidate", {}).get("candidate_id")
    }
    for row in intelligence.get("marketAnalysisResults", []):
        candidate_id = row.get("marketSlug") or row.get("marketId")
        item = by_candidate_id.get(candidate_id, {})
        candidate = item.get("candidate", {})
        expected_resolution_at = candidate.get("end_time")
        outcome = (candidate.get("resolved_outcome") or row.get("state") or "").lower()
        resolved_at = expected_resolution_at if outcome in {"win", "loss", "yes", "no"} else None
        if outcome in {"win", "yes"}:
            resolution_status = "resolved_win"
        elif outcome in {"loss", "no"}:
            resolution_status = "resolved_loss"
        elif expected_resolution_at:
            resolution_status = "expected_resolution_pending"
        else:
            resolution_status = "resolution_time_unknown"
        row["lifecycleTimes"] = {
            "gatheredAt": gathered_at,
            "oddsRetrievedAt": gathered_at,
            "estimatedAt": row.get("createdAt") or estimated_at,
            "estimatedDecisionAt": row.get("createdAt") or estimated_at,
            "paperExecutionAt": row.get("createdAt") or estimated_at,
            "paperExecutionMode": "research_only_paper",
            "expectedResolutionAt": expected_resolution_at,
            "resolvedAt": resolved_at,
            "resolutionStatus": resolution_status,
        }
        row["publicLifecycleStatus"] = {
            "publicView": "market_collection_and_model_state_only",
            "hidesBettingProgress": True,
            "showsPaperTimingOnly": True,
        }


def _attach_multi_model_forecasts(
    intelligence: dict[str, Any],
    dashboard_payload: dict[str, Any],
    ml_report: dict[str, Any],
) -> None:
    recommendations = dashboard_payload.get("multi_agent", {}).get("recommendations", [])
    items_by_market = {
        item.get("candidate", {}).get("candidate_id"): item
        for item in recommendations
        if item.get("candidate", {}).get("candidate_id")
    }
    candidates_by_id = {market_id: item["candidate"] for market_id, item in items_by_market.items()}
    correlations_by_market = _correlations_by_market(ml_report.get("correlations", {}), candidates_by_id)
    model_state = ml_report.get("modelState", {})
    models = model_state.get("models", {})
    output_family_health = {"rule": 0, "logistic": 0, "ols": 0, "iv": 0, "tree": 0, "ensemble": 0}

    for row in intelligence.get("marketAnalysisResults", []):
        market_id = row.get("marketSlug") or row.get("marketId")
        item = items_by_market.get(market_id)
        if not item:
            continue
        candidate = item["candidate"]
        features = _features(item)
        question_id = classify_question(candidate.get("category", "culture"), candidate.get("market_title", ""))
        global_model = models.get("global", {"weights": {key: 0.0 for key in FEATURE_KEYS}, "sampleCount": 0})
        category_model = models.get(f"category:{candidate.get('category')}", global_model)
        question_model = models.get(f"question:{question_id}", category_model)
        correlation_signal = _correlated_odds_signal(candidate, correlations_by_market.get(market_id, []), candidates_by_id)
        news_signal = _news_monitor_signal(candidate)
        outputs = _forecast_output_bundle(item, features, global_model, category_model, question_model, news_signal, correlation_signal)
        row["multiModelForecast"] = outputs
        row["newsMonitor"] = news_signal
        row["correlatedOddsInfluence"] = correlation_signal
        row["modelInterpretation"].setdefault("mainDrivers", [])
        row["modelInterpretation"]["mainDrivers"] = (
            [
                f"news monitor {news_signal['score']:+.2f} ({news_signal['stance']})",
                f"correlated odds instrument {correlation_signal['score']:+.2f}",
                f"ensemble probability {outputs['ensembleProbability']:.2%}",
            ]
            + row["modelInterpretation"]["mainDrivers"]
        )[:8]
        row["decisionCommentary"].setdefault("reasoning", [])
        row["decisionCommentary"]["reasoning"] = (
            [
                outputs["expectation"]["why"],
                news_signal["argument"],
                correlation_signal["argument"],
            ]
            + row["decisionCommentary"]["reasoning"]
        )[:8]
        for key in output_family_health:
            output_family_health[key] += 1

    model_state["outputFamilies"] = _output_families(output_family_health["ensemble"])


def _output_families(market_count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": "rule",
            "label": "News-weighted probability rule",
            "purpose": "Transparent probability rule using market price, agent probability, news direction, correlated odds and spread risk.",
            "marketCount": market_count,
        },
        {
            "id": "logistic",
            "label": "Online logistic ML",
            "purpose": "Global/category/question online logistic models trained only on timestamp-valid known labels.",
            "marketCount": market_count,
        },
        {
            "id": "ols",
            "label": "OLS-style linear probability",
            "purpose": "Interpretable linear probability approximation for sensitivity against market price and agent edge.",
            "marketCount": market_count,
        },
        {
            "id": "iv",
            "label": "IV-style correlated odds model",
            "purpose": "Instrumental-variable style adjustment where related odds movement is an instrument, not a hard override.",
            "marketCount": market_count,
        },
        {
            "id": "tree",
            "label": "Deterministic random-tree ensemble",
            "purpose": "Small transparent tree ensemble over news, momentum, spread/liquidity and correlated odds regimes.",
            "marketCount": market_count,
        },
        {
            "id": "ensemble",
            "label": "Final research ensemble",
            "purpose": "Weighted blend of direct odds, ML, OLS-style, IV-style and tree outputs with news-first explanation.",
            "marketCount": market_count,
        },
    ]


def _forecast_output_bundle(
    item: dict[str, Any],
    features: dict[str, float],
    global_model: dict[str, Any],
    category_model: dict[str, Any],
    question_model: dict[str, Any],
    news_signal: dict[str, Any],
    correlation_signal: dict[str, Any],
) -> dict[str, Any]:
    candidate = item["candidate"]
    market_price = _safe_float(candidate.get("price"))
    agent_probability = _safe_float(item.get("blended_probability"), market_price)
    expected_value = _safe_float(item.get("expected_value"))
    spread = _safe_float(candidate.get("spread"))
    price_delta = _safe_float(features.get("price_delta"))
    news_score = _safe_float(news_signal.get("score"))
    corr_score = _safe_float(correlation_signal.get("score"))

    logistic_global = _model_predict(global_model, features)
    logistic_category = _model_predict(category_model, features)
    logistic_question = _model_predict(question_model, features)
    logistic_probability = _weighted_probability(
        [
            (logistic_global, 0.25 if int(global_model.get("sampleCount", 0)) else 0.08),
            (logistic_category, 0.35 if int(category_model.get("sampleCount", 0)) else 0.10),
            (logistic_question, 0.40 if int(question_model.get("sampleCount", 0)) else 0.12),
            (agent_probability, 0.70 if not int(question_model.get("sampleCount", 0)) else 0.15),
        ]
    )
    rule_probability = clamp(
        market_price * 0.50
        + agent_probability * 0.24
        + 0.12 * (0.5 + news_score / 2)
        + 0.08 * (0.5 + corr_score / 2)
        + 0.06 * clamp(0.5 + price_delta * 4, 0.0, 1.0)
        - min(spread * 0.30, 0.05),
        0.01,
        0.99,
    )
    ols_probability = clamp(
        market_price
        + 0.35 * (agent_probability - market_price)
        + 0.22 * expected_value
        + 0.16 * price_delta
        + 0.10 * news_score
        + 0.08 * corr_score
        - 0.20 * spread,
        0.01,
        0.99,
    )
    iv_probability = clamp(
        market_price
        + 0.32 * (agent_probability - market_price)
        + 0.24 * corr_score
        + 0.14 * news_score
        + 0.10 * price_delta
        - 0.10 * spread,
        0.01,
        0.99,
    )
    tree_probability = _tree_ensemble_probability(market_price, agent_probability, expected_value, spread, price_delta, news_score, corr_score, features)
    logistic_weight = 0.16 if any(int(model.get("sampleCount", 0)) for model in (global_model, category_model, question_model)) else 0.08
    ensemble_probability = _weighted_probability(
        [
            (rule_probability, 0.26),
            (logistic_probability, logistic_weight),
            (ols_probability, 0.20),
            (iv_probability, 0.18),
            (tree_probability, 0.18),
            (market_price, 0.10),
        ]
    )
    direction = "up" if ensemble_probability - market_price > 0.025 else "down" if ensemble_probability - market_price < -0.025 else "flat"
    disagreement = max(rule_probability, logistic_probability, ols_probability, iv_probability, tree_probability) - min(
        rule_probability, logistic_probability, ols_probability, iv_probability, tree_probability
    )
    return {
        "schemaVersion": 1,
        "marketPrice": round(market_price, 4),
        "agentProbability": round(agent_probability, 4),
        "ensembleProbability": round(ensemble_probability, 4),
        "expectedDirection": direction,
        "modelDisagreement": round(disagreement, 4),
        "outputs": [
            _model_output("rule", "News-weighted rule", rule_probability, "Market price plus explicit news, correlation, momentum and spread adjustments."),
            _model_output("logistic", "Online logistic ML", logistic_probability, "Global/category/question logistic probabilities, downweighted when labels are sparse."),
            _model_output("ols", "OLS-style linear probability", ols_probability, "Linear probability sensitivity to agent edge, expected value, momentum, news and spread."),
            _model_output("iv", "IV-style correlated odds", iv_probability, "Related market odds movement used as an instrument, not a direct override."),
            _model_output("tree", "Deterministic random-tree ensemble", tree_probability, "Transparent tree votes over news, momentum, liquidity/spread and related-odds regimes."),
        ],
        "expectation": {
            "direction": direction,
            "probability": round(ensemble_probability, 4),
            "why": _expectation_reason(direction, ensemble_probability, market_price, news_signal, correlation_signal, disagreement),
        },
        "rules": {
            "newsWeight": 0.12,
            "correlatedOddsContextWeight": 0.08,
            "directMarketEvidenceDominates": True,
            "relatedOddsNeverOverrideDirectMarket": True,
        },
    }


def _model_output(model_id: str, label: str, probability: float, explanation: str) -> dict[str, Any]:
    return {"id": model_id, "label": label, "probability": round(probability, 4), "explanation": explanation}


def _tree_ensemble_probability(
    market_price: float,
    agent_probability: float,
    expected_value: float,
    spread: float,
    price_delta: float,
    news_score: float,
    corr_score: float,
    features: dict[str, float],
) -> float:
    votes = []
    votes.append(market_price + (0.08 if news_score > 0.25 else -0.08 if news_score < -0.25 else 0.0))
    votes.append(market_price + (0.06 if corr_score > 0.20 else -0.06 if corr_score < -0.20 else 0.0))
    votes.append(market_price + (0.05 if price_delta > 0.015 else -0.05 if price_delta < -0.015 else 0.0))
    votes.append(agent_probability + (0.04 if expected_value > 0.03 else -0.04 if expected_value < -0.03 else 0.0))
    liquidity_depth = _safe_float(features.get("liquidity_depth"))
    volatility = _safe_float(features.get("volatility"))
    risk_penalty = (0.04 if spread > 0.05 else 0.0) + (0.03 if volatility > 0.04 else 0.0) + (0.02 if liquidity_depth < 0.05 else 0.0)
    votes.append((market_price + agent_probability) / 2 - risk_penalty)
    return clamp(mean(clamp(vote, 0.01, 0.99) for vote in votes), 0.01, 0.99)


def _news_monitor_signal(candidate: dict[str, Any]) -> dict[str, Any]:
    rows = candidate.get("news_items", [])
    if not rows:
        return {
            "score": 0.0,
            "stance": "no_attached_news",
            "confidence": 0.0,
            "argument": "News monitor: no attached timestamp-valid news items were available, so the forecast must rely mainly on odds and model context.",
            "topItems": [],
        }
    scored = []
    total_weight = 0.0
    weighted = 0.0
    for row in rows:
        impact = _safe_float(row.get("impact"))
        credibility = clamp(_safe_float(row.get("credibility"), 0.5), 0.0, 1.0)
        weight = 0.25 + 0.75 * credibility
        weighted += clamp(impact * 4.0, -1.0, 1.0) * weight
        total_weight += weight
        scored.append(
            {
                "title": row.get("headline") or row.get("title") or "Untitled news item",
                "source": row.get("source", "unknown"),
                "time": row.get("time"),
                "impact": round(impact, 4),
                "credibility": round(credibility, 4),
            }
        )
    score = clamp(weighted / max(total_weight, 1e-9), -1.0, 1.0)
    stance = "supports_yes" if score > 0.15 else "weakens_yes" if score < -0.15 else "mixed_or_neutral"
    top = sorted(scored, key=lambda row: abs(row["impact"]) * row["credibility"], reverse=True)[:3]
    direction_text = "supports" if score > 0 else "weakens" if score < 0 else "does not materially move"
    return {
        "score": round(score, 4),
        "stance": stance,
        "confidence": round(min(total_weight / max(len(rows), 1), 1.0), 4),
        "argument": f"News monitor: attached news {direction_text} the Yes side with score {score:+.2f}; top item: {top[0]['title'] if top else 'none'}.",
        "topItems": top,
    }


def _correlations_by_market(correlations: dict[str, Any], candidates_by_id: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {market_id: [] for market_id in candidates_by_id}
    for category in correlations.get("categories", []):
        for pair in category.get("pairs", []):
            left = pair.get("left")
            right = pair.get("right")
            if left in rows:
                rows[left].append({**pair, "other": right, "otherTitle": pair.get("rightTitle")})
            if right in rows:
                rows[right].append({**pair, "other": left, "otherTitle": pair.get("leftTitle")})
    for market_id, pairs in rows.items():
        pairs.sort(key=lambda row: abs(_safe_float(row.get("contextWeight"))), reverse=True)
        rows[market_id] = pairs[:12]
    return rows


def _correlated_odds_signal(
    candidate: dict[str, Any],
    related_pairs: list[dict[str, Any]],
    candidates_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    weighted = 0.0
    weight_sum = 0.0
    related = []
    for pair in related_pairs:
        other = candidates_by_id.get(pair.get("other"))
        if not other:
            continue
        deltas = _price_deltas(other.get("odds_history", []))
        other_delta = deltas[-1] if deltas else 0.0
        context_weight = _safe_float(pair.get("contextWeight"))
        weighted += context_weight * clamp(other_delta * 10, -1.0, 1.0)
        weight_sum += abs(context_weight)
        related.append(
            {
                "marketId": pair.get("other"),
                "title": pair.get("otherTitle") or other.get("market_title"),
                "correlation": pair.get("correlation"),
                "contextWeight": round(context_weight, 4),
                "otherProbabilityDelta": round(other_delta, 4),
            }
        )
    score = clamp(weighted / max(weight_sum, 1e-9), -1.0, 1.0) if related else 0.0
    if related:
        argument = f"Correlated odds: {len(related)} related markets reviewed; instrument score {score:+.2f}, led by {related[0]['title']}."
    else:
        argument = "Correlated odds: no reliable overlapping related-market movement was available, so no IV adjustment was applied."
    return {"score": round(score, 4), "argument": argument, "relatedMarkets": related[:6]}


def _expectation_reason(
    direction: str,
    ensemble_probability: float,
    market_price: float,
    news_signal: dict[str, Any],
    correlation_signal: dict[str, Any],
    disagreement: float,
) -> str:
    edge = ensemble_probability - market_price
    return (
        f"Expectation is {direction}: ensemble is {ensemble_probability:.2%} versus market {market_price:.2%} "
        f"(edge {edge:+.2%}); news score {news_signal.get('score', 0.0):+.2f}, "
        f"correlated-odds instrument {correlation_signal.get('score', 0.0):+.2f}, "
        f"model disagreement {disagreement:.2%}."
    )


def _weighted_probability(rows: list[tuple[float, float]]) -> float:
    numerator = sum(clamp(value, 0.001, 0.999) * max(weight, 0.0) for value, weight in rows)
    denominator = sum(max(weight, 0.0) for _, weight in rows)
    return clamp(numerator / max(denominator, 1e-9), 0.001, 0.999)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def run_agent_replay(
    *,
    store: JsonStateStore | None = None,
    extra_snapshots: dict[str, dict[str, Any]] | None = None,
    run_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state_store = store or default_store()
    history = {"runs": run_history} if run_history is not None else state_store.read_json(RUN_HISTORY_KEY, {"runs": []})
    runs = sorted(history.get("runs", []), key=lambda row: row.get("cycleStartedAt") or row.get("createdAt") or "")
    state = state_store.read_json(
        AGENT_STATE_KEY,
        {"schema_version": 1, "checkpointRunId": None, "processedRunIds": [], "betTimelines": {}, "gaps": []},
    )
    processed_ids = set(state.get("processedRunIds", []))
    processed_now = []
    for run in runs:
        run_id = run["id"]
        if run_id in processed_ids:
            continue
        snapshot = (extra_snapshots or {}).get(run_id) or state_store.read_json(f"collection_runs/{run_id}.json")
        if not snapshot:
            continue
        _append_agent_timelines(state, snapshot)
        processed_ids.add(run_id)
        processed_now.append(run_id)
    state["processedRunIds"] = sorted(processed_ids, key=lambda rid: _run_sort_key(runs, rid))
    state["checkpointRunId"] = state["processedRunIds"][-1] if state["processedRunIds"] else None
    state["gaps"] = _run_gaps(runs)
    state["updatedAt"] = iso_now()
    write = state_store.write_json(AGENT_STATE_KEY, state)
    return {
        "status": "ok" if processed_now else "OK - no new chronological runs; dashboard state unchanged",
        "processedRunCount": len(processed_now),
        "processedRunIds": processed_now,
        "decisionCount": sum(len(rows) for rows in state.get("betTimelines", {}).values()),
        "storage": write,
    }


def run_ml_update(
    *,
    store: JsonStateStore | None = None,
    global_review: bool = False,
    extra_snapshots: dict[str, dict[str, Any]] | None = None,
    run_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state_store = store or default_store()
    history = {"runs": run_history} if run_history is not None else state_store.read_json(RUN_HISTORY_KEY, {"runs": []})
    runs = sorted(history.get("runs", []), key=lambda row: row.get("cycleStartedAt") or row.get("createdAt") or "")
    # Rebuild from persisted chronological examples each run so repeated ML automations
    # cannot double-train on the same historical examples.
    models: dict[str, Any] = {}
    examples = []
    for run in runs:
        snapshot = (extra_snapshots or {}).get(run["id"]) or state_store.read_json(f"collection_runs/{run['id']}.json")
        if not snapshot:
            continue
        for item in snapshot.get("dashboard", {}).get("multi_agent", {}).get("recommendations", []):
            examples.append(_example_from_recommendation(run, item))
    updated_models = _update_models(models, examples)
    model_state = {
        "schema_version": 1,
        "updatedAt": iso_now(),
        "globalReview": global_review,
        "featureKeys": FEATURE_KEYS,
        "questionArchetypes": QUESTION_ARCHETYPES,
        "models": updated_models,
        "health": _model_health(updated_models, examples),
        "diagnostics": _model_diagnostics(updated_models, examples),
        "outputFamilies": _output_families(len(examples)),
    }
    correlations = build_correlation_matrices(runs, state_store, extra_snapshots=extra_snapshots)
    model_write = state_store.write_json(MODEL_STATE_KEY, model_state)
    correlation_write = state_store.write_json(CORRELATION_KEY, correlations)
    return {
        "status": "success",
        "updatedModelCount": len(updated_models),
        "correlationRowCount": sum(len(row.get("pairs", [])) for row in correlations.get("categories", [])),
        "modelState": model_state,
        "correlations": correlations,
        "storage": {"model": model_write, "correlation": correlation_write},
    }


def load_run_history(store: JsonStateStore | None = None) -> dict[str, Any]:
    state_store = store or default_store()
    history = state_store.read_json(RUN_HISTORY_KEY, {"schema_version": 1, "runs": []})
    history["gaps"] = _run_gaps(history.get("runs", []))
    return history


def load_model_state(store: JsonStateStore | None = None) -> dict[str, Any]:
    return (store or default_store()).read_json(MODEL_STATE_KEY, _empty_model_state())


def load_correlations(store: JsonStateStore | None = None) -> dict[str, Any]:
    return (store or default_store()).read_json(CORRELATION_KEY, {"schema_version": 1, "categories": []})


def _append_run_history(previous_runs: list[dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    run = {
        "id": snapshot["id"],
        "createdAt": snapshot["createdAt"],
        "cycleStartedAt": snapshot["cycleStartedAt"],
        "cycleType": snapshot["cycleType"],
        "sourceMode": snapshot["sourceMode"],
        "targetCount": snapshot["targetCount"],
        "status": snapshot["status"],
        "previousRunId": snapshot["previousRunId"],
        "globalReview": snapshot["globalReview"],
    }
    by_id = {row["id"]: row for row in previous_runs if "id" in row}
    by_id[run["id"]] = run
    return sorted(by_id.values(), key=lambda row: row.get("cycleStartedAt") or row.get("createdAt") or "")[-384:]


def _append_agent_timelines(state: dict[str, Any], snapshot: dict[str, Any]) -> None:
    run = {
        "id": snapshot["id"],
        "timestamp": snapshot["cycleStartedAt"],
        "sourceMode": snapshot["sourceMode"],
    }
    bet_timelines = state.setdefault("betTimelines", {})
    multi_agent = snapshot.get("dashboard", {}).get("multi_agent", {})
    for item in multi_agent.get("recommendations", []):
        candidate = item["candidate"]
        key = candidate["candidate_id"]
        timestamp = run["timestamp"]
        bet_timelines.setdefault(key, [])
        news = [
            row
            for row in candidate.get("news_items", [])
            if _timestamp_lte(row.get("time"), timestamp)
        ]
        entry = {
            "runId": run["id"],
            "timestamp": timestamp,
            "sourceMode": run["sourceMode"],
            "marketTitle": candidate.get("market_title"),
            "category": candidate.get("category"),
            "ideas": _agent_ideas(item),
            "agentAssessments": item.get("assessments", {}),
            "sourceContext": {"newsItems": news, "excludedFutureNewsCount": len(candidate.get("news_items", [])) - len(news)},
            "paperDecision": {
                "decision": item.get("decision"),
                "reason": item.get("reason"),
                "probability": item.get("blended_probability"),
                "confidence": item.get("confidence"),
                "stakeUnits": item.get("stake_units"),
            },
            "result": item.get("outcome") or "PENDING",
            "learningNote": _learning_note(item),
        }
        if not any(row.get("runId") == run["id"] for row in bet_timelines[key]):
            bet_timelines[key].append(entry)
            bet_timelines[key].sort(key=lambda row: row["timestamp"])


def _agent_ideas(item: dict[str, Any]) -> list[str]:
    candidate = item["candidate"]
    return [
        f"Review {candidate.get('category')} market probability versus current price.",
        f"Check spread {candidate.get('spread')} and liquidity {candidate.get('liquidity')}.",
        f"Keep decision paper-only: {item.get('decision')} because {item.get('reason')}.",
    ]


def _learning_note(item: dict[str, Any]) -> str:
    if item.get("outcome") == "LOSS":
        return "Loss marked for mistake review; separate model error, context error, liquidity, wording, and variance."
    if item.get("outcome") == "WIN":
        return "Win recorded; do not overfit without repeated calibrated evidence."
    return "Outcome pending; no training label is available yet."


def _empty_model_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updatedAt": None,
        "featureKeys": FEATURE_KEYS,
        "questionArchetypes": QUESTION_ARCHETYPES,
        "models": {},
        "health": [],
    }


def _example_from_recommendation(run: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    candidate = item["candidate"]
    features = _features(item)
    question_id = classify_question(candidate.get("category", "culture"), candidate.get("market_title", ""))
    return {
        "runId": run["id"],
        "timestamp": run.get("cycleStartedAt") or run.get("createdAt"),
        "category": candidate.get("category"),
        "questionId": question_id,
        "marketId": candidate.get("candidate_id"),
        "marketTitle": candidate.get("market_title"),
        "marketPrice": candidate.get("price"),
        "blendedProbability": item.get("blended_probability"),
        "features": features,
        "label": candidate.get("resolved_outcome"),
        "prediction": item.get("blended_probability"),
    }


def _features(item: dict[str, Any]) -> dict[str, float]:
    candidate = item["candidate"]
    history = candidate.get("odds_history", [])
    prices = [float(row.get("price", 0.0)) for row in history]
    price_delta = prices[-1] - prices[-2] if len(prices) >= 2 else 0.0
    volatility = math.sqrt(mean([(price - mean(prices)) ** 2 for price in prices])) if len(prices) > 1 else 0.0
    stats = candidate.get("stats", {})
    return {
        "bias": 1.0,
        "price": float(candidate.get("price", 0.0)),
        "spread": float(candidate.get("spread", 0.0)),
        "liquidity_depth": clamp(float(candidate.get("liquidity", 0.0)) / 100000.0, 0.0, 1.0),
        "volume_depth": clamp(float(candidate.get("volume_24h", 0.0)) / 100000.0, 0.0, 1.0),
        "price_delta": price_delta,
        "volatility": volatility,
        "source_depth": float(stats.get("source_depth", 0.0)),
        "ambiguity": float(stats.get("ambiguity", 0.0)),
        "expected_value": float(item.get("expected_value", 0.0)),
        "agent_confidence": float(item.get("confidence", 0.0)),
    }


def classify_question(category: str, title: str) -> str:
    lowered = title.lower()
    for spec in QUESTION_ARCHETYPES.get(category, []):
        if any(keyword in lowered for keyword in spec["keywords"]):
            return spec["id"]
    specs = QUESTION_ARCHETYPES.get(category) or QUESTION_ARCHETYPES["culture"]
    digest = int(hashlib.sha1(lowered.encode("utf-8")).hexdigest()[:4], 16)
    return specs[digest % len(specs)]["id"]


def _update_models(models: dict[str, Any], examples: list[dict[str, Any]]) -> dict[str, Any]:
    updated = deepcopy(models)
    for example in examples:
        scopes = ["global", f"category:{example['category']}", f"question:{example['questionId']}"]
        for scope in scopes:
            model = updated.setdefault(scope, {"weights": {key: 0.0 for key in FEATURE_KEYS}, "sampleCount": 0, "lastUpdatedAt": None})
            label = example.get("label")
            if label is None:
                continue
            prediction = _model_predict(model, example["features"])
            error = float(label) - prediction
            learning_rate = 0.08
            for key in FEATURE_KEYS:
                model["weights"][key] = round(float(model["weights"].get(key, 0.0)) + learning_rate * error * example["features"].get(key, 0.0), 6)
            model["sampleCount"] = int(model.get("sampleCount", 0)) + 1
            model["lastUpdatedAt"] = example["timestamp"]
    for scope, model in updated.items():
        model["scope"] = scope
        model.setdefault("weights", {key: 0.0 for key in FEATURE_KEYS})
        model.setdefault("sampleCount", 0)
        model.setdefault("lastUpdatedAt", None)
    return updated


def _model_predict(model: dict[str, Any], features: dict[str, float]) -> float:
    value = sum(float(model.get("weights", {}).get(key, 0.0)) * features.get(key, 0.0) for key in FEATURE_KEYS)
    return clamp(1.0 / (1.0 + math.exp(-value)), 0.001, 0.999)


def _model_health(models: dict[str, Any], examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for scope, model in sorted(models.items()):
        scoped = _examples_for_scope(scope, examples)
        labeled = [example for example in scoped if example.get("label") is not None]
        brier = None
        if labeled:
            brier = mean((_model_predict(model, row["features"]) - float(row["label"])) ** 2 for row in labeled)
        rows.append(
            {
                "scope": scope,
                "sampleCount": model.get("sampleCount", 0),
                "observedExampleCount": len(scoped),
                "labeledExampleCount": len(labeled),
                "brier": round(brier, 4) if brier is not None else None,
                "lastUpdatedAt": model.get("lastUpdatedAt"),
                "featureCount": len(model.get("weights", {})),
            }
        )
    return rows


def _model_diagnostics(models: dict[str, Any], examples: list[dict[str, Any]]) -> dict[str, Any]:
    global_model = models.get("global", {"weights": {key: 0.0 for key in FEATURE_KEYS}})
    scatter = []
    for example in examples[-500:]:
        category_model = models.get(f"category:{example['category']}", global_model)
        question_model = models.get(f"question:{example['questionId']}", category_model)
        scatter.append(
            {
                "marketId": example["marketId"],
                "marketTitle": example.get("marketTitle"),
                "category": example["category"],
                "questionId": example["questionId"],
                "marketPrice": round(float(example.get("marketPrice") or 0.0), 4),
                "agentProbability": round(float(example.get("blendedProbability") or 0.0), 4),
                "globalMlProbability": round(_model_predict(global_model, example["features"]), 4),
                "categoryMlProbability": round(_model_predict(category_model, example["features"]), 4),
                "questionMlProbability": round(_model_predict(question_model, example["features"]), 4),
                "label": example.get("label"),
                "timestamp": example["timestamp"],
            }
        )
    return {
        "scatter": scatter,
        "featureWeights": [
            {
                "scope": scope,
                "topPositive": _top_weights(model.get("weights", {}), reverse=True),
                "topNegative": _top_weights(model.get("weights", {}), reverse=False),
            }
            for scope, model in sorted(models.items())
        ],
    }


def _top_weights(weights: dict[str, float], *, reverse: bool) -> list[dict[str, Any]]:
    rows = [{"feature": key, "weight": round(float(value), 6)} for key, value in weights.items()]
    rows.sort(key=lambda row: row["weight"], reverse=reverse)
    if reverse:
        return [row for row in rows if row["weight"] > 0][:5]
    return [row for row in rows if row["weight"] < 0][:5]


def _examples_for_scope(scope: str, examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if scope == "global":
        return examples
    if scope.startswith("category:"):
        category = scope.split(":", 1)[1]
        return [row for row in examples if row["category"] == category]
    if scope.startswith("question:"):
        question = scope.split(":", 1)[1]
        return [row for row in examples if row["questionId"] == question]
    return []


def build_correlation_matrices(
    runs: list[dict[str, Any]],
    store: JsonStateStore,
    *,
    extra_snapshots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    category_markets: dict[str, dict[str, dict[str, Any]]] = {category: {} for category in ACTIVE_CATEGORIES}
    for run in runs:
        snapshot = (extra_snapshots or {}).get(run["id"]) or store.read_json(f"collection_runs/{run['id']}.json")
        if not snapshot:
            continue
        for item in snapshot.get("dashboard", {}).get("multi_agent", {}).get("recommendations", []):
            candidate = item["candidate"]
            category = candidate.get("category", "culture")
            market_id = candidate.get("candidate_id")
            category_markets.setdefault(category, {})[market_id] = candidate
    categories = []
    for category, markets in category_markets.items():
        market_rows = list(markets.values())
        pairs = _correlation_pairs(market_rows)
        categories.append(
            {
                "category": category,
                "marketCount": len(markets),
                "pairs": pairs[:200],
                "matrix": _correlation_matrix(market_rows, pairs),
                "sparse": len(pairs) == 0,
            }
        )
    return {"schema_version": 1, "updatedAt": iso_now(), "categories": categories}


def _correlation_matrix(markets: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = []
    for pair in pairs[:80]:
        for key in ("left", "right"):
            if pair[key] not in selected_ids:
                selected_ids.append(pair[key])
            if len(selected_ids) >= 16:
                break
        if len(selected_ids) >= 16:
            break
    if not selected_ids:
        selected_ids = [market.get("candidate_id") for market in markets[:12]]
    labels_by_id = {market.get("candidate_id"): market.get("market_title") for market in markets}
    pair_lookup = {}
    for pair in pairs:
        pair_lookup[(pair["left"], pair["right"])] = pair
        pair_lookup[(pair["right"], pair["left"])] = pair
    cells = []
    for left in selected_ids:
        for right in selected_ids:
            if left == right:
                value = 1.0
                relatedness = 1.0
                context_weight = 1.0
            else:
                pair = pair_lookup.get((left, right), {})
                value = pair.get("correlation")
                relatedness = pair.get("relatedness")
                context_weight = pair.get("contextWeight")
            cells.append(
                {
                    "left": left,
                    "right": right,
                    "correlation": value,
                    "relatedness": relatedness,
                    "contextWeight": context_weight,
                }
            )
    return {
        "markets": [{"id": market_id, "title": labels_by_id.get(market_id, market_id)} for market_id in selected_ids],
        "cells": cells,
    }


def _correlation_pairs(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = []
    for left_index, left in enumerate(markets):
        left_delta = _price_deltas(left.get("odds_history", []))
        for right in markets[left_index + 1 :]:
            right_delta = _price_deltas(right.get("odds_history", []))
            corr = _pearson(left_delta, right_delta)
            if corr is None:
                continue
            related = _relatedness(left, right)
            if related <= 0.0 and abs(corr) < 0.45:
                continue
            pairs.append(
                {
                    "left": left.get("candidate_id"),
                    "right": right.get("candidate_id"),
                    "leftTitle": left.get("market_title"),
                    "rightTitle": right.get("market_title"),
                    "correlation": round(corr, 4),
                    "relatedness": round(related, 4),
                    "sharedEvent": left.get("event_id") == right.get("event_id"),
                    "contextWeight": round(corr * (0.25 + related * 0.35), 4),
                }
            )
    return sorted(pairs, key=lambda row: (abs(row["correlation"]), row["relatedness"]), reverse=True)


def _price_deltas(history: list[dict[str, Any]]) -> list[float]:
    prices = [float(row.get("price", 0.0)) for row in history]
    return [round(prices[index] - prices[index - 1], 6) for index in range(1, len(prices))]


def _pearson(left: list[float], right: list[float]) -> float | None:
    size = min(len(left), len(right))
    if size < 3:
        return None
    xs = left[-size:]
    ys = right[-size:]
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_den == 0 or y_den == 0:
        return None
    return numerator / (x_den * y_den)


def _relatedness(left: dict[str, Any], right: dict[str, Any]) -> float:
    score = 0.0
    if left.get("event_id") == right.get("event_id"):
        score += 0.45
    left_actors = set(left.get("actors", []))
    right_actors = set(right.get("actors", []))
    if left_actors and right_actors:
        score += min(len(left_actors & right_actors) / max(len(left_actors | right_actors), 1), 1.0) * 0.35
    left_words = set(str(left.get("market_title", "")).lower().split())
    right_words = set(str(right.get("market_title", "")).lower().split())
    if left_words and right_words:
        score += min(len(left_words & right_words) / max(len(left_words | right_words), 1), 1.0) * 0.20
    return min(score, 1.0)


def _timestamp_lte(value: str | None, upper: str) -> bool:
    if not value:
        return True
    return value <= upper


def _run_gaps(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(runs, key=lambda row: row.get("cycleStartedAt") or row.get("createdAt") or "")
    gaps = []
    for previous, current in zip(ordered, ordered[1:]):
        prev_ts = _parse_time(previous.get("cycleStartedAt") or previous.get("createdAt"))
        cur_ts = _parse_time(current.get("cycleStartedAt") or current.get("createdAt"))
        if not prev_ts or not cur_ts:
            continue
        minutes = (cur_ts - prev_ts).total_seconds() / 60.0
        if minutes > 17.0:
            gaps.append({"from": previous["id"], "to": current["id"], "minutes": round(minutes, 2)})
    return gaps


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _run_sort_key(runs: list[dict[str, Any]], run_id: str) -> str:
    for run in runs:
        if run.get("id") == run_id:
            return run.get("cycleStartedAt") or run.get("createdAt") or ""
    return ""
