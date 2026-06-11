from __future__ import annotations

from statistics import mean
from typing import Any

from .model_scoring import model_outputs_by_candidate
from .research_scope import ACTIVE_CATEGORIES, CATEGORY_LABELS
from .schemas import ContextReport, reliability_label, stable_id
from .source_registry import SourceRecord as RegistrySourceRecord
from .source_registry import SourceRegistry


HARD_REJECT_FLAGS = {
    "unclear_resolution_criteria",
    "high_spread",
    "low_liquidity",
    "high_model_disagreement",
    "missing_resolution_time",
}


class ContextAgent:
    """Research-first context layer for broad and candidate-specific analysis.

    The fixture implementation does not fetch news or social feeds. It turns the registered source
    inventory, external-observation readiness, market wording, and model diagnostics into auditable
    context reports so later live adapters can replace the evidence rows without changing contracts.
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self.registry = registry or SourceRegistry()

    def broad_context_reports(
        self,
        *,
        run_id: str,
        created_at: str,
        source_mode: str = "fixture",
        data_payload: dict[str, Any] | None = None,
    ) -> list[ContextReport]:
        data_payload = data_payload or {}
        reports: list[ContextReport] = []
        for category in ACTIVE_CATEGORIES:
            sources = self._source_rows(category, topic=CATEGORY_LABELS[category], limit=8)
            observations = [
                row
                for row in data_payload.get("externalObservations", [])
                if row.get("category") == category
            ]
            confidence = self._broad_confidence(sources=sources, observations=observations, source_mode=source_mode)
            reports.append(
                ContextReport(
                    report_id=stable_id(run_id, category, "broad_context"),
                    run_id=run_id,
                    category=category,
                    scope="broad_category",
                    created_at=created_at,
                    summary=self._broad_summary(category, source_mode, observations),
                    key_events=self._broad_events(category, observations),
                    sources=sources,
                    uncertainty=self._broad_uncertainty(source_mode, observations),
                    confidence=confidence,
                    reliability=reliability_label(
                        confidence,
                        strong_evidence=self._has_high_reliability_source(sources),
                        model_agreement=False,
                    ),
                    market_relevance=[category],
                    invalidation_triggers=[
                        "official source freshness exceeds SLA",
                        "major event calendar changes after the run timestamp",
                        "source registry marks a required source as blocked or unreliable",
                        "candidate-specific analysis contradicts the broad category thesis",
                    ],
                )
            )
        return reports

    def bet_specific_reports(
        self,
        *,
        run_id: str,
        created_at: str,
        data_payload: dict[str, Any],
        model_outputs: list[Any],
        source_mode: str = "fixture",
        max_candidates: int = 12,
    ) -> list[ContextReport]:
        outputs_by_candidate = model_outputs_by_candidate(model_outputs)
        relevant = self.relevant_candidates(
            data_payload=data_payload,
            model_outputs=model_outputs,
            max_candidates=max_candidates,
        )
        reports: list[ContextReport] = []
        for market in relevant:
            candidate_id = str(market.get("market_id"))
            category = str(market.get("category"))
            candidate_outputs = outputs_by_candidate.get(candidate_id, [])
            sources = self._source_rows(category, topic=str(market.get("question") or ""), limit=8)
            disagreement = _candidate_disagreement(candidate_outputs)
            confidence = self._candidate_confidence(market=market, sources=sources, disagreement=disagreement, source_mode=source_mode)
            reports.append(
                ContextReport(
                    report_id=stable_id(run_id, candidate_id, "bet_specific_context"),
                    run_id=run_id,
                    category=category,
                    scope="bet_specific",
                    created_at=created_at,
                    candidate_id=candidate_id,
                    summary=self._candidate_summary(market, disagreement, source_mode),
                    key_events=self._candidate_events(market, candidate_outputs),
                    sources=sources,
                    uncertainty=self._candidate_uncertainty(market, disagreement, source_mode),
                    confidence=confidence,
                    reliability=reliability_label(
                        confidence,
                        strong_evidence=self._has_high_reliability_source(sources) and source_mode != "fixture",
                        model_agreement=float(disagreement.get("range") or 1.0) <= 0.12,
                    ),
                    market_relevance=[candidate_id, category],
                    invalidation_triggers=self._candidate_invalidation_triggers(market),
                )
            )
        return reports

    def relevant_candidates(
        self,
        *,
        data_payload: dict[str, Any],
        model_outputs: list[Any],
        max_candidates: int = 12,
    ) -> list[dict[str, Any]]:
        outputs_by_candidate = model_outputs_by_candidate(model_outputs)
        scored: list[tuple[float, dict[str, Any]]] = []
        for market in data_payload.get("marketSnapshots", []):
            category = str(market.get("category") or "")
            if category not in ACTIVE_CATEGORIES:
                continue
            candidate_id = str(market.get("market_id"))
            outputs = outputs_by_candidate.get(candidate_id, [])
            reject_flags = {flag for row in outputs for flag in row.get("reject_flags", [])}
            if reject_flags.intersection(HARD_REJECT_FLAGS):
                continue
            score = self._relevance_score(market, outputs)
            if score > 0:
                scored.append((score, market))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [market for _, market in scored[:max_candidates]]

    def _source_rows(self, category: str, *, topic: str, limit: int) -> list[dict[str, Any]]:
        sources = self.registry.search(topic, category=category, allowed_only=False, limit=limit)
        if not sources:
            sources = self.registry.for_category(category, include_global=True, include_polymarket=True, allowed_only=False)[:limit]
        return [self._source_row(source, topic=topic) for source in sources]

    def _source_row(self, source: RegistrySourceRecord, *, topic: str) -> dict[str, Any]:
        return {
            "source_id": source.id,
            "name": source.name,
            "source_type": source.source_type,
            "category": source.category,
            "reliability_tier": source.reliability_tier,
            "allowed_by_default": source.allowed_by_default,
            "access_policy": source.access,
            "license_notes": source.license_notes,
            "freshness": source.freshness,
            "history_depth": source.history_depth,
            "query": self.registry.render_query(source, topic=topic),
            "source_reliability": "strong" if source.reliability_tier in {"primary", "high"} else source.reliability_tier,
        }

    @staticmethod
    def _broad_confidence(*, sources: list[dict[str, Any]], observations: list[dict[str, Any]], source_mode: str) -> float:
        high_reliability = sum(1 for source in sources if source.get("reliability_tier") in {"primary", "high"})
        allowed = sum(1 for source in sources if source.get("allowed_by_default"))
        confidence = 0.42 + min(high_reliability * 0.025, 0.14) + min(allowed * 0.015, 0.08)
        if observations:
            confidence += 0.03
        if source_mode == "fixture":
            confidence = min(confidence, 0.62)
        return round(max(min(confidence, 0.82), 0.0), 4)

    @staticmethod
    def _candidate_confidence(
        *,
        market: dict[str, Any],
        sources: list[dict[str, Any]],
        disagreement: dict[str, Any],
        source_mode: str,
    ) -> float:
        spread = _float(market.get("spread")) or 0.20
        liquidity = _float(market.get("liquidity")) or 0.0
        source_quality = min(sum(1 for source in sources if source.get("reliability_tier") in {"primary", "high"}) * 0.025, 0.14)
        confidence = 0.40 + source_quality + min(liquidity / 50000.0, 0.08) + max(0.0, 0.08 - spread)
        confidence -= min(float(disagreement.get("range") or 1.0), 0.20) * 0.40
        if source_mode == "fixture":
            confidence = min(confidence, 0.64)
        return round(max(min(confidence, 0.86), 0.0), 4)

    @staticmethod
    def _broad_summary(category: str, source_mode: str, observations: list[dict[str, Any]]) -> str:
        label = CATEGORY_LABELS[category]
        if source_mode == "fixture":
            return (
                f"Fixture broad {label} context uses registered source coverage and adapter-readiness observations; "
                "it does not claim fresh live news or official release evidence."
            )
        return f"Broad {label} context assembled from registered read-only sources and normalized observations."

    @staticmethod
    def _broad_events(category: str, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if observations:
            return [
                {
                    "event_type": "external_observation",
                    "metric_name": row.get("metric_name"),
                    "source_id": row.get("source_id"),
                    "as_of": row.get("as_of"),
                    "relevance": "category_data_readiness",
                }
                for row in observations
            ]
        return [
            {
                "event_type": "source_readiness",
                "category": category,
                "relevance": "registered_sources_available_but_no_live_context_fetch",
            }
        ]

    @staticmethod
    def _broad_uncertainty(source_mode: str, observations: list[dict[str, Any]]) -> str:
        if source_mode == "fixture":
            return "Fixture mode validates context contracts and source selection only; live evidence remains uncollected."
        if not observations:
            return "No normalized external observations were available for this category at run time."
        return "Context depends on registered source freshness and downstream candidate-specific evidence."

    @staticmethod
    def _candidate_summary(market: dict[str, Any], disagreement: dict[str, Any], source_mode: str) -> str:
        question = str(market.get("question") or "Untitled market")
        status = disagreement.get("status", "unknown")
        if source_mode == "fixture":
            return (
                f"Bet-specific fixture context for '{question}' was requested because the market passed relevance gates. "
                f"Model disagreement is {status}; live source evidence is still pending."
            )
        return f"Bet-specific context for '{question}' with model disagreement marked {status}."

    @staticmethod
    def _candidate_events(market: dict[str, Any], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        question = str(market.get("question") or "").lower()
        events = [
            {
                "event_type": "market_resolution_check",
                "resolution_criteria_present": bool(market.get("resolution_criteria")),
                "end_time": market.get("end_time"),
                "relevance": "resolution_risk",
            },
            {
                "event_type": "microstructure_check",
                "spread": market.get("spread"),
                "liquidity": market.get("liquidity"),
                "relevance": "liquidity_and_entry_quality",
            },
        ]
        if any(term in question for term in ("cpi", "inflation", "jobs", "gdp", "rate")):
            events.append({"event_type": "macro_release_calendar_needed", "relevance": "official_release_timing"})
        if any(term in question for term in ("election", "senate", "deadline", "certification", "vote")):
            events.append({"event_type": "political_calendar_needed", "relevance": "institutional_timing"})
        if any(term in question for term in ("close", "nvda", "stock", "tariff", "trade", "earnings")):
            events.append({"event_type": "market_close_or_trade_catalyst_needed", "relevance": "official_market_or_filing_timing"})
        ev_rows = [row for row in outputs if row.get("model_family") == "portfolio_ev_risk"]
        if ev_rows:
            features = ev_rows[0].get("features", {})
            events.append({"event_type": "portfolio_ev_check", "edge": features.get("edge"), "relevance": "decision_agent_input"})
        return events

    @staticmethod
    def _candidate_uncertainty(market: dict[str, Any], disagreement: dict[str, Any], source_mode: str) -> str:
        parts = []
        if source_mode == "fixture":
            parts.append("live news, official releases, and social/expert reaction are not fetched in fixture mode")
        if float(disagreement.get("range") or 1.0) > 0.08:
            parts.append("model families do not fully agree")
        if not market.get("resolution_criteria"):
            parts.append("resolution criteria are missing")
        if not parts:
            parts.append("remaining uncertainty is source freshness and event timing")
        return "; ".join(parts) + "."

    @staticmethod
    def _candidate_invalidation_triggers(market: dict[str, Any]) -> list[str]:
        triggers = [
            "official source contradicts the market premise",
            "new evidence changes event timing or eligibility",
            "spread/liquidity deteriorates before paper entry",
            "model disagreement widens after refresh",
        ]
        if "close" in str(market.get("question") or "").lower():
            triggers.append("official close price source differs from assumed threshold source")
        if "deadline" in str(market.get("question") or "").lower():
            triggers.append("institutional deadline or rule interpretation changes")
        return triggers

    @staticmethod
    def _has_high_reliability_source(sources: list[dict[str, Any]]) -> bool:
        return any(source.get("reliability_tier") in {"primary", "high"} for source in sources)

    @staticmethod
    def _relevance_score(market: dict[str, Any], outputs: list[dict[str, Any]]) -> float:
        liquidity = _float(market.get("liquidity")) or 0.0
        spread = _float(market.get("spread")) or 0.25
        probabilities = [float(row["probability"]) for row in outputs if row.get("probability") is not None]
        disagreement = _candidate_disagreement(outputs)
        fair = _model_probability(outputs, "portfolio_ev_risk")
        market_price = _model_probability(outputs, "market_implied_probability")
        edge = abs((fair or 0.5) - (market_price or 0.5))
        score = min(liquidity / 10000.0, 0.35) + max(0.0, 0.12 - spread) + edge
        score += max(0.0, 0.16 - float(disagreement.get("range") or 1.0))
        if probabilities:
            score += 0.05
        return round(score, 6)


def _candidate_disagreement(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outputs:
        disagreement = row.get("disagreement")
        if isinstance(disagreement, dict) and disagreement.get("range") is not None:
            return disagreement
    probabilities = [float(row["probability"]) for row in outputs if row.get("probability") is not None]
    if not probabilities:
        return {"range": 1.0, "status": "missing", "modelCount": 0}
    range_value = max(probabilities) - min(probabilities)
    return {
        "range": round(range_value, 4),
        "status": "low" if range_value <= 0.08 else "medium" if range_value <= 0.16 else "high",
        "modelCount": len(probabilities),
    }


def _model_probability(outputs: list[dict[str, Any]], family: str) -> float | None:
    for row in outputs:
        if row.get("model_family") == family and row.get("probability") is not None:
            return float(row["probability"])
    return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
