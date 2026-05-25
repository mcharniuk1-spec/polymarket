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
    agent_report = run_agent_replay(store=state_store)
    ml_report = run_ml_update(store=state_store, global_review=global_review)
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


def run_agent_replay(*, store: JsonStateStore | None = None) -> dict[str, Any]:
    state_store = store or default_store()
    history = state_store.read_json(RUN_HISTORY_KEY, {"runs": []})
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
        snapshot = state_store.read_json(f"collection_runs/{run_id}.json")
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


def run_ml_update(*, store: JsonStateStore | None = None, global_review: bool = False) -> dict[str, Any]:
    state_store = store or default_store()
    history = state_store.read_json(RUN_HISTORY_KEY, {"runs": []})
    runs = sorted(history.get("runs", []), key=lambda row: row.get("cycleStartedAt") or row.get("createdAt") or "")
    # Rebuild from persisted chronological examples each run so repeated ML automations
    # cannot double-train on the same historical examples.
    models: dict[str, Any] = {}
    examples = []
    for run in runs:
        snapshot = state_store.read_json(f"collection_runs/{run['id']}.json")
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
    }
    correlations = build_correlation_matrices(runs, state_store)
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


def build_correlation_matrices(runs: list[dict[str, Any]], store: JsonStateStore) -> dict[str, Any]:
    category_markets: dict[str, dict[str, dict[str, Any]]] = {category: {} for category in ACTIVE_CATEGORIES}
    for run in runs:
        snapshot = store.read_json(f"collection_runs/{run['id']}.json")
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
