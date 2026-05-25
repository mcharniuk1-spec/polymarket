from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agents import ACTIVE_CATEGORIES, MarketCandidate, MarketDataAgent
from .odds_math import clamp
from .source_registry import SourceRecord, SourceRegistry


@dataclass(frozen=True)
class ResearchBrief:
    category: str
    topic: str
    candidate_id: str | None
    market_title: str
    outcome: str
    actors: list[str]
    market_url: str
    settlement_notes: str
    source_coverage: dict[str, Any]
    planned_queries: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    global_context_score: float
    category_context_score: float
    bet_research_score: float
    contradiction_flags: list[str]
    staleness_flags: list[str]
    resolution_risk_flags: list[str]
    next_evidence_needed: list[str]
    conclusion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "topic": self.topic,
            "candidate_id": self.candidate_id,
            "market_title": self.market_title,
            "outcome": self.outcome,
            "actors": self.actors,
            "market_url": self.market_url,
            "settlement_notes": self.settlement_notes,
            "source_coverage": self.source_coverage,
            "planned_queries": self.planned_queries,
            "evidence_items": self.evidence_items,
            "global_context_score": self.global_context_score,
            "category_context_score": self.category_context_score,
            "bet_research_score": self.bet_research_score,
            "contradiction_flags": self.contradiction_flags,
            "staleness_flags": self.staleness_flags,
            "resolution_risk_flags": self.resolution_risk_flags,
            "next_evidence_needed": self.next_evidence_needed,
            "conclusion": self.conclusion,
        }


class BetResearchPlanner:
    """Fixture-backed research planner.

    The planner generates source plans and evidence briefs only. It does not perform
    live network fetches and cannot place or automate bets.
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self.registry = registry or SourceRegistry()
        self.registry.require_valid()

    def brief_for_candidate_id(self, candidate_id: str, *, target_count: int = 600) -> ResearchBrief:
        candidates = MarketDataAgent().load_candidates(source_mode="fixture", target_count=max(target_count, 600))
        for candidate in candidates:
            if candidate.candidate_id == candidate_id:
                return self.brief_for_candidate(candidate)
        raise ValueError(f"Unknown fixture candidate_id: {candidate_id}")

    def brief_for_candidate(self, candidate: MarketCandidate) -> ResearchBrief:
        topic = candidate.market_title
        planned_sources = self._planned_sources(candidate.category, topic)
        planned_queries = self._planned_queries(planned_sources, category=candidate.category, topic=topic, actors=candidate.actors)
        evidence_items = self._fixture_evidence(candidate)
        source_coverage = self._source_coverage(candidate.category, planned_sources)
        candidate_context = candidate.context_fields()
        scores = self._scores(source_coverage, candidate_context)
        contradiction_flags = list(candidate_context["contradiction_flags"])
        staleness_flags = list(candidate_context["staleness_flags"])
        resolution_risk_flags = list(candidate_context["resolution_risk_flags"])
        next_evidence_needed = self._next_evidence_needed(candidate.category, planned_sources, contradiction_flags, resolution_risk_flags)
        conclusion = self._conclusion(source_coverage, contradiction_flags, staleness_flags, resolution_risk_flags)
        return ResearchBrief(
            category=candidate.category,
            topic=topic,
            candidate_id=candidate.candidate_id,
            market_title=candidate.market_title,
            outcome=candidate.outcome,
            actors=candidate.actors,
            market_url=candidate.source_url,
            settlement_notes=candidate.resolution_notes,
            source_coverage=source_coverage,
            planned_queries=planned_queries,
            evidence_items=evidence_items,
            global_context_score=scores["global_context_score"],
            category_context_score=scores["category_context_score"],
            bet_research_score=scores["bet_research_score"],
            contradiction_flags=contradiction_flags,
            staleness_flags=staleness_flags,
            resolution_risk_flags=resolution_risk_flags,
            next_evidence_needed=next_evidence_needed,
            conclusion=conclusion,
        )

    def brief_for_topic(self, category: str, topic: str) -> ResearchBrief:
        if category not in ACTIVE_CATEGORIES:
            raise ValueError(f"Unknown category: {category}")
        planned_sources = self._planned_sources(category, topic)
        planned_queries = self._planned_queries(planned_sources, category=category, topic=topic, actors=[])
        source_coverage = self._source_coverage(category, planned_sources)
        scores = self._scores(source_coverage, {})
        staleness_flags = ["topic_only_no_fixture_evidence"]
        next_evidence_needed = self._next_evidence_needed(category, planned_sources, [], [])
        conclusion = self._conclusion(source_coverage, [], staleness_flags, [])
        return ResearchBrief(
            category=category,
            topic=topic,
            candidate_id=None,
            market_title=topic,
            outcome="unspecified",
            actors=[],
            market_url="",
            settlement_notes="Topic research brief; attach exact market settlement notes before paper decision.",
            source_coverage=source_coverage,
            planned_queries=planned_queries,
            evidence_items=[
                {
                    "source_id": "fixture-topic-research",
                    "source_name": "Fixture topic research planner",
                    "headline": "No live network fetch was performed; this is a source and query plan.",
                    "impact": 0.0,
                    "credibility": 0.5,
                }
            ],
            global_context_score=scores["global_context_score"],
            category_context_score=scores["category_context_score"],
            bet_research_score=scores["bet_research_score"],
            contradiction_flags=[],
            staleness_flags=staleness_flags,
            resolution_risk_flags=[],
            next_evidence_needed=next_evidence_needed,
            conclusion=conclusion,
        )

    def _planned_sources(self, category: str, topic: str) -> list[SourceRecord]:
        searched = self.registry.search(topic, category=category, allowed_only=False, limit=14)
        required = self.registry.for_category(category, include_global=True, include_polymarket=True, allowed_only=False)
        by_id = {source.id: source for source in searched}
        for source in required:
            by_id.setdefault(source.id, source)
        return sorted(by_id.values(), key=lambda source: (source.category not in {category, "polymarket", "global"}, source.category, source.id))

    def _planned_queries(
        self,
        sources: list[SourceRecord],
        *,
        category: str,
        topic: str,
        actors: list[str],
    ) -> list[dict[str, Any]]:
        actor_text = ", ".join(actors)
        queries = []
        for source in sources:
            queries.append(
                {
                    "source_id": source.id,
                    "source_name": source.name,
                    "category": source.category,
                    "access": source.access,
                    "reliability_tier": source.reliability_tier,
                    "allowed_by_default": source.allowed_by_default,
                    "query": self.registry.render_query(source, topic=topic, category=category, actors=actor_text),
                    "live_fetch": False,
                }
            )
        return queries

    @staticmethod
    def _fixture_evidence(candidate: MarketCandidate) -> list[dict[str, Any]]:
        evidence = []
        for item in candidate.news_items:
            evidence.append(
                {
                    "source_id": str(item.get("source", "fixture-news")),
                    "source_name": str(item.get("source", "fixture-news")),
                    "published_at": item.get("time", ""),
                    "headline": item.get("headline", ""),
                    "impact": float(item.get("impact", 0.0)),
                    "credibility": float(item.get("credibility", 0.5)),
                    "live_fetch": False,
                }
            )
        return evidence

    def _source_coverage(self, category: str, planned_sources: list[SourceRecord]) -> dict[str, Any]:
        category_sources = [source for source in planned_sources if source.category == category]
        global_sources = [source for source in planned_sources if source.category == "global"]
        polymarket_sources = [source for source in planned_sources if source.category == "polymarket"]
        allowed_sources = [source for source in planned_sources if source.allowed_by_default]
        high_sources = [source for source in planned_sources if source.is_high_reliability]
        primary_category_sources = [source for source in category_sources if source.reliability_tier == "primary"]
        return {
            "planned_source_count": len(planned_sources),
            "category_source_count": len(category_sources),
            "global_source_count": len(global_sources),
            "polymarket_source_count": len(polymarket_sources),
            "default_allowed_source_count": len(allowed_sources),
            "high_reliability_source_count": len(high_sources),
            "primary_category_source_count": len(primary_category_sources),
            "not_enabled_by_default": [
                source.id for source in planned_sources if not source.allowed_by_default
            ],
            "fixture_backed_only": True,
        }

    @staticmethod
    def _scores(source_coverage: dict[str, Any], candidate_context: dict[str, Any]) -> dict[str, float]:
        planned = max(int(source_coverage["planned_source_count"]), 1)
        allowed_ratio = float(source_coverage["default_allowed_source_count"]) / planned
        high_ratio = float(source_coverage["high_reliability_source_count"]) / planned
        primary_ratio = clamp(float(source_coverage["primary_category_source_count"]) / 3.0, 0.0, 1.0)
        global_ratio = clamp(float(source_coverage["global_source_count"]) / 4.0, 0.0, 1.0)
        base_global = clamp((global_ratio * 0.45) + (high_ratio * 0.35) + (allowed_ratio * 0.20), 0.0, 1.0)
        base_category = clamp((primary_ratio * 0.48) + (high_ratio * 0.32) + (allowed_ratio * 0.20), 0.0, 1.0)
        candidate_bonus = float(candidate_context.get("bet_research_score", 0.0)) * 0.25
        return {
            "global_context_score": round(base_global, 4),
            "category_context_score": round(base_category, 4),
            "bet_research_score": round(clamp(((base_global + base_category) / 2.0) + candidate_bonus, 0.0, 1.0), 4),
        }

    @staticmethod
    def _next_evidence_needed(
        category: str,
        planned_sources: list[SourceRecord],
        contradiction_flags: list[str],
        resolution_risk_flags: list[str],
    ) -> list[str]:
        needs = []
        primary_sources = [source for source in planned_sources if source.category == category and source.reliability_tier == "primary"]
        if not primary_sources:
            needs.append("find at least one primary category source")
        if contradiction_flags:
            needs.append("resolve contradictory fixture/context evidence")
        if resolution_risk_flags:
            needs.append("review exact settlement wording against primary source")
        needs.append("fetch live source evidence only after access and terms are approved")
        return needs

    @staticmethod
    def _conclusion(
        source_coverage: dict[str, Any],
        contradiction_flags: list[str],
        staleness_flags: list[str],
        resolution_risk_flags: list[str],
    ) -> str:
        if source_coverage["primary_category_source_count"] == 0:
            return "NEEDS_PRIMARY_SOURCE"
        if contradiction_flags or len(resolution_risk_flags) >= 2:
            return "WATCHLIST_RESEARCH"
        if staleness_flags and staleness_flags != ["fixture_context_not_live"]:
            return "RESEARCH_PLAN_ONLY"
        return "RESEARCH_READY"
