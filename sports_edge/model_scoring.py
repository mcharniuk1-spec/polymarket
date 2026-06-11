from __future__ import annotations

from statistics import mean
from typing import Any

from .research_scope import ACTIVE_CATEGORIES
from .schemas import ModelOutput, stable_id


PROBABILITY_MODEL_FAMILIES = (
    "market_implied_probability",
    "liquidity_microstructure",
    "base_rate_event_history",
    "bayesian_consensus",
    "news_catalyst_sentiment",
)


def score_market_candidates(*, run_id: str, data_payload: dict[str, Any], created_at: str) -> list[ModelOutput]:
    markets = data_payload.get("marketSnapshots", [])
    books_by_market = {row.get("market_id"): row for row in data_payload.get("orderBookSnapshots", [])}
    external_by_category = _external_observations_by_category(data_payload.get("externalObservations", []))
    outputs: list[ModelOutput] = []
    for market in markets:
        category = str(market.get("category") or "")
        if category not in ACTIVE_CATEGORIES:
            continue
        candidate_id = str(market.get("market_id"))
        market_id = str(market.get("market_id"))
        book = books_by_market.get(market_id, {})
        external = external_by_category.get(category, [])
        implied = _market_implied_probability(market, book)
        base_rate = _base_rate_probability(market, external)
        liquidity = _liquidity_adjusted_probability(market, book, implied)
        bayesian = _bayesian_probability(implied, base_rate, external)
        catalyst = _catalyst_probability(market, base_rate, external)
        probability_rows = [
            ("market_implied_probability", implied, _market_confidence(market, book), {"source": "price_midpoint_or_outcome_price"}),
            ("liquidity_microstructure", liquidity, _liquidity_confidence(market, book), _liquidity_features(market, book)),
            ("base_rate_event_history", base_rate, _base_rate_confidence(external), {"baseRateClass": _base_rate_class(market), **_external_feature_summary(external)}),
            ("bayesian_consensus", bayesian, _bayesian_confidence(external), {"prior": base_rate, "likelihood": implied, "consensusStatus": _consensus_status(external), **_external_feature_summary(external)}),
            ("news_catalyst_sentiment", catalyst, _catalyst_confidence(external), {"sentiment": _catalyst_status(external), "liveNewsStatus": "fixture_context_ready", **_external_feature_summary(external)}),
        ]
        probabilities = [row[1] for row in probability_rows]
        disagreement = _disagreement(probabilities)
        reject_flags = _reject_flags(market, book, disagreement)
        for family, probability, confidence, features in probability_rows:
            outputs.append(
                ModelOutput(
                    output_id=stable_id(run_id, candidate_id, family),
                    run_id=run_id,
                    candidate_id=candidate_id,
                    market_id=market_id,
                    category=category,
                    model_family=family,
                    probability=round(probability, 4),
                    confidence=round(confidence, 4),
                    evidence_quality=_evidence_quality(reject_flags, confidence),
                    features={**features, "marketPrice": implied, "question": market.get("question")},
                    disagreement=disagreement,
                    gaps=_model_gaps(family),
                    reject_flags=reject_flags,
                    created_at=created_at,
                )
            )
        portfolio_probability = _portfolio_fair_probability(probabilities)
        outputs.append(
            ModelOutput(
                output_id=stable_id(run_id, candidate_id, "portfolio_ev_risk"),
                run_id=run_id,
                candidate_id=candidate_id,
                market_id=market_id,
                category=category,
                model_family="portfolio_ev_risk",
                probability=round(portfolio_probability, 4),
                confidence=round(max(0.2, 1.0 - disagreement["range"]), 4),
                evidence_quality=_evidence_quality(reject_flags, max(0.2, 1.0 - disagreement["range"])),
                features={
                    "fairProbability": portfolio_probability,
                    "marketPrice": implied,
                    "edge": round(portfolio_probability - implied, 4),
                    "spread": market.get("spread"),
                    "liquidity": market.get("liquidity"),
                    "portfolioUse": "decision_agent_input",
                },
                disagreement=disagreement,
                gaps=[] if not reject_flags else ["portfolio risk model received reject flags"],
                reject_flags=reject_flags,
                created_at=created_at,
            )
        )
        outputs.append(
            ModelOutput(
                output_id=stable_id(run_id, candidate_id, "statistical_ml_probability"),
                run_id=run_id,
                candidate_id=candidate_id,
                market_id=market_id,
                category=category,
                model_family="statistical_ml_probability",
                probability=None,
                confidence=0.0,
                evidence_quality="insufficient_training_data",
                features={"trainingStatus": "disabled_until_enough_resolved_asof_safe_examples"},
                disagreement=disagreement,
                gaps=["insufficient resolved outcome history for statistical/ML probability"],
                reject_flags=["statistical_ml_unavailable"],
                created_at=created_at,
            )
        )
    return outputs


def model_outputs_by_candidate(model_outputs: list[ModelOutput] | list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in model_outputs:
        payload = row.to_dict() if hasattr(row, "to_dict") else row
        grouped.setdefault(str(payload.get("candidate_id")), []).append(payload)
    return grouped


def _market_implied_probability(market: dict[str, Any], book: dict[str, Any]) -> float:
    bid = _float(book.get("best_bid"), market.get("best_bid"))
    ask = _float(book.get("best_ask"), market.get("best_ask"))
    if bid is not None and ask is not None:
        return _clamp((bid + ask) / 2)
    prices = market.get("outcome_prices")
    if isinstance(prices, list) and prices:
        first = _float(prices[0])
        if first is not None:
            return _clamp(first)
    return 0.5


def _liquidity_adjusted_probability(market: dict[str, Any], book: dict[str, Any], implied: float) -> float:
    spread = _float(book.get("spread"), market.get("spread")) or 0.25
    liquidity = _float(market.get("liquidity")) or 0.0
    depth = (_float(book.get("bid_depth")) or 0.0) + (_float(book.get("ask_depth")) or 0.0)
    penalty = min(spread * 0.35, 0.08)
    depth_credit = min(depth / 10000.0, 0.03)
    liquidity_credit = min(liquidity / 100000.0, 0.03)
    return _clamp(implied - penalty + depth_credit + liquidity_credit)


def _base_rate_probability(market: dict[str, Any], external: list[dict[str, Any]]) -> float:
    category = market.get("category")
    text = str(market.get("question") or "").lower()
    if category == "macroeconomics":
        surprise = _metric(external, "consensus_surprise_z") or 0.0
        if "above consensus" in text or "above" in text:
            return _clamp(0.48 + min(max(surprise * 0.08, -0.05), 0.05))
        return 0.50
    if category == "politics":
        delay_risk = _metric(external, "deadline_delay_risk_index")
        if "delayed" in text or "delay" in text:
            return _clamp(delay_risk if delay_risk is not None else 0.30)
        return 0.45
    if category == "stocks_trade":
        recent_return = _metric(external, "underlying_return_1d") or 0.0
        if "close above" in text:
            return _clamp(0.51 + min(max(recent_return * 1.2, -0.04), 0.04))
        return 0.50
    return 0.50


def _bayesian_probability(implied: float, base_rate: float, external: list[dict[str, Any]]) -> float:
    consensus_weight = 0.60 if _has_real_external_signal(external) else 0.55
    market_weight = 1.0 - consensus_weight
    return _clamp((base_rate * consensus_weight) + (implied * market_weight))


def _catalyst_probability(market: dict[str, Any], base_rate: float, external: list[dict[str, Any]]) -> float:
    text = str(market.get("question") or "").lower()
    catalyst_adjustment = 0.0
    if any(term in text for term in ("deadline", "release", "earnings", "threshold")):
        catalyst_adjustment += 0.01
    days_to_release = _metric(external, "days_until_next_release")
    event_window = _metric(external, "event_window_days")
    political_deadline = _metric(external, "days_until_political_deadline")
    if days_to_release is not None and days_to_release <= 5:
        catalyst_adjustment += 0.008
    if event_window is not None and event_window <= 3:
        catalyst_adjustment += 0.006
    if political_deadline is not None and political_deadline <= 7:
        catalyst_adjustment += 0.004
    if any(term in text for term in ("delayed", "delay")):
        catalyst_adjustment -= 0.015
    return _clamp(base_rate + catalyst_adjustment)


def _portfolio_fair_probability(probabilities: list[float]) -> float:
    return _clamp(mean(probabilities))


def _market_confidence(market: dict[str, Any], book: dict[str, Any]) -> float:
    spread = _float(book.get("spread"), market.get("spread"))
    liquidity = _float(market.get("liquidity")) or 0.0
    confidence = 0.55
    if spread is not None:
        confidence += max(0.0, 0.10 - spread)
    confidence += min(liquidity / 50000.0, 0.10)
    return _clamp(confidence)


def _liquidity_confidence(market: dict[str, Any], book: dict[str, Any]) -> float:
    spread = _float(book.get("spread"), market.get("spread")) or 0.25
    liquidity = _float(market.get("liquidity")) or 0.0
    depth = (_float(book.get("bid_depth")) or 0.0) + (_float(book.get("ask_depth")) or 0.0)
    confidence = 0.25 + min(liquidity / 20000.0, 0.20) + min(depth / 5000.0, 0.20) + max(0.0, 0.15 - spread)
    return _clamp(confidence)


def _liquidity_features(market: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    return {
        "spread": _float(book.get("spread"), market.get("spread")),
        "liquidity": _float(market.get("liquidity")),
        "bidDepth": _float(book.get("bid_depth")),
        "askDepth": _float(book.get("ask_depth")),
        "microstructureStatus": "usable" if not _reject_flags(market, book, {"range": 0.0}) else "gated",
    }


def _base_rate_class(market: dict[str, Any]) -> str:
    category = market.get("category")
    text = str(market.get("question") or "").lower()
    if category == "macroeconomics":
        return "macro_release_threshold"
    if category == "politics" and "deadline" in text:
        return "political_deadline_delay"
    if category == "stocks_trade" and "close" in text:
        return "equity_close_threshold"
    return f"{category}_generic"


def _disagreement(probabilities: list[float]) -> dict[str, Any]:
    if not probabilities:
        return {"minProbability": None, "maxProbability": None, "range": 1.0, "modelCount": 0, "status": "missing"}
    low = min(probabilities)
    high = max(probabilities)
    spread = high - low
    if spread <= 0.08:
        status = "low"
    elif spread <= 0.16:
        status = "medium"
    else:
        status = "high"
    return {
        "minProbability": round(low, 4),
        "maxProbability": round(high, 4),
        "range": round(spread, 4),
        "modelCount": len(probabilities),
        "status": status,
    }


def _reject_flags(market: dict[str, Any], book: dict[str, Any], disagreement: dict[str, Any]) -> list[str]:
    flags = []
    spread = _float(book.get("spread"), market.get("spread"))
    liquidity = _float(market.get("liquidity")) or 0.0
    if spread is None:
        flags.append("missing_spread")
    elif spread > 0.12:
        flags.append("high_spread")
    if liquidity < 500:
        flags.append("low_liquidity")
    if not market.get("resolution_criteria"):
        flags.append("unclear_resolution_criteria")
    if disagreement.get("range", 1.0) > 0.18:
        flags.append("high_model_disagreement")
    if not market.get("end_time"):
        flags.append("missing_resolution_time")
    return flags


def _model_gaps(family: str) -> list[str]:
    gaps_by_family = {
        "base_rate_event_history": ["base-rate history uses fixture priors until outcome database is populated"],
        "bayesian_consensus": ["consensus adapters require approved structured inputs; health checks are not decision evidence"],
        "news_catalyst_sentiment": ["live news/social/expert Context Agent fetchers pending"],
    }
    return gaps_by_family.get(family, [])


def _evidence_quality(reject_flags: list[str], confidence: float) -> str:
    if reject_flags:
        return "weak"
    if confidence >= 0.7:
        return "moderate"
    return "limited"


def _float(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _clamp(value: float, low: float = 0.01, high: float = 0.99) -> float:
    return min(max(value, low), high)


def _external_observations_by_category(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("category")), []).append(row)
    return grouped


def _metric(external: list[dict[str, Any]], metric_name: str) -> float | None:
    for row in external:
        if row.get("metric_name") == metric_name:
            return _float(row.get("metric_value"))
    return None


def _external_feature_summary(external: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "externalObservationCount": len(external),
        "externalMetrics": {
            str(row.get("metric_name")): row.get("metric_value")
            for row in external
            if row.get("metric_name")
        },
        "externalSourceIds": sorted({str(row.get("source_id")) for row in external if row.get("source_id")}),
        "asOfSafe": all(row.get("as_of") and row.get("observed_at") for row in external),
    }


def _has_real_external_signal(external: list[dict[str, Any]]) -> bool:
    return any(_is_decision_evidence(row) for row in external)


def _is_decision_evidence(row: dict[str, Any]) -> bool:
    metric_name = row.get("metric_name")
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if metric_name in {"adapter_readiness", "official_source_http_ok"}:
        return False
    if payload.get("relevance") == "source_health_not_decision_evidence":
        return False
    return row.get("metric_value") is not None


def _base_rate_confidence(external: list[dict[str, Any]]) -> float:
    return 0.48 if _has_real_external_signal(external) else 0.40


def _bayesian_confidence(external: list[dict[str, Any]]) -> float:
    return 0.50 if _has_real_external_signal(external) else 0.42


def _catalyst_confidence(external: list[dict[str, Any]]) -> float:
    return 0.44 if _has_real_external_signal(external) else 0.34


def _consensus_status(external: list[dict[str, Any]]) -> str:
    if any(row.get("metric_name") == "adapter_readiness" for row in external):
        return "adapter_pending"
    if not _has_real_external_signal(external):
        return "source_health_only"
    return "external_signal_available"


def _catalyst_status(external: list[dict[str, Any]]) -> str:
    if not _has_real_external_signal(external):
        return "neutral_contract"
    return "catalyst_observed"
