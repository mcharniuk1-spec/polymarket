from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .research_scope import ACTIVE_CATEGORIES, RELIABILITY_LABELS


SCHEMA_VERSION = 1
DECISIONS = {"reject", "watchlist", "paper_bet"}
PAPER_BET_STATUSES = {"open", "resolved", "cancelled"}
OUTCOME_RESULTS = {"win", "loss", "push"}
LESSON_TYPES = {"win_review", "loss_review", "calibration_update", "risk_control"}
MODEL_FAMILIES = {
    "market_implied_probability",
    "liquidity_microstructure",
    "base_rate_event_history",
    "bayesian_consensus",
    "news_catalyst_sentiment",
    "statistical_ml_probability",
    "portfolio_ev_risk",
}
SOURCE_TYPES = {"official", "market_data", "news", "expert_commentary", "social", "low_reliability"}


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_id(*parts: object) -> str:
    encoded = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def reliability_label(confidence: float, *, strong_evidence: bool = False, model_agreement: bool = False) -> str:
    if confidence > RELIABILITY_LABELS["reliable"]["min_confidence"] and strong_evidence and model_agreement:
        return "reliable"
    if confidence >= RELIABILITY_LABELS["possible/probable"]["min_confidence"]:
        return "possible/probable"
    return "unreliable/reject"


def validation_errors(payload: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    return [f"missing required field: {field_name}" for field_name in required if payload.get(field_name) in {None, ""}]


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    name: str
    source_type: str
    category: str
    reliability_tier: str
    access_policy: str
    freshness_sla_minutes: int
    url: str | None = None
    notes: str | None = None
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(self.to_dict(), ("source_id", "name", "source_type", "category", "reliability_tier"))
        if self.source_type not in SOURCE_TYPES:
            errors.append(f"invalid source_type: {self.source_type}")
        if self.category not in (*ACTIVE_CATEGORIES, "global", "polymarket"):
            errors.append(f"invalid category: {self.category}")
        if self.freshness_sla_minutes <= 0:
            errors.append("freshness_sla_minutes must be positive")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketSnapshot:
    snapshot_id: str
    run_id: str
    market_id: str
    question: str
    category: str
    observed_at: str
    fetched_at: str
    condition_id: str | None = None
    active: bool = True
    closed: bool = False
    outcomes: list[str] = field(default_factory=list)
    outcome_prices: list[float] = field(default_factory=list)
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    liquidity: float | None = None
    volume_24h: float | None = None
    rules_summary: str | None = None
    resolution_criteria: str | None = None
    end_time: str | None = None
    time_to_resolution_hours: float | None = None
    source_url: str | None = None
    raw_ref: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("snapshot_id", "run_id", "market_id", "question", "category", "observed_at", "fetched_at"),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        for price in self.outcome_prices:
            if not 0.0 <= price <= 1.0:
                errors.append(f"outcome price must be between 0 and 1: {price}")
        if self.spread is not None and self.spread < 0:
            errors.append("spread cannot be negative")
        if self.liquidity is not None and self.liquidity < 0:
            errors.append("liquidity cannot be negative")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderBookSnapshot:
    snapshot_id: str
    run_id: str
    market_id: str
    token_id: str
    observed_at: str
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    bid_depth: float
    ask_depth: float
    bids: list[dict[str, float]]
    asks: list[dict[str, float]]
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(self.to_dict(), ("snapshot_id", "run_id", "market_id", "token_id", "observed_at"))
        if self.spread is not None and self.spread < 0:
            errors.append("spread cannot be negative")
        if self.bid_depth < 0 or self.ask_depth < 0:
            errors.append("order-book depth cannot be negative")
        for side_name, rows in (("bid", self.bids), ("ask", self.asks)):
            for row in rows:
                price = row.get("price")
                size = row.get("size")
                if price is None or not 0.0 <= price <= 1.0:
                    errors.append(f"{side_name} price must be between 0 and 1")
                if size is None or size < 0:
                    errors.append(f"{side_name} size cannot be negative")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalObservation:
    observation_id: str
    source_id: str
    category: str
    observed_at: str
    metric_name: str
    metric_value: float | None
    as_of: str | None = None
    unit: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(self.to_dict(), ("observation_id", "source_id", "category", "observed_at", "metric_name"))
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextReport:
    report_id: str
    run_id: str
    category: str
    scope: str
    created_at: str
    summary: str
    key_events: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    uncertainty: str
    confidence: float
    reliability: str
    market_relevance: list[str]
    invalidation_triggers: list[str]
    candidate_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("report_id", "run_id", "category", "scope", "created_at", "summary", "uncertainty", "reliability"),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        if self.scope not in {"broad_category", "bet_specific"}:
            errors.append(f"invalid scope: {self.scope}")
        if self.scope == "bet_specific" and not self.candidate_id:
            errors.append("bet_specific reports require candidate_id")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
        if self.reliability not in RELIABILITY_LABELS:
            errors.append(f"invalid reliability: {self.reliability}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelOutput:
    output_id: str
    run_id: str
    candidate_id: str
    market_id: str
    category: str
    model_family: str
    probability: float | None
    confidence: float
    evidence_quality: str
    features: dict[str, Any]
    disagreement: dict[str, Any]
    gaps: list[str]
    reject_flags: list[str]
    created_at: str
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("output_id", "run_id", "candidate_id", "market_id", "category", "model_family", "created_at"),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        if self.model_family not in MODEL_FAMILIES:
            errors.append(f"invalid model_family: {self.model_family}")
        if self.probability is not None and not 0.0 <= self.probability <= 1.0:
            errors.append("probability must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionSignal:
    decision_id: str
    run_id: str
    candidate_id: str
    market_id: str
    category: str
    decision: str
    confidence: float
    reliability: str
    edge: float
    stake_units: float
    reasons: list[str]
    model_disagreement: dict[str, Any]
    invalidation_triggers: list[str]
    evaluation_plan: str
    created_at: str
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("decision_id", "run_id", "candidate_id", "market_id", "category", "decision", "reliability", "created_at"),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        if self.decision not in DECISIONS:
            errors.append(f"invalid decision: {self.decision}")
        if self.reliability not in RELIABILITY_LABELS:
            errors.append(f"invalid reliability: {self.reliability}")
        if self.decision != "paper_bet" and self.stake_units != 0:
            errors.append("non-paper-bet decisions must have zero stake_units")
        if self.stake_units < 0:
            errors.append("stake_units cannot be negative")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioState:
    portfolio_id: str
    run_id: str
    bankroll_units: float
    total_exposure_units: float
    max_portfolio_exposure_pct: float
    max_single_market_pct: float
    max_category_pct: float
    max_correlated_theme_pct: float
    current_drawdown_pct: float
    category_exposure: dict[str, float]
    warnings: list[str]
    created_at: str
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(self.to_dict(), ("portfolio_id", "run_id", "created_at"))
        if self.bankroll_units <= 0:
            errors.append("bankroll_units must be positive")
        if self.total_exposure_units < 0:
            errors.append("total_exposure_units cannot be negative")
        for key in ("max_portfolio_exposure_pct", "max_single_market_pct", "max_category_pct", "max_correlated_theme_pct"):
            value = getattr(self, key)
            if not 0.0 <= value <= 1.0:
                errors.append(f"{key} must be between 0 and 1")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperBet:
    paper_bet_id: str
    decision_id: str
    run_id: str
    candidate_id: str
    market_id: str
    category: str
    side: str
    entry_price: float
    stake_units: float
    opened_at: str
    status: str = "open"
    fair_probability: float | None = None
    confidence: float | None = None
    slippage_assumption: float = 0.01
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("paper_bet_id", "decision_id", "run_id", "candidate_id", "market_id", "category", "side", "opened_at", "status"),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        if self.status not in PAPER_BET_STATUSES:
            errors.append(f"invalid paper bet status: {self.status}")
        if not 0.0 < self.entry_price < 1.0:
            errors.append("entry_price must be between 0 and 1")
        if self.stake_units <= 0:
            errors.append("stake_units must be positive")
        if self.fair_probability is not None and not 0.0 <= self.fair_probability <= 1.0:
            errors.append("fair_probability must be between 0 and 1")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedOutcome:
    outcome_id: str
    paper_bet_id: str
    decision_id: str
    run_id: str
    candidate_id: str
    market_id: str
    category: str
    resolved_at: str
    result: str
    pnl_units: float
    calibration_bucket: str
    proof_url: str | None = None
    fair_probability: float | None = None
    entry_price: float | None = None
    stake_units: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            (
                "outcome_id",
                "paper_bet_id",
                "decision_id",
                "run_id",
                "candidate_id",
                "market_id",
                "category",
                "resolved_at",
                "result",
                "calibration_bucket",
            ),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        if self.result not in OUTCOME_RESULTS:
            errors.append(f"invalid outcome result: {self.result}")
        if self.fair_probability is not None and not 0.0 <= self.fair_probability <= 1.0:
            errors.append("fair_probability must be between 0 and 1")
        if self.entry_price is not None and not 0.0 < self.entry_price < 1.0:
            errors.append("entry_price must be between 0 and 1")
        if self.stake_units is not None and self.stake_units <= 0:
            errors.append("stake_units must be positive")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionNote:
    note_id: str
    decision_id: str
    run_id: str
    candidate_id: str
    market_id: str
    category: str
    created_at: str
    summary: str
    evidence: list[str]
    risks: list[str]
    evaluation_plan: str
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("note_id", "decision_id", "run_id", "candidate_id", "market_id", "category", "created_at", "summary"),
        )
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeLesson:
    lesson_id: str
    category: str
    lesson_type: str
    created_at: str
    summary: str
    source_run_id: str | None = None
    candidate_id: str | None = None
    severity: str = "info"
    evidence: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(self.to_dict(), ("lesson_id", "category", "lesson_type", "created_at", "summary"))
        if self.category not in ACTIVE_CATEGORIES:
            errors.append(f"invalid category: {self.category}")
        if self.lesson_type not in LESSON_TYPES:
            errors.append(f"invalid lesson_type: {self.lesson_type}")
        if self.severity not in {"info", "low", "medium", "high"}:
            errors.append(f"invalid severity: {self.severity}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CronRunRecord:
    run_id: str
    cycle_type: str
    scheduled_for: str
    idempotency_key: str
    status: str
    dry_run: bool
    started_at: str
    finished_at: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors = validation_errors(
            self.to_dict(),
            ("run_id", "cycle_type", "scheduled_for", "idempotency_key", "status", "started_at"),
        )
        if self.cycle_type not in {"scheduled_15m", "daily_analytics", "manual"}:
            errors.append(f"invalid cycle_type: {self.cycle_type}")
        if self.status not in {"dry_run", "running", "success", "partial", "failed", "duplicate_skipped"}:
            errors.append(f"invalid status: {self.status}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assert_valid_contract(name: str, payload: dict[str, Any], errors: list[str]) -> None:
    if errors:
        raise ValueError(f"{name} failed schema validation: {json.dumps(errors, sort_keys=True)}")
