from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from .agents import MultiAgentPipeline
from .codex_queue import emit_or_enqueue_codex_review, queue_summary
from .codex_review import codex_disabled, run_local_codex_review
from .dashboard_enrichment import enrich_multi_agent_payload
from .reporting import multi_agent_payload


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG_PATH = REPO_ROOT / "config" / "news-sources.json"
INTELLIGENCE_DIR = REPO_ROOT / "data" / "generated" / "intelligence"
LATEST_PATH = INTELLIGENCE_DIR / "latest.json"
RUNS_PATH = INTELLIGENCE_DIR / "analysis_runs.json"
MARKET_RESULTS_PATH = INTELLIGENCE_DIR / "market_analysis_results.json"
SOURCE_SNAPSHOTS_PATH = INTELLIGENCE_DIR / "source_snapshots.json"

CONFIDENCE_LABELS = ((0.67, "high"), (0.38, "medium"), (0.0, "low"))


@dataclass(frozen=True)
class NewsSource:
    name: str
    url: str
    category: str
    reliability_tier: int
    update_frequency: str
    notes: str
    enabled: bool

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "NewsSource":
        tier = int(row.get("reliability_tier", 3))
        if tier not in {1, 2, 3}:
            raise ValueError(f"Invalid reliability_tier for {row.get('name', '<unknown>')}")
        return cls(
            name=str(row["name"]),
            url=str(row.get("url", "")),
            category=str(row["category"]),
            reliability_tier=tier,
            update_frequency=str(row["update_frequency"]),
            notes=str(row.get("notes", "")),
            enabled=bool(row.get("enabled", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "category": self.category,
            "reliability_tier": self.reliability_tier,
            "update_frequency": self.update_frequency,
            "notes": self.notes,
            "enabled": self.enabled,
        }


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_news_sources(path: Path | str = SOURCE_CONFIG_PATH) -> list[NewsSource]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("news source config must be a JSON list")
    return [NewsSource.from_dict(row) for row in payload]


def validate_news_sources(path: Path | str = SOURCE_CONFIG_PATH) -> list[str]:
    errors: list[str] = []
    try:
        sources = load_news_sources(path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [str(exc)]
    names = set()
    for source in sources:
        if source.name in names:
            errors.append(f"duplicate source name: {source.name}")
        names.add(source.name)
        if source.reliability_tier == 3 and source.enabled:
            errors.append(f"tier 3 source must not be enabled by default: {source.name}")
        if source.enabled and not source.url:
            errors.append(f"enabled source requires url: {source.name}")
    if not any(source.enabled and source.reliability_tier == 1 for source in sources):
        errors.append("at least one enabled tier 1 source is required")
    return errors


def run_intelligence_cycle(
    *,
    cycle_type: str = "manual",
    source_mode: str = "fixture",
    target_count: int = 300,
    persist: bool = True,
    allow_codex: bool = True,
    queue_codex: bool = True,
    dashboard_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if cycle_type not in {"scheduled_15m", "post_ingestion", "manual"}:
        raise ValueError("cycle_type must be scheduled_15m, post_ingestion, or manual")

    cycle_started_at = iso_now()
    if dashboard_payload is None:
        result = MultiAgentPipeline().run(source_mode=source_mode, target_count=target_count)
        multi_agent = enrich_multi_agent_payload(multi_agent_payload(result))
    else:
        multi_agent = dashboard_payload["multi_agent"] if "multi_agent" in dashboard_payload else dashboard_payload

    cycle_id = _cycle_id(cycle_type, source_mode, target_count, cycle_started_at)
    source_config = load_news_sources()
    source_snapshots = _source_snapshots(source_config, cycle_started_at)
    recommendations = multi_agent.get("recommendations", [])
    detail_by_id = {row["candidate_id"]: row for row in multi_agent.get("bet_detail_records", [])}
    analyses = [
        _analysis_for_recommendation(
            item,
            detail_by_id.get(item["candidate"]["candidate_id"], {}),
            cycle_id=cycle_id,
            cycle_started_at=cycle_started_at,
            cycle_type=cycle_type,
            source_config=source_config,
        )
        for item in recommendations
    ]
    codex_review = _maybe_run_local_codex_review(analyses[:8], cycle_started_at) if allow_codex else codex_disabled()
    if codex_review["status"] == "failed":
        for analysis in analyses[:8]:
            analysis["status"] = "partial"
            analysis.setdefault("errors", []).append(codex_review["message"])

    payload = {
        "schema_version": 1,
        "id": cycle_id,
        "createdAt": iso_now(),
        "cycleStartedAt": cycle_started_at,
        "cycleType": cycle_type,
        "sourceMode": source_mode,
        "targetCount": target_count,
        "status": _cycle_status(analyses),
        "researchOnly": True,
        "localCodex": codex_review,
        "inputSnapshot": {
            "runId": multi_agent.get("run_id"),
            "createdAt": multi_agent.get("created_at"),
            "candidateCount": multi_agent.get("metrics", {}).get("candidate_count", len(recommendations)),
            "paperBetCount": multi_agent.get("metrics", {}).get("paper_bet_count", 0),
            "sourceNote": multi_agent.get("source_note", ""),
        },
        "summary": _summary(analyses, source_snapshots),
        "analysisRuns": [
            {
                "id": cycle_id,
                "createdAt": cycle_started_at,
                "cycleType": cycle_type,
                "status": _cycle_status(analyses),
                "marketCount": len(analyses),
                "localCodexStatus": codex_review["status"],
            }
        ],
        "analysisSources": source_snapshots,
        "marketAnalysisResults": analyses,
    }
    if queue_codex:
        payload["codexQueue"] = emit_or_enqueue_codex_review(
            payload,
            persist=persist,
            reason=_codex_queue_reason(codex_review),
        )
    else:
        payload["codexQueue"] = {
            "status": "disabled",
            "message": "Codex queueing disabled for this run.",
            "durable": False,
            "pendingCount": 0,
        }
    for row in payload["analysisRuns"]:
        row["codexQueueStatus"] = payload["codexQueue"].get("status")
        row["codexQueuePendingCount"] = payload["codexQueue"].get("pendingCount")
    if persist:
        persist_intelligence_payload(payload)
    return payload


def load_latest_intelligence() -> dict[str, Any]:
    try:
        from .managed_pipeline import LATEST_INTELLIGENCE_KEY
        from .state_store import default_store

        persisted = default_store().read_json(LATEST_INTELLIGENCE_KEY)
        if isinstance(persisted, dict):
            return _normalize_queue_for_runtime(persisted)
    except Exception:
        pass
    if LATEST_PATH.exists():
        return _normalize_queue_for_runtime(json.loads(LATEST_PATH.read_text(encoding="utf-8")))
    return run_intelligence_cycle(cycle_type="manual", source_mode="fixture", target_count=120, persist=False, allow_codex=False)


def _normalize_queue_for_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    queue = dict(payload.get("codexQueue", {}))
    if os.environ.get("VERCEL"):
        if queue:
            queue.update(
                {
                    "status": "deployment_snapshot",
                    "message": "Bundled local queue metadata is visible, but Vercel cannot persist or drain the local Codex queue. /api/cron-refresh emits response-only queue items unless an external durable store is configured.",
                    "storageMode": "vercel_static_snapshot",
                    "durable": False,
                    "pendingCount": 0,
                }
            )
            payload["codexQueue"] = queue
        return payload
    if queue:
        live_summary = queue_summary()
        queue.update(live_summary)
        payload["codexQueue"] = queue
    return payload


def persist_intelligence_payload(payload: dict[str, Any]) -> None:
    INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(LATEST_PATH, payload)
    _atomic_write_json(MARKET_RESULTS_PATH, payload["marketAnalysisResults"])
    _atomic_write_json(SOURCE_SNAPSHOTS_PATH, payload["analysisSources"])
    run_history = []
    if RUNS_PATH.exists():
        try:
            run_history = json.loads(RUNS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            run_history = []
    run_by_id = {row["id"]: row for row in run_history if isinstance(row, dict) and "id" in row}
    for row in payload["analysisRuns"]:
        run_by_id[row["id"]] = row
    rows = sorted(run_by_id.values(), key=lambda row: row["createdAt"], reverse=True)[:96]
    _atomic_write_json(RUNS_PATH, rows)


def _analysis_for_recommendation(
    item: dict[str, Any],
    detail: dict[str, Any],
    *,
    cycle_id: str,
    cycle_started_at: str,
    cycle_type: str,
    source_config: list[NewsSource],
) -> dict[str, Any]:
    candidate = item["candidate"]
    history = candidate.get("odds_history", [])
    probabilities = [float(point.get("price", 0.0)) for point in history]
    current_probability = float(candidate.get("price", 0.0))
    previous_probability = probabilities[-2] if len(probabilities) >= 2 else (probabilities[0] if probabilities else None)
    probability_delta = None if previous_probability is None else round(current_probability - previous_probability, 4)
    volatility = round(pstdev(probabilities), 4) if len(probabilities) > 1 else 0.0
    news_items = _news_items(candidate, source_config, cycle_started_at)
    model = _model_interpretation(item, candidate, probability_delta, volatility)
    news_context = _news_context(news_items)
    reliability = _reliability(item, candidate, news_context, volatility)
    decision = _decision_commentary(item, model, news_context, reliability)
    status = "success" if reliability["overallScore"] >= 0.5 else "partial"
    errors = []
    if not news_items:
        errors.append("No source-backed news/context items were available for this market.")
    elif news_context["tier1Count"] + news_context["tier2Count"] == 0:
        errors.append("Only weak/noisy Tier 3 context is available; strong conclusion blocked.")
    return {
        "id": f"{cycle_id}:{candidate['candidate_id']}",
        "createdAt": iso_now(),
        "cycleStartedAt": cycle_started_at,
        "cycleType": cycle_type,
        "marketId": candidate.get("event_id"),
        "marketSlug": candidate.get("candidate_id"),
        "marketTitle": candidate.get("market_title"),
        "marketUrl": candidate.get("source_url"),
        "category": candidate.get("category"),
        "state": detail.get("state", "planning"),
        "marketSnapshot": {
            "currentProbability": round(current_probability, 4),
            "previousProbability": round(previous_probability, 4) if previous_probability is not None else None,
            "probabilityDelta": probability_delta,
            "volumeDelta": 0.0,
            "liquidityDelta": 0.0,
            "priceVolatility": volatility,
            "unusualMoveDetected": bool(abs(probability_delta or 0.0) >= 0.03 or volatility >= 0.035),
        },
        "modelInterpretation": model,
        "newsContext": news_context,
        "decisionCommentary": decision,
        "reliability": reliability,
        "forecastChart": _forecast_chart(history, item, model),
        "status": status,
        "errors": errors,
    }


def _news_items(candidate: dict[str, Any], source_config: list[NewsSource], fetched_time: str) -> list[dict[str, Any]]:
    configured = {(source.category, source.name.lower()): source for source in source_config}
    category_defaults = [source for source in source_config if source.category in {candidate.get("category"), "global", "polymarket"}]
    rows = []
    for item in candidate.get("news_items", []):
        source_name = str(item.get("source", "unknown"))
        configured_source = configured.get((candidate.get("category", ""), source_name.lower()))
        tier = configured_source.reliability_tier if configured_source else 3
        url = configured_source.url if configured_source else ""
        relevance = min(abs(float(item.get("impact", 0.0))) * 4.0 + float(item.get("credibility", 0.5)) * 0.4, 1.0)
        rows.append(
            {
                "title": str(item.get("headline", "")),
                "source": source_name,
                "sourceUrl": url,
                "publicationTime": item.get("time"),
                "fetchedTime": fetched_time,
                "reliabilityTier": tier,
                "relevanceScore": round(relevance, 4),
                "marketIdsAffected": [candidate.get("candidate_id")],
                "whyItMatters": _why_news_matters(item, tier),
                "evidenceRole": _evidence_role(tier, relevance),
            }
        )
    if not rows:
        for source in category_defaults[:3]:
            rows.append(
                {
                    "title": "No fetched item available from configured source in this MVP cycle",
                    "source": source.name,
                    "sourceUrl": source.url,
                    "publicationTime": None,
                    "fetchedTime": fetched_time,
                    "reliabilityTier": source.reliability_tier,
                    "relevanceScore": 0.0,
                    "marketIdsAffected": [candidate.get("candidate_id")],
                    "whyItMatters": "Configured source exists but no current fetched item was attached to this market.",
                    "evidenceRole": "weak/noisy signal",
                }
            )
    return rows


def _why_news_matters(item: dict[str, Any], tier: int) -> str:
    direction = "supports" if float(item.get("impact", 0.0)) > 0 else "weakens" if float(item.get("impact", 0.0)) < 0 else "does not move"
    tier_note = "primary/reliable" if tier == 1 else "supporting" if tier == 2 else "weak/noisy"
    return f"Observed context {direction} the market thesis; source tier is {tier_note}."


def _evidence_role(tier: int, relevance: float) -> str:
    if tier == 1 and relevance >= 0.35:
        return "primary evidence"
    if tier in {1, 2} and relevance >= 0.15:
        return "supporting context"
    return "weak/noisy signal"


def _model_interpretation(
    item: dict[str, Any],
    candidate: dict[str, Any],
    probability_delta: float | None,
    volatility: float,
) -> dict[str, Any]:
    edge = float(item.get("edge", 0.0))
    confidence = float(item.get("confidence", 0.0))
    if edge > 0.025:
        direction = "up"
    elif edge < -0.025:
        direction = "down"
    elif probability_delta is not None and probability_delta > 0.015:
        direction = "up"
    elif probability_delta is not None and probability_delta < -0.015:
        direction = "down"
    else:
        direction = "neutral"
    return {
        "forecastDirection": direction,
        "confidence": round(confidence, 4),
        "confidenceLabel": _confidence_label(confidence),
        "mainDrivers": [
            f"model edge {edge:+.2%}",
            f"expected value {float(item.get('expected_value', 0.0)):+.2%}",
            f"spread {float(candidate.get('spread', 0.0)):.2%}",
        ],
        "riskFactors": _risk_factors(item, candidate, volatility),
        "uncertaintyNotes": _uncertainty_notes(item, candidate),
    }


def _risk_factors(item: dict[str, Any], candidate: dict[str, Any], volatility: float) -> list[str]:
    risks = []
    if float(candidate.get("spread", 0.0)) > 0.05:
        risks.append("Wide spread reduces execution and interpretation quality.")
    if float(candidate.get("liquidity", 0.0)) < 5000:
        risks.append("Low liquidity makes price movement less reliable.")
    if volatility > 0.035:
        risks.append("Recent probability path is volatile.")
    risks.extend(candidate.get("resolution_risk_flags", []))
    risks.extend(candidate.get("contradiction_flags", []))
    return risks or ["No major model-side risk flag beyond normal market uncertainty."]


def _uncertainty_notes(item: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    notes = []
    if "fixture_context_not_live" in candidate.get("staleness_flags", []):
        notes.append("Fixture context is deterministic and not live external news.")
    if item.get("decision") != "PAPER_BET":
        notes.append(f"Decision layer did not allocate paper stake: {item.get('reason', '')}")
    if not notes:
        notes.append("Forecast is still probabilistic; no outcome is guaranteed.")
    return notes


def _news_context(news_items: list[dict[str, Any]]) -> dict[str, Any]:
    strongest = sorted(news_items, key=lambda row: (row["reliabilityTier"] * -1, row["relevanceScore"]), reverse=True)
    return {
        "relevantItemsCount": len(news_items),
        "tier1Count": sum(1 for row in news_items if row["reliabilityTier"] == 1),
        "tier2Count": sum(1 for row in news_items if row["reliabilityTier"] == 2),
        "tier3Count": sum(1 for row in news_items if row["reliabilityTier"] == 3),
        "strongestSources": [
            {
                "title": row["title"],
                "source": row["source"],
                "url": row.get("sourceUrl") or None,
                "reliabilityTier": row["reliabilityTier"],
                "relevanceScore": row["relevanceScore"],
                "summary": row["whyItMatters"],
                "evidenceRole": row["evidenceRole"],
            }
            for row in strongest[:5]
        ],
        "items": news_items,
    }


def _decision_commentary(
    item: dict[str, Any],
    model: dict[str, Any],
    news_context: dict[str, Any],
    reliability: dict[str, Any],
) -> dict[str, Any]:
    source_quality = reliability["sourceQualityScore"]
    strength = min(
        abs(float(item.get("edge", 0.0))) * 4.5
        + float(item.get("confidence", 0.0)) * 0.35
        + reliability["overallScore"] * 0.25,
        1.0,
    )
    if reliability["overallScore"] < 0.35:
        signal = "avoid"
    elif news_context["tier1Count"] + news_context["tier2Count"] == 0 and strength > 0.65:
        signal = "watch"
    elif model["forecastDirection"] == "up" and strength >= 0.55 and source_quality >= 0.45:
        signal = "bullish"
    elif model["forecastDirection"] == "down" and strength >= 0.55 and source_quality >= 0.45:
        signal = "bearish"
    elif model["forecastDirection"] == "neutral":
        signal = "neutral"
    else:
        signal = "watch"
    return {
        "signal": signal,
        "signalStrength": round(strength, 4),
        "reasoning": [
            f"Observed model direction is {model['forecastDirection']} with {model['confidenceLabel']} confidence.",
            f"Source quality score is {source_quality:.2f}; Tier 3 sources cannot justify strong conclusions alone.",
            "Decision is a paper-only research signal and never an execution instruction.",
        ],
        "recommendedHumanAction": _human_action(signal),
        "notFinancialAdvice": True,
    }


def _human_action(signal: str) -> str:
    actions = {
        "bullish": "Review source links and settlement rules before considering this as a paper portfolio candidate.",
        "bearish": "Monitor for downside confirmation and avoid increasing paper exposure without reliable sources.",
        "watch": "Keep on watchlist until source reliability, liquidity, or model confidence improves.",
        "neutral": "No clear action; wait for stronger movement or source-backed context.",
        "avoid": "Avoid paper allocation until data/source quality improves.",
    }
    return actions[signal]


def _reliability(
    item: dict[str, Any],
    candidate: dict[str, Any],
    news_context: dict[str, Any],
    volatility: float,
) -> dict[str, Any]:
    data_quality = 1.0
    if "fixture_context_not_live" in candidate.get("staleness_flags", []):
        data_quality -= 0.18
    if float(candidate.get("spread", 0.0)) > 0.06:
        data_quality -= 0.14
    if float(candidate.get("liquidity", 0.0)) < 5000:
        data_quality -= 0.10
    if volatility > 0.04:
        data_quality -= 0.10
    source_quality = _source_quality(news_context)
    model_quality = min(max(float(item.get("confidence", 0.0)) * 0.75 + (1.0 - abs(float(item.get("edge", 0.0))) * 0.4), 0.0), 1.0)
    overall = max(min((data_quality * 0.34) + (source_quality * 0.33) + (model_quality * 0.33), 1.0), 0.0)
    return {
        "overallScore": round(overall, 4),
        "dataQualityScore": round(max(data_quality, 0.0), 4),
        "sourceQualityScore": round(source_quality, 4),
        "modelQualityScore": round(model_quality, 4),
        "label": _reliability_label(overall),
        "explanation": _reliability_explanation(overall, source_quality),
    }


def _source_quality(news_context: dict[str, Any]) -> float:
    total = max(news_context["relevantItemsCount"], 1)
    score = (news_context["tier1Count"] * 1.0 + news_context["tier2Count"] * 0.65 + news_context["tier3Count"] * 0.25) / total
    if news_context["tier1Count"] + news_context["tier2Count"] == 0:
        score = min(score, 0.35)
    return round(min(max(score, 0.0), 1.0), 4)


def _reliability_label(score: float) -> str:
    if score > 0.8:
        return "reliable"
    if score >= 0.5:
        return "possible/probable"
    return "unreliable/reject"


def _reliability_explanation(score: float, source_quality: float) -> str:
    label = _reliability_label(score)
    if source_quality < 0.5:
        return f"{label}: source quality is weak, so interpretation must remain cautious."
    return f"{label}: data, source, and model scores are sufficient for paper-only monitoring."


def _forecast_chart(history: list[dict[str, Any]], item: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    values = [{"time": point.get("time", ""), "probability": float(point.get("price", 0.0))} for point in history[-12:]]
    forecast = float(item.get("blended_probability", 0.0))
    confidence = float(model.get("confidence", 0.0))
    interval = max(0.04, (1.0 - confidence) * 0.18 + float(item["candidate"].get("spread", 0.0)))
    return {
        "history": values,
        "forecastProbability": round(forecast, 4),
        "lowerInterval": round(max(forecast - interval, 0.01), 4),
        "upperInterval": round(min(forecast + interval, 0.99), 4),
        "deviationFromMarket": round(forecast - float(item["candidate"].get("price", 0.0)), 4),
    }


def _summary(analyses: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    signal_counts: dict[str, int] = {}
    for row in analyses:
        signal = row["decisionCommentary"]["signal"]
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
    return {
        "marketCount": len(analyses),
        "successCount": sum(1 for row in analyses if row["status"] == "success"),
        "partialCount": sum(1 for row in analyses if row["status"] == "partial"),
        "failedCount": sum(1 for row in analyses if row["status"] == "failed"),
        "averageReliability": round(mean([row["reliability"]["overallScore"] for row in analyses]), 4) if analyses else 0.0,
        "unusualMoveCount": sum(1 for row in analyses if row["marketSnapshot"]["unusualMoveDetected"]),
        "signalCounts": signal_counts,
        "enabledSourceCount": sum(1 for row in sources if row["enabled"]),
    }


def _source_snapshots(sources: list[NewsSource], fetched_time: str) -> list[dict[str, Any]]:
    return [
        {
            **source.to_dict(),
            "fetchedTime": fetched_time,
            "status": "configured_enabled" if source.enabled else "configured_disabled",
        }
        for source in sources
    ]


def _maybe_run_local_codex_review(analyses: list[dict[str, Any]], cycle_started_at: str) -> dict[str, Any]:
    return run_local_codex_review(analyses, cycle_started_at)


def _codex_queue_reason(codex_review: dict[str, Any]) -> str:
    status = codex_review.get("status", "unknown")
    message = codex_review.get("message", "")
    return f"local_codex_{status}: {message}"


def _cycle_status(analyses: list[dict[str, Any]]) -> str:
    if not analyses:
        return "failed"
    if any(row["status"] == "failed" for row in analyses):
        return "partial"
    if any(row["status"] == "partial" for row in analyses):
        return "partial"
    return "success"


def _cycle_id(cycle_type: str, source_mode: str, target_count: int, started_at: str) -> str:
    if cycle_type == "scheduled_15m":
        now = int(time.time())
        bucket = now - (now % 900)
        raw = f"{cycle_type}:{source_mode}:{target_count}:{bucket}"
    else:
        raw = f"{cycle_type}:{source_mode}:{target_count}:{started_at}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"intel-{digest}"


def _confidence_label(confidence: float) -> str:
    for threshold, label in CONFIDENCE_LABELS:
        if confidence >= threshold:
            return label
    return "low"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Polymarket intelligence analysis cycle")
    parser.add_argument("--cycle-type", choices=["scheduled_15m", "post_ingestion", "manual"], default="manual")
    parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--target-count", type=int, default=300)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--no-codex", action="store_true")
    parser.add_argument("--no-queue", action="store_true")
    args = parser.parse_args(argv)
    payload = run_intelligence_cycle(
        cycle_type=args.cycle_type,
        source_mode=args.source,
        target_count=args.target_count,
        persist=not args.no_persist,
        allow_codex=not args.no_codex,
        queue_codex=not args.no_queue,
    )
    print(
        json.dumps(
            {
                "id": payload["id"],
                "status": payload["status"],
                "marketCount": payload["summary"]["marketCount"],
                "averageReliability": payload["summary"]["averageReliability"],
                "localCodexStatus": payload["localCodex"]["status"],
                "codexQueueStatus": payload.get("codexQueue", {}).get("status"),
                "codexQueuePendingCount": payload.get("codexQueue", {}).get("pendingCount"),
                "output": str(LATEST_PATH if not args.no_persist else "<not persisted>"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
