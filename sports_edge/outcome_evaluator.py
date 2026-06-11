from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import DecisionNote, KnowledgeLesson, PaperBet, ResolvedOutcome, iso_now, stable_id
from .state_store import JsonStateStore


FIXTURE_RESULTS = {
    "macro-cpi-june": "yes",
    "politics-election-cert": "no",
    "stocks-nvda-close": "no",
}


def evaluate_previous_paper_bets(
    *,
    store: JsonStateStore,
    current_run_id: str,
    as_of: str,
    source_mode: str,
) -> dict[str, Any]:
    """Evaluate stored prior paper bets without fetching live data or executing trades."""

    prior_payloads = _prior_daily_payloads(store=store, current_run_id=current_run_id)
    paper_bets: list[PaperBet] = []
    resolved: list[ResolvedOutcome] = []
    lessons: list[KnowledgeLesson] = []
    warnings: list[str] = []

    for payload in prior_payloads:
        for paper_bet, market, decision, model_outputs in paper_bets_from_payload(payload):
            paper_bets.append(paper_bet)
            outcome = _resolve_paper_bet(
                paper_bet=paper_bet,
                market=market,
                decision=decision,
                model_outputs=model_outputs,
                as_of=as_of,
                source_mode=source_mode,
            )
            if outcome is None:
                continue
            resolved.append(outcome)
            lesson = _lesson_from_outcome(outcome, paper_bet)
            if lesson:
                lessons.append(lesson)

    if source_mode != "fixture":
        warnings.append("Live outcome resolution uses stored closed-market snapshots only; no live resolution fetch occurred.")
    if not paper_bets:
        status = "no_prior_paper_bets"
    elif not resolved:
        status = "no_new_resolutions"
    else:
        status = "resolved_outcomes_available"

    performance = _performance_summary(paper_bets, resolved)
    return {
        "ok": True,
        "status": status,
        "asOf": as_of,
        "sourceMode": source_mode,
        "evaluatedPaperBetCount": len(paper_bets),
        "resolvedOutcomeCount": len(resolved),
        "openPaperBetCount": max(len(paper_bets) - len(resolved), 0),
        "paperTradingHistory": [row.to_dict() for row in paper_bets],
        "resolvedOutcomes": [row.to_dict() for row in resolved],
        "knowledgeLessons": [row.to_dict() for row in lessons],
        "calibration": performance["calibration"],
        "drawdown": performance["drawdown"],
        "metrics": performance["metrics"],
        "warnings": warnings,
    }


def paper_bets_from_payload(payload: dict[str, Any]) -> list[tuple[PaperBet, dict[str, Any], dict[str, Any], list[dict[str, Any]]]]:
    markets = {row.get("market_id"): row for row in payload.get("dataAgent", {}).get("marketSnapshots", [])}
    model_outputs = payload.get("modelOutputs", [])
    rows = []
    for decision in payload.get("decisionSignals", []):
        if decision.get("decision") != "paper_bet":
            continue
        market_id = str(decision.get("market_id") or decision.get("candidate_id"))
        market = markets.get(market_id, {})
        paper_bet = paper_bet_from_decision(decision, model_outputs=model_outputs)
        if paper_bet:
            rows.append((paper_bet, market, decision, model_outputs))
    return rows


def paper_bet_from_decision(decision: dict[str, Any], *, model_outputs: list[dict[str, Any]]) -> PaperBet | None:
    stake_units = _float(decision.get("stake_units")) or 0.0
    if decision.get("decision") != "paper_bet" or stake_units <= 0:
        return None
    decision_id = str(decision.get("decision_id"))
    candidate_id = str(decision.get("candidate_id"))
    entry_price = _model_probability(model_outputs, candidate_id, "market_implied_probability")
    fair_probability = _model_probability(model_outputs, candidate_id, "portfolio_ev_risk")
    if entry_price is None:
        entry_price = max(min(0.5 - float(decision.get("edge") or 0.0), 0.99), 0.01)
    return PaperBet(
        paper_bet_id=stable_id(decision_id, "yes"),
        decision_id=decision_id,
        run_id=str(decision.get("run_id")),
        candidate_id=candidate_id,
        market_id=str(decision.get("market_id")),
        category=str(decision.get("category")),
        side="Yes",
        entry_price=round(entry_price, 4),
        fair_probability=round(fair_probability, 4) if fair_probability is not None else None,
        confidence=_float(decision.get("confidence")),
        stake_units=round(stake_units, 4),
        opened_at=str(decision.get("created_at")),
        status="open",
        payload={"decision": decision},
    )


def decision_notes_from_signals(decisions: list[Any], *, created_at: str) -> list[DecisionNote]:
    notes: list[DecisionNote] = []
    for row in decisions:
        decision = row.to_dict() if hasattr(row, "to_dict") else row
        reasons = [str(item) for item in decision.get("reasons", [])]
        risks = [str(item) for item in decision.get("invalidation_triggers", [])]
        summary = f"{decision.get('decision')} for {decision.get('market_id')}: " + (reasons[0] if reasons else "No reason recorded.")
        notes.append(
            DecisionNote(
                note_id=stable_id(decision.get("decision_id"), "note"),
                decision_id=str(decision.get("decision_id")),
                run_id=str(decision.get("run_id")),
                candidate_id=str(decision.get("candidate_id")),
                market_id=str(decision.get("market_id")),
                category=str(decision.get("category")),
                created_at=created_at,
                summary=summary,
                evidence=reasons[:6],
                risks=risks[:6],
                evaluation_plan=str(decision.get("evaluation_plan") or "Evaluate after resolution."),
                payload={"decision": decision},
            )
        )
    return notes


def _prior_daily_payloads(*, store: JsonStateStore, current_run_id: str) -> list[dict[str, Any]]:
    rows = []
    seen_run_ids: set[str] = set()
    for entry in store.list_json("cron_runs"):
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        cron = payload.get("cronRun", {})
        run_id = str(cron.get("run_id") or "")
        if run_id == current_run_id or run_id in seen_run_ids:
            continue
        if cron.get("cycle_type") != "daily_analytics":
            continue
        seen_run_ids.add(run_id)
        rows.append(payload)
    rows.sort(key=lambda payload: str(payload.get("cronRun", {}).get("scheduled_for") or ""))
    return rows


def _resolve_paper_bet(
    *,
    paper_bet: PaperBet,
    market: dict[str, Any],
    decision: dict[str, Any],
    model_outputs: list[dict[str, Any]],
    as_of: str,
    source_mode: str,
) -> ResolvedOutcome | None:
    if not _is_due(market, as_of):
        return None
    resolution = _stored_resolution_result(market)
    resolution_mode = "stored_market_snapshot"
    if resolution is None and source_mode == "fixture":
        resolution = FIXTURE_RESULTS.get(paper_bet.market_id)
        resolution_mode = "fixture_only"
    if resolution not in {"yes", "no"}:
        return None
    result = "win" if (paper_bet.side.lower() == "yes" and resolution == "yes") else "loss"
    pnl = _pnl_for_binary_share(paper_bet.entry_price, paper_bet.stake_units, result)
    fair_probability = paper_bet.fair_probability
    return ResolvedOutcome(
        outcome_id=stable_id(paper_bet.paper_bet_id, resolution, market.get("end_time")),
        paper_bet_id=paper_bet.paper_bet_id,
        decision_id=paper_bet.decision_id,
        run_id=paper_bet.run_id,
        candidate_id=paper_bet.candidate_id,
        market_id=paper_bet.market_id,
        category=paper_bet.category,
        resolved_at=str(market.get("end_time") or as_of),
        result=result,
        proof_url=str(market.get("source_url") or "fixture://resolution"),
        pnl_units=pnl,
        calibration_bucket=_calibration_bucket(fair_probability or decision.get("confidence")),
        fair_probability=fair_probability,
        entry_price=paper_bet.entry_price,
        stake_units=paper_bet.stake_units,
        payload={
            "resolvedSide": resolution,
            "resolutionMode": resolution_mode,
            "market": market,
            "decision": decision,
            "modelProbabilities": [
                {
                    "model_family": row.get("model_family"),
                    "probability": row.get("probability"),
                    "confidence": row.get("confidence"),
                }
                for row in model_outputs
                if row.get("candidate_id") == paper_bet.candidate_id
            ],
        },
    )


def _lesson_from_outcome(outcome: ResolvedOutcome, paper_bet: PaperBet) -> KnowledgeLesson | None:
    if outcome.result == "win":
        lesson_type = "win_review"
        severity = "low"
        summary = f"Paper bet {paper_bet.market_id} resolved WIN; preserve evidence trail and calibration bucket {outcome.calibration_bucket}."
        action_items = ["Check whether the edge came from repeatable evidence or fixture-only assumptions."]
    elif outcome.result == "loss":
        lesson_type = "loss_review"
        severity = "medium"
        summary = f"Paper bet {paper_bet.market_id} resolved LOSS; review model edge, context evidence, and liquidity assumptions."
        action_items = [
            "Compare market-implied, portfolio EV, and context assumptions at decision time.",
            "Mark similar future markets for stricter evidence or smaller sizing until calibration improves.",
        ]
    else:
        return None
    return KnowledgeLesson(
        lesson_id=stable_id(outcome.outcome_id, lesson_type),
        category=outcome.category,
        lesson_type=lesson_type,
        created_at=iso_now(),
        source_run_id=outcome.run_id,
        candidate_id=outcome.candidate_id,
        severity=severity,
        summary=summary,
        evidence=[
            f"result={outcome.result}",
            f"pnl_units={outcome.pnl_units}",
            f"entry_price={outcome.entry_price}",
            f"fair_probability={outcome.fair_probability}",
        ],
        action_items=action_items,
        payload={"resolvedOutcome": outcome.to_dict(), "paperBet": paper_bet.to_dict()},
    )


def _performance_summary(paper_bets: list[PaperBet], outcomes: list[ResolvedOutcome]) -> dict[str, Any]:
    total_staked = round(sum(row.stake_units for row in paper_bets), 4)
    total_pnl = round(sum(row.pnl_units for row in outcomes), 4)
    wins = sum(1 for row in outcomes if row.result == "win")
    losses = sum(1 for row in outcomes if row.result == "loss")
    ending_bankroll = round(100.0 + total_pnl, 4)
    drawdown_pct = round(max(0.0, -total_pnl) / 100.0, 4)
    return {
        "metrics": {
            "paperBetCount": len(paper_bets),
            "resolvedOutcomeCount": len(outcomes),
            "wins": wins,
            "losses": losses,
            "winRate": round(wins / len(outcomes), 4) if outcomes else 0.0,
            "totalStakedUnits": total_staked,
            "totalPnlUnits": total_pnl,
            "simulatedRoi": round(total_pnl / total_staked, 4) if total_staked else 0.0,
            "endingBankrollUnits": ending_bankroll,
        },
        "calibration": _calibration(outcomes),
        "drawdown": {
            "currentDrawdownPct": drawdown_pct,
            "status": "available" if outcomes else "pending_resolved_outcomes",
        },
    }


def _calibration(outcomes: list[ResolvedOutcome]) -> dict[str, Any]:
    buckets = [
        {"label": "0.00-0.50", "low": 0.0, "high": 0.50, "count": 0, "wins": 0},
        {"label": "0.50-0.60", "low": 0.50, "high": 0.60, "count": 0, "wins": 0},
        {"label": "0.60-0.70", "low": 0.60, "high": 0.70, "count": 0, "wins": 0},
        {"label": "0.70-1.00", "low": 0.70, "high": 1.01, "count": 0, "wins": 0},
    ]
    brier_terms = []
    for outcome in outcomes:
        probability = outcome.fair_probability
        if probability is None:
            continue
        actual = 1.0 if outcome.result == "win" else 0.0
        brier_terms.append((probability - actual) ** 2)
        for bucket in buckets:
            if bucket["low"] <= probability < bucket["high"]:
                bucket["count"] += 1
                bucket["wins"] += int(outcome.result == "win")
                break
    rows = [
        {
            "label": bucket["label"],
            "count": bucket["count"],
            "actualWinRate": round(bucket["wins"] / bucket["count"], 4) if bucket["count"] else None,
        }
        for bucket in buckets
    ]
    return {
        "status": "available" if outcomes else "pending_resolved_outcomes",
        "brierScore": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
        "buckets": rows,
    }


def _is_due(market: dict[str, Any], as_of: str) -> bool:
    if not market:
        return False
    if bool(market.get("closed")):
        return True
    end_time = market.get("end_time")
    if not end_time:
        return False
    end_dt = _parse_time(str(end_time))
    as_of_dt = _parse_time(as_of)
    return bool(end_dt and as_of_dt and end_dt <= as_of_dt)


def _stored_resolution_result(market: dict[str, Any]) -> str | None:
    if not bool(market.get("closed")):
        return None
    prices = market.get("outcome_prices")
    outcomes = [str(item).strip().lower() for item in market.get("outcomes", [])]
    if not isinstance(prices, list) or len(prices) < 2:
        return None
    yes_index = outcomes.index("yes") if "yes" in outcomes else 0
    no_index = outcomes.index("no") if "no" in outcomes else 1
    yes_price = _float(prices[yes_index])
    no_price = _float(prices[no_index])
    if yes_price is None or no_price is None:
        return None
    if yes_price >= 0.99 and no_price <= 0.01:
        return "yes"
    if no_price >= 0.99 and yes_price <= 0.01:
        return "no"
    resolved = str(market.get("resolved_outcome") or market.get("result") or "").strip().lower()
    if resolved in {"yes", "no"}:
        return resolved
    return None


def _pnl_for_binary_share(entry_price: float, stake_units: float, result: str) -> float:
    if result == "push":
        return 0.0
    if result == "loss":
        return round(-stake_units, 4)
    shares = stake_units / entry_price
    return round((shares * 1.0) - stake_units, 4)


def _model_probability(model_outputs: list[dict[str, Any]], candidate_id: str, family: str) -> float | None:
    for row in model_outputs:
        if row.get("candidate_id") == candidate_id and row.get("model_family") == family and row.get("probability") is not None:
            return _float(row.get("probability"))
    return None


def _calibration_bucket(probability: Any) -> str:
    value = _float(probability)
    if value is None:
        return "unknown"
    if value < 0.5:
        return "0.00-0.50"
    if value < 0.6:
        return "0.50-0.60"
    if value < 0.7:
        return "0.60-0.70"
    return "0.70-1.00"


def _parse_time(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
