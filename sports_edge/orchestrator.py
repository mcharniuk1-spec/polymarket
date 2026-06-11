from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .context_agent import ContextAgent
from .data_agent import DataAgent, data_source_records
from .decision_agent import DecisionAgent
from .model_scoring import score_market_candidates
from .outcome_evaluator import (
    decision_notes_from_signals,
    evaluate_previous_paper_bets,
    paper_bet_from_decision,
)
from .research_scope import ACTIVE_CATEGORIES, CATEGORY_LABELS
from .safety import assert_paper_trading_only
from .schemas import (
    ContextReport,
    CronRunRecord,
    DecisionSignal,
    DecisionNote,
    KnowledgeLesson,
    MODEL_FAMILIES,
    ModelOutput,
    PaperBet,
    PortfolioState,
    ResolvedOutcome,
    SourceRecord,
    iso_now,
    reliability_label,
    stable_id,
)
from .state_store import JsonStateStore, default_store


SOFIA = ZoneInfo("Europe/Sofia")
DAILY_RUN_HOUR = 9


@dataclass(frozen=True)
class DailyRunConfig:
    source_mode: str = "fixture"
    target_count: int = 30
    dry_run: bool = True
    as_of: str | None = None
    force: bool = False


@dataclass(frozen=True)
class CollectorRunConfig:
    source_mode: str = "fixture"
    target_count: int = 30
    dry_run: bool = True
    as_of: str | None = None
    force: bool = False


def run_collector(config: CollectorRunConfig | None = None, *, store: JsonStateStore | None = None) -> dict[str, Any]:
    cfg = config or CollectorRunConfig()
    if cfg.source_mode not in {"fixture", "live"}:
        raise ValueError("source_mode must be fixture or live")
    safety = assert_paper_trading_only()
    state_store = store or default_store()
    as_of_dt = _parse_as_of(cfg.as_of)
    scheduled_for = _collector_bucket(as_of_dt)
    bucket_key = scheduled_for.strftime("%Y-%m-%dT%H:%MZ")
    idempotency_key = f"collector:{bucket_key}"
    idempotency_hash = stable_id(idempotency_key)
    run_id = f"collector-{bucket_key.replace(':', '').replace('-', '')}-{idempotency_hash[:10]}"
    existing = state_store.read_json(_collector_run_key(idempotency_hash), default=None)
    duplicate = bool(existing) and not cfg.force
    started_at = iso_now()
    if duplicate:
        data_payload = existing.get("dataAgent", {}) if isinstance(existing, dict) else {}
    else:
        data_payload = DataAgent().collect(
            run_id=run_id,
            source_mode=cfg.source_mode,
            target_count=cfg.target_count,
            observed_at=_iso_z(scheduled_for),
        )
    counts = {
        "marketSnapshots": len(data_payload.get("marketSnapshots", [])),
        "orderBookSnapshots": len(data_payload.get("orderBookSnapshots", [])),
        "sourceRecords": len(data_payload.get("sourceRecords", [])),
        "externalObservations": len(data_payload.get("externalObservations", [])),
    }
    status = "dry_run" if cfg.dry_run else "duplicate_skipped" if duplicate else "success"
    warnings = list(data_payload.get("warnings", []))
    if cfg.source_mode == "fixture":
        warnings.append("Collector used deterministic fixture data; no live public API call occurred.")
    if duplicate:
        warnings.append("Collector idempotency key already exists; non-forced write skipped.")
    cron_run = CronRunRecord(
        run_id=run_id,
        cycle_type="scheduled_15m",
        scheduled_for=_iso_z(scheduled_for),
        idempotency_key=idempotency_key,
        status=status,
        dry_run=cfg.dry_run,
        started_at=started_at,
        finished_at=iso_now(),
        counts=counts,
        warnings=warnings,
        errors=list(data_payload.get("errors", [])),
    )
    payload = {
        "ok": bool(data_payload.get("ok", not cron_run.errors)),
        "researchOnly": True,
        "paperTradingOnly": True,
        "collector": True,
        "dryRun": cfg.dry_run,
        "duplicate": duplicate,
        "sourceMode": cfg.source_mode,
        "targetCount": cfg.target_count,
        "activeSections": list(ACTIVE_CATEGORIES),
        "idempotencyKey": idempotency_key,
        "cronRun": cron_run.to_dict(),
        "safety": safety,
        "dataAgent": data_payload,
        "storage": {"written": False, "reason": "dry_run" if cfg.dry_run else "duplicate_skipped" if duplicate else "pending"},
    }
    if cfg.dry_run or duplicate or not payload["ok"]:
        return payload

    write_result = state_store.write_json(_collector_run_key(idempotency_hash), payload)
    latest_result = state_store.write_json("collector_latest.json", payload)
    payload["storage"] = {"written": True, "collectorRun": write_result, "latest": latest_result}
    return payload


def run_daily_analysis(config: DailyRunConfig | None = None, *, store: JsonStateStore | None = None) -> dict[str, Any]:
    cfg = config or DailyRunConfig()
    if cfg.source_mode not in {"fixture", "live"}:
        raise ValueError("source_mode must be fixture or live")

    safety = assert_paper_trading_only()
    state_store = store or default_store()
    as_of_dt = _parse_as_of(cfg.as_of)
    scheduled_for = _scheduled_for_sofia(as_of_dt)
    local_date = scheduled_for.astimezone(SOFIA).date().isoformat()
    idempotency_key = f"daily:{local_date}"
    idempotency_hash = stable_id(idempotency_key)
    existing = state_store.read_json(_cron_run_key(idempotency_hash), default=None)
    duplicate = bool(existing) and not cfg.force
    started_at = iso_now()
    run_id = f"daily-{local_date}-{idempotency_hash[:10]}"
    scheduled_for_iso = _iso_z(scheduled_for)

    previous_evaluation = evaluate_previous_paper_bets(
        store=state_store,
        current_run_id=run_id,
        as_of=scheduled_for_iso,
        source_mode=cfg.source_mode,
    )

    context_agent = ContextAgent()
    broad_context_reports = context_agent.broad_context_reports(
        run_id=run_id,
        created_at=started_at,
        source_mode=cfg.source_mode,
    )
    data_payload = DataAgent().collect(
        run_id=run_id,
        source_mode="fixture" if cfg.dry_run else cfg.source_mode,
        target_count=cfg.target_count,
        observed_at=started_at,
    )
    source_records = [SourceRecord(**row) for row in data_payload.get("sourceRecords", [])]
    model_outputs = score_market_candidates(run_id=run_id, data_payload=data_payload, created_at=started_at)
    bet_specific_context_reports = context_agent.bet_specific_reports(
        run_id=run_id,
        created_at=started_at,
        data_payload=data_payload,
        model_outputs=model_outputs,
        source_mode="fixture" if cfg.dry_run else cfg.source_mode,
    )
    context_reports = [*broad_context_reports, *bet_specific_context_reports]
    decisions, portfolio = DecisionAgent().decide(
        run_id=run_id,
        data_payload=data_payload,
        model_outputs=model_outputs,
        context_reports=context_reports,
        created_at=started_at,
    )
    model_output_dicts = [output.to_dict() for output in model_outputs]
    current_paper_bets = [
        paper_bet
        for decision in decisions
        if (paper_bet := paper_bet_from_decision(decision.to_dict(), model_outputs=model_output_dicts)) is not None
    ]
    decision_notes = decision_notes_from_signals(decisions, created_at=started_at)
    previous_drawdown = previous_evaluation.get("drawdown", {}).get("currentDrawdownPct")
    if previous_drawdown is not None:
        portfolio = replace(
            portfolio,
            current_drawdown_pct=float(previous_drawdown),
            warnings=[
                *portfolio.warnings,
                *previous_evaluation.get("warnings", []),
            ],
        )
    warnings = _warnings(cfg, duplicate)
    counts = {
        "sections": len(ACTIVE_CATEGORIES),
        "contextReports": len(context_reports),
        "sourceRecords": len(source_records),
        "marketSnapshots": len(data_payload["marketSnapshots"]),
        "orderBookSnapshots": len(data_payload["orderBookSnapshots"]),
        "externalObservations": len(data_payload["externalObservations"]),
        "modelOutputs": len(model_outputs),
        "decisionSignals": len(decisions),
        "paperBets": len([row for row in decisions if row.decision == "paper_bet"]),
        "currentPaperBets": len(current_paper_bets),
        "resolvedOutcomes": len(previous_evaluation.get("resolvedOutcomes", [])),
        "decisionNotes": len(decision_notes),
        "knowledgeLessons": len(previous_evaluation.get("knowledgeLessons", [])),
    }
    status = "dry_run" if cfg.dry_run else "duplicate_skipped" if duplicate else "success"
    cron_run = CronRunRecord(
        run_id=run_id,
        cycle_type="daily_analytics",
        scheduled_for=scheduled_for_iso,
        idempotency_key=idempotency_key,
        status=status,
        dry_run=cfg.dry_run,
        started_at=started_at,
        finished_at=iso_now(),
        counts=counts,
        warnings=warnings,
        errors=[],
    )
    validation = _validate_contracts(
        context_reports,
        source_records,
        model_outputs,
        decisions,
        portfolio,
        cron_run,
        current_paper_bets,
        [ResolvedOutcome(**row) for row in previous_evaluation.get("resolvedOutcomes", [])],
        decision_notes,
        [KnowledgeLesson(**row) for row in previous_evaluation.get("knowledgeLessons", [])],
    )
    payload = {
        "ok": not validation["errors"],
        "researchOnly": True,
        "paperTradingOnly": True,
        "dryRun": cfg.dry_run,
        "duplicate": duplicate,
        "sourceMode": cfg.source_mode,
        "targetCount": cfg.target_count,
        "activeSections": list(ACTIVE_CATEGORIES),
        "dailyRunHourEuropeSofia": DAILY_RUN_HOUR,
        "idempotencyKey": idempotency_key,
        "cronRun": cron_run.to_dict(),
        "safety": safety,
        "schemaValidation": validation,
        "previousEvaluation": previous_evaluation,
        "contextReports": [report.to_dict() for report in context_reports],
        "sourceRecords": [record.to_dict() for record in source_records],
        "dataAgent": data_payload,
        "modelOutputs": [output.to_dict() for output in model_outputs],
        "decisionSignals": [decision.to_dict() for decision in decisions],
        "currentPaperBets": [paper_bet.to_dict() for paper_bet in current_paper_bets],
        "resolvedOutcomes": previous_evaluation.get("resolvedOutcomes", []),
        "decisionNotes": [note.to_dict() for note in decision_notes],
        "knowledgeLessons": previous_evaluation.get("knowledgeLessons", []),
        "portfolioState": portfolio.to_dict(),
        "storage": {"written": False, "reason": "dry_run" if cfg.dry_run else "duplicate_skipped" if duplicate else "pending"},
    }
    if validation["errors"]:
        payload["cronRun"]["status"] = "failed"
        payload["ok"] = False
        return payload
    if cfg.dry_run or duplicate:
        return payload

    write_result = state_store.write_json(_cron_run_key(idempotency_hash), payload)
    latest_result = state_store.write_json("daily_runs/latest.json", payload)
    payload["storage"] = {"written": True, "cronRun": write_result, "latest": latest_result}
    return payload


def _parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.strip()
    if len(normalized) == 10:
        year, month, day = [int(part) for part in normalized.split("-")]
        return datetime(year, month, day, DAILY_RUN_HOUR, 0, tzinfo=SOFIA).astimezone(timezone.utc)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scheduled_for_sofia(as_of_dt: datetime) -> datetime:
    local = as_of_dt.astimezone(SOFIA)
    return datetime(local.year, local.month, local.day, DAILY_RUN_HOUR, 0, tzinfo=SOFIA).astimezone(timezone.utc)


def _collector_bucket(as_of_dt: datetime) -> datetime:
    utc = as_of_dt.astimezone(timezone.utc)
    minute = (utc.minute // 15) * 15
    return utc.replace(minute=minute, second=0, microsecond=0)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cron_run_key(idempotency_hash: str) -> str:
    return f"cron_runs/{idempotency_hash}.json"


def _collector_run_key(idempotency_hash: str) -> str:
    return f"collector_runs/{idempotency_hash}.json"


def _broad_context_reports(run_id: str, created_at: str) -> list[ContextReport]:
    reports: list[ContextReport] = []
    for category in ACTIVE_CATEGORIES:
        label = CATEGORY_LABELS[category]
        confidence = 0.5
        reports.append(
            ContextReport(
                report_id=stable_id(run_id, category, "broad_context"),
                run_id=run_id,
                category=category,
                scope="broad_category",
                created_at=created_at,
                summary=(
                    f"Fixture-first broad {label} context contract. Milestone 1 validates structure "
                    "without claiming live evidence or forcing a bet."
                ),
                key_events=[],
                sources=[],
                uncertainty="Live context collection is not enabled in Milestone 1 dry-run mode.",
                confidence=confidence,
                reliability=reliability_label(confidence),
                market_relevance=[category],
                invalidation_triggers=[
                    "source freshness exceeds SLA",
                    "resolution rules are unclear",
                    "model families disagree materially",
                ],
            )
        )
    return reports


def _source_records() -> list[SourceRecord]:
    return data_source_records()


def _model_outputs(run_id: str, created_at: str) -> list[ModelOutput]:
    outputs: list[ModelOutput] = []
    ordered_families = sorted(MODEL_FAMILIES)
    for category in ACTIVE_CATEGORIES:
        candidate_id = f"fixture-{category}-daily-contract"
        for family in ordered_families:
            probability = 0.5 if family == "market_implied_probability" else None
            confidence = 0.25 if probability is None else 0.5
            outputs.append(
                ModelOutput(
                    output_id=stable_id(run_id, candidate_id, family),
                    run_id=run_id,
                    candidate_id=candidate_id,
                    market_id=candidate_id,
                    category=category,
                    model_family=family,
                    probability=probability,
                    confidence=confidence,
                    evidence_quality="contract_only",
                    features={"sourceMode": "fixture", "asOfSafe": True},
                    disagreement={"status": "not_evaluated", "reason": "Milestone 1 schema dry run"},
                    gaps=["live market data not collected in Milestone 1 dry run"],
                    reject_flags=["insufficient_evidence_for_paper_bet"],
                    created_at=created_at,
                )
            )
    return outputs


def _decision_signals(run_id: str, created_at: str) -> list[DecisionSignal]:
    decisions: list[DecisionSignal] = []
    for category in ACTIVE_CATEGORIES:
        candidate_id = f"fixture-{category}-daily-contract"
        decisions.append(
            DecisionSignal(
                decision_id=stable_id(run_id, candidate_id, "decision"),
                run_id=run_id,
                candidate_id=candidate_id,
                market_id=candidate_id,
                category=category,
                decision="watchlist",
                confidence=0.5,
                reliability="possible/probable",
                edge=0.0,
                stake_units=0.0,
                reasons=[
                    "Milestone 1 validates the daily decision contract.",
                    "No paper bet is forced without live market, source, and model evidence.",
                ],
                model_disagreement={"status": "not_evaluated"},
                invalidation_triggers=["missing source evidence", "stale data", "high spread", "ambiguous resolution"],
                evaluation_plan="Promote to candidate-level evaluation after Data Agent selects a real market.",
                created_at=created_at,
            )
        )
    return decisions


def _portfolio_state(run_id: str, created_at: str) -> PortfolioState:
    bankroll_units = 100.0
    return PortfolioState(
        portfolio_id=stable_id(run_id, "portfolio"),
        run_id=run_id,
        bankroll_units=bankroll_units,
        total_exposure_units=0.0,
        max_portfolio_exposure_pct=0.25,
        max_single_market_pct=0.03,
        max_category_pct=0.10,
        max_correlated_theme_pct=0.06,
        current_drawdown_pct=0.0,
        category_exposure={category: 0.0 for category in ACTIVE_CATEGORIES},
        warnings=[],
        created_at=created_at,
    )


def _warnings(cfg: DailyRunConfig, duplicate: bool) -> list[str]:
    warnings = [
        "Previous paper-bet evaluation runs before new context, data, model, and decision stages.",
        "Daily run defaults to fixture mode locally; scheduled production can use source=live for read-only data.",
        "Candidate-specific context is generated only for markets passing Data Agent and model relevance gates.",
        "External numeric adapters still emit readiness contracts until official adapters are implemented.",
    ]
    if cfg.source_mode == "live":
        warnings.append("Live source mode is accepted only as a dry-run contract check in Milestone 1.")
    if duplicate:
        warnings.append("Daily idempotency key already exists; non-forced write would be skipped.")
    return warnings


def _validate_contracts(
    context_reports: list[ContextReport],
    source_records: list[SourceRecord],
    model_outputs: list[ModelOutput],
    decisions: list[DecisionSignal],
    portfolio: PortfolioState,
    cron_run: CronRunRecord,
    paper_bets: list[PaperBet],
    resolved_outcomes: list[ResolvedOutcome],
    decision_notes: list[DecisionNote],
    knowledge_lessons: list[KnowledgeLesson],
) -> dict[str, Any]:
    rows: list[tuple[str, list[str]]] = []
    rows.extend((f"context:{row.report_id}", row.validate()) for row in context_reports)
    rows.extend((f"source:{row.source_id}", row.validate()) for row in source_records)
    rows.extend((f"model:{row.output_id}", row.validate()) for row in model_outputs)
    rows.extend((f"decision:{row.decision_id}", row.validate()) for row in decisions)
    rows.extend((f"paper_bet:{row.paper_bet_id}", row.validate()) for row in paper_bets)
    rows.extend((f"resolved:{row.outcome_id}", row.validate()) for row in resolved_outcomes)
    rows.extend((f"note:{row.note_id}", row.validate()) for row in decision_notes)
    rows.extend((f"lesson:{row.lesson_id}", row.validate()) for row in knowledge_lessons)
    rows.append((f"portfolio:{portfolio.portfolio_id}", portfolio.validate()))
    rows.append((f"cron:{cron_run.run_id}", cron_run.validate()))
    errors = [{"record": name, "errors": errors} for name, errors in rows if errors]
    return {"ok": not errors, "checkedRecordCount": len(rows), "errors": errors}
