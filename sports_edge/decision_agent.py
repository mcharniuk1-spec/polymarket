from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model_scoring import model_outputs_by_candidate
from .research_scope import ACTIVE_CATEGORIES
from .schemas import DecisionSignal, PortfolioState, reliability_label, stable_id


@dataclass(frozen=True)
class PortfolioRules:
    bankroll_units: float = 100.0
    max_portfolio_exposure_pct: float = 0.25
    max_single_market_pct: float = 0.03
    max_category_pct: float = 0.10
    max_correlated_theme_pct: float = 0.06
    min_edge: float = 0.04
    min_confidence: float = 0.55
    max_spread: float = 0.08
    min_liquidity: float = 1000.0
    max_disagreement: float = 0.12
    fractional_kelly: float = 0.25


class DecisionAgent:
    """Paper-only portfolio and decision gate.

    This agent produces reject/watchlist/paper_bet records only. It does not execute trades.
    """

    def __init__(self, rules: PortfolioRules | None = None) -> None:
        self.rules = rules or PortfolioRules()

    def decide(
        self,
        *,
        run_id: str,
        data_payload: dict[str, Any],
        model_outputs: list[Any],
        context_reports: list[Any] | None = None,
        created_at: str,
    ) -> tuple[list[DecisionSignal], PortfolioState]:
        markets = data_payload.get("marketSnapshots", [])
        outputs_by_candidate = model_outputs_by_candidate(model_outputs)
        context_by_candidate = _context_by_candidate(context_reports or [])
        decisions: list[DecisionSignal] = []
        exposure_by_category = {category: 0.0 for category in ACTIVE_CATEGORIES}
        total_exposure = 0.0
        warnings: list[str] = []

        for market in markets:
            candidate_id = str(market.get("market_id"))
            category = str(market.get("category"))
            candidate_outputs = outputs_by_candidate.get(candidate_id, [])
            decision, total_exposure = self._decision_for_market(
                run_id=run_id,
                market=market,
                model_outputs=candidate_outputs,
                context_reports=context_by_candidate.get(candidate_id, []),
                created_at=created_at,
                total_exposure=total_exposure,
                category_exposure=exposure_by_category.get(category, 0.0),
            )
            decisions.append(decision)
            if decision.decision == "paper_bet":
                exposure_by_category[category] = round(exposure_by_category.get(category, 0.0) + decision.stake_units, 4)

        if not any(decision.decision == "paper_bet" for decision in decisions):
            warnings.append("No paper bet passed all evidence, edge, liquidity, spread, and disagreement gates.")
        portfolio = PortfolioState(
            portfolio_id=stable_id(run_id, "portfolio"),
            run_id=run_id,
            bankroll_units=self.rules.bankroll_units,
            total_exposure_units=round(total_exposure, 4),
            max_portfolio_exposure_pct=self.rules.max_portfolio_exposure_pct,
            max_single_market_pct=self.rules.max_single_market_pct,
            max_category_pct=self.rules.max_category_pct,
            max_correlated_theme_pct=self.rules.max_correlated_theme_pct,
            current_drawdown_pct=0.0,
            category_exposure=exposure_by_category,
            warnings=warnings,
            created_at=created_at,
        )
        return decisions, portfolio

    def _decision_for_market(
        self,
        *,
        run_id: str,
        market: dict[str, Any],
        model_outputs: list[dict[str, Any]],
        context_reports: list[dict[str, Any]],
        created_at: str,
        total_exposure: float,
        category_exposure: float,
    ) -> tuple[DecisionSignal, float]:
        candidate_id = str(market.get("market_id"))
        market_price = _model_probability(model_outputs, "market_implied_probability")
        fair_probability = _model_probability(model_outputs, "portfolio_ev_risk")
        if market_price is None:
            market_price = _market_price(market)
        if fair_probability is None:
            fair_probability = market_price
        edge = round(fair_probability - market_price, 4)
        disagreement = _candidate_disagreement(model_outputs)
        reject_flags = sorted({flag for row in model_outputs for flag in row.get("reject_flags", []) if flag != "statistical_ml_unavailable"})
        confidence = _decision_confidence(model_outputs, disagreement, reject_flags)
        if context_reports:
            context_confidence = sum(float(row.get("confidence") or 0.0) for row in context_reports) / len(context_reports)
            confidence = max(min((confidence * 0.82) + (context_confidence * 0.18), 1.0), 0.0)
        hard_reasons = _hard_reject_reasons(market, disagreement, reject_flags, self.rules)
        reasons = _base_reasons(market, edge, confidence, disagreement, reject_flags)
        context_reason = _context_reason(context_reports)
        if context_reason:
            reasons.append(context_reason)
        decision = "watchlist"
        stake_units = 0.0
        if hard_reasons:
            decision = "reject"
            reasons = hard_reasons + reasons
        elif edge < self.rules.min_edge:
            decision = "watchlist"
            reasons.insert(0, f"Edge {edge:.2%} is below paper-bet threshold {self.rules.min_edge:.2%}.")
        elif confidence < self.rules.min_confidence:
            decision = "watchlist"
            reasons.insert(0, f"Confidence {confidence:.2%} is below paper-bet threshold {self.rules.min_confidence:.2%}.")
        else:
            stake_units = self._stake_units(
                fair_probability=fair_probability,
                market_price=market_price,
                confidence=confidence,
                total_exposure=total_exposure,
                category_exposure=category_exposure,
            )
            if stake_units > 0:
                decision = "paper_bet"
                total_exposure = round(total_exposure + stake_units, 4)
                reasons.insert(0, "Paper bet passed edge, confidence, spread, liquidity, disagreement, and portfolio caps.")
            else:
                decision = "watchlist"
                reasons.insert(0, "Portfolio caps or fractional-Kelly sizing reduced stake to zero.")
        reliability = reliability_label(
            confidence,
            strong_evidence=decision == "paper_bet" and not reject_flags,
            model_agreement=disagreement.get("range", 1.0) <= self.rules.max_disagreement,
        )
        if decision == "reject":
            reliability = "unreliable/reject"
        signal = DecisionSignal(
            decision_id=stable_id(run_id, candidate_id, "decision"),
            run_id=run_id,
            candidate_id=candidate_id,
            market_id=str(market.get("market_id")),
            category=str(market.get("category")),
            decision=decision,
            confidence=round(confidence, 4),
            reliability=reliability,
            edge=edge,
            stake_units=stake_units,
            reasons=reasons[:8],
            model_disagreement=disagreement,
            invalidation_triggers=[
                "spread widens beyond limit",
                "liquidity drops below limit",
                "resolution criteria becomes ambiguous",
                "new context invalidates base-rate or catalyst assumptions",
            ]
            + _context_invalidation_triggers(context_reports),
            evaluation_plan="Compare final resolution to paper decision, fair probability, market price, and model disagreement bucket.",
            created_at=created_at,
        )
        return signal, total_exposure

    def _stake_units(
        self,
        *,
        fair_probability: float,
        market_price: float,
        confidence: float,
        total_exposure: float,
        category_exposure: float,
    ) -> float:
        bankroll = self.rules.bankroll_units
        max_portfolio_units = bankroll * self.rules.max_portfolio_exposure_pct
        max_market_units = bankroll * self.rules.max_single_market_pct
        max_category_units = bankroll * self.rules.max_category_pct
        remaining_portfolio = max(max_portfolio_units - total_exposure, 0.0)
        remaining_category = max(max_category_units - category_exposure, 0.0)
        if market_price <= 0.0 or market_price >= 1.0:
            return 0.0
        edge = fair_probability - market_price
        if edge <= 0:
            return 0.0
        kelly_fraction = edge / max(1.0 - market_price, 0.01)
        raw_units = bankroll * kelly_fraction * self.rules.fractional_kelly * confidence
        stake = min(raw_units, max_market_units, remaining_portfolio, remaining_category)
        return round(max(stake, 0.0), 4)


def _model_probability(model_outputs: list[dict[str, Any]], family: str) -> float | None:
    for row in model_outputs:
        if row.get("model_family") == family and row.get("probability") is not None:
            return float(row["probability"])
    return None


def _context_by_candidate(context_reports: list[Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in context_reports:
        payload = row.to_dict() if hasattr(row, "to_dict") else row
        if not isinstance(payload, dict) or payload.get("scope") != "bet_specific":
            continue
        candidate_id = payload.get("candidate_id")
        if candidate_id:
            grouped.setdefault(str(candidate_id), []).append(payload)
    return grouped


def _context_reason(context_reports: list[dict[str, Any]]) -> str | None:
    if not context_reports:
        return None
    confidence = sum(float(row.get("confidence") or 0.0) for row in context_reports) / len(context_reports)
    reliability = sorted({str(row.get("reliability")) for row in context_reports if row.get("reliability")})
    return (
        f"Bet-specific context available with average confidence {confidence:.2%} "
        f"and reliability labels: {', '.join(reliability)}."
    )


def _context_invalidation_triggers(context_reports: list[dict[str, Any]]) -> list[str]:
    triggers: list[str] = []
    for row in context_reports:
        for trigger in row.get("invalidation_triggers", []):
            if trigger not in triggers:
                triggers.append(str(trigger))
    return triggers[:4]


def _candidate_disagreement(model_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    for row in model_outputs:
        disagreement = row.get("disagreement")
        if isinstance(disagreement, dict) and disagreement.get("range") is not None:
            return disagreement
    return {"range": 1.0, "status": "missing", "modelCount": 0}


def _decision_confidence(
    model_outputs: list[dict[str, Any]],
    disagreement: dict[str, Any],
    reject_flags: list[str],
) -> float:
    confidences = [float(row.get("confidence") or 0.0) for row in model_outputs if row.get("model_family") != "statistical_ml_probability"]
    base = sum(confidences) / len(confidences) if confidences else 0.0
    disagreement_penalty = min(float(disagreement.get("range") or 1.0), 0.35)
    reject_penalty = min(len(reject_flags) * 0.08, 0.32)
    return max(min(base - disagreement_penalty - reject_penalty + 0.08, 1.0), 0.0)


def _hard_reject_reasons(
    market: dict[str, Any],
    disagreement: dict[str, Any],
    reject_flags: list[str],
    rules: PortfolioRules,
) -> list[str]:
    reasons = []
    spread = _float(market.get("spread"))
    liquidity = _float(market.get("liquidity")) or 0.0
    if "unclear_resolution_criteria" in reject_flags:
        reasons.append("Resolution criteria are missing or unclear.")
    if spread is not None and spread > rules.max_spread:
        reasons.append(f"Spread {spread:.2%} exceeds max spread {rules.max_spread:.2%}.")
    if liquidity < rules.min_liquidity:
        reasons.append(f"Liquidity {liquidity:.0f} is below minimum {rules.min_liquidity:.0f}.")
    if float(disagreement.get("range") or 1.0) > rules.max_disagreement:
        reasons.append(
            f"Model disagreement range {float(disagreement.get('range') or 1.0):.2%} exceeds max {rules.max_disagreement:.2%}."
        )
    return reasons


def _base_reasons(
    market: dict[str, Any],
    edge: float,
    confidence: float,
    disagreement: dict[str, Any],
    reject_flags: list[str],
) -> list[str]:
    reasons = [
        f"Estimated edge vs market price is {edge:.2%}.",
        f"Decision confidence is {confidence:.2%}.",
        f"Model disagreement is {float(disagreement.get('range') or 0.0):.2%} ({disagreement.get('status', 'unknown')}).",
    ]
    if reject_flags:
        reasons.append(f"Reject/watchlist flags: {', '.join(reject_flags)}.")
    if market.get("resolution_criteria"):
        reasons.append("Resolution criteria are present in the normalized market snapshot.")
    return reasons


def _market_price(market: dict[str, Any]) -> float:
    prices = market.get("outcome_prices")
    if isinstance(prices, list) and prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return 0.5
    return 0.5


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
