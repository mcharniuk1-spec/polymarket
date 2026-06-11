from __future__ import annotations

from typing import Any

from .data_agent import infer_market_category
from .orchestrator import DailyRunConfig, run_daily_analysis
from .research_scope import ACTIVE_CATEGORIES
from .state_store import JsonStateStore, default_store


def load_dashboard_contract(store: JsonStateStore | None = None) -> dict[str, Any]:
    state_store = store or default_store()
    latest = state_store.read_json("daily_runs/latest.json", default=None)
    collector_latest = state_store.read_json("collector_latest.json", default=None)
    payload = latest if isinstance(latest, dict) and latest.get("cronRun") else None
    if payload is None:
        payload = run_daily_analysis(DailyRunConfig(source_mode="fixture", target_count=30, dry_run=True), store=state_store)
    if isinstance(collector_latest, dict) and collector_latest.get("dataAgent"):
        payload = {**payload, "dataAgent": collector_latest["dataAgent"]}
        payload["collectorStatus"] = collector_latest.get("cronRun", {})
    return dashboard_contract_from_daily(payload)


def dashboard_contract_from_daily(payload: dict[str, Any]) -> dict[str, Any]:
    data_agent = payload.get("dataAgent", {}) if isinstance(payload.get("dataAgent"), dict) else {}
    markets = data_agent.get("marketSnapshots", []) if isinstance(data_agent.get("marketSnapshots"), list) else []
    scoped_markets = [row for row in markets if _market_in_scope(row)]
    scoped_market_ids = {row.get("market_id") for row in scoped_markets}
    decisions = [
        row
        for row in payload.get("decisionSignals", [])
        if row.get("market_id") in scoped_market_ids or row.get("candidate_id") in scoped_market_ids
    ]
    decision_ids = {row.get("decision_id") for row in decisions}
    model_outputs = [
        row
        for row in payload.get("modelOutputs", [])
        if row.get("market_id") in scoped_market_ids or row.get("candidate_id") in scoped_market_ids
    ]
    cron_run = payload.get("cronRun", {})
    warnings = _warnings(payload, data_agent)
    filtered_count = len(markets) - len(scoped_markets)
    if filtered_count > 0:
        warnings.append(f"Filtered {filtered_count} out-of-scope stored market(s) from dashboard output.")
    context_reports = [
        row
        for row in payload.get("contextReports", [])
        if not row.get("candidate_id") or row.get("candidate_id") in scoped_market_ids
    ]
    decision_notes = [
        row
        for row in payload.get("decisionNotes", [])
        if not row.get("decision_id") or row.get("decision_id") in decision_ids
    ]
    contract = {
        "ok": bool(payload.get("ok")),
        "researchOnly": True,
        "paperTradingOnly": True,
        "status": {
            "runId": cron_run.get("run_id"),
            "status": cron_run.get("status"),
            "dryRun": payload.get("dryRun", False),
            "sourceMode": payload.get("sourceMode"),
            "scheduledFor": cron_run.get("scheduled_for"),
            "startedAt": cron_run.get("started_at"),
            "finishedAt": cron_run.get("finished_at"),
            "idempotencyKey": payload.get("idempotencyKey") or cron_run.get("idempotency_key"),
            "counts": cron_run.get("counts", {}),
            "latestCollector": payload.get("collectorStatus"),
        },
        "freshness": data_agent.get("freshness", _empty_freshness()),
        "context": {
            "reports": context_reports,
            "broadReports": [row for row in context_reports if row.get("scope") == "broad_category"],
            "betSpecificReports": [row for row in context_reports if row.get("scope") == "bet_specific"],
            "byCategory": _by_key(context_reports, "category"),
            "byCandidate": _by_key(
                [row for row in context_reports if row.get("candidate_id")],
                "candidate_id",
            ),
        },
        "candidates": _candidate_rows(scoped_markets, decisions),
        "decisions": {
            "paperBets": [row for row in decisions if row.get("decision") == "paper_bet"],
            "watchlist": [row for row in decisions if row.get("decision") == "watchlist"],
            "rejected": [row for row in decisions if row.get("decision") == "reject"],
            "decisionNotes": decision_notes,
            "all": decisions,
        },
        "models": {
            "outputs": model_outputs,
            "disagreement": _model_disagreement(model_outputs),
        },
        "sources": {
            "records": payload.get("sourceRecords", []),
            "evidence": data_agent.get("externalObservations", []),
        },
        "portfolio": payload.get("portfolioState", {}),
        "performance": _performance_payload(payload),
        "warnings": warnings,
        "errors": _errors(payload, data_agent),
    }
    return contract


def _market_in_scope(market: dict[str, Any]) -> bool:
    if market.get("category") not in ACTIVE_CATEGORIES:
        return False
    return infer_market_category(
        {
            "question": market.get("question"),
            "title": market.get("question"),
            "description": market.get("rules_summary") or market.get("resolution_criteria"),
            "slug": market.get("market_id"),
        }
    ) in ACTIVE_CATEGORIES


def section_payload(section: str, store: JsonStateStore | None = None) -> dict[str, Any]:
    contract = load_dashboard_contract(store=store)
    if section == "all":
        return contract
    if section not in contract:
        return {"ok": False, "error": f"unknown dashboard section: {section}"}
    value = contract[section]
    return {"ok": contract["ok"], section: value}


def runs_latest_payload(store: JsonStateStore | None = None) -> dict[str, Any]:
    contract = load_dashboard_contract(store=store)
    return {
        "ok": contract["ok"],
        "researchOnly": contract["researchOnly"],
        "paperTradingOnly": contract["paperTradingOnly"],
        "run": contract.get("status", {}),
        "status": contract.get("status", {}),
        "warnings": contract.get("warnings", []),
        "errors": contract.get("errors", []),
    }


def runs_history_payload(store: JsonStateStore | None = None) -> dict[str, Any]:
    from .managed_pipeline import load_run_history

    history = load_run_history(store=store)
    return {
        "ok": True,
        "researchOnly": True,
        "paperTradingOnly": True,
        "runs": history.get("runs", []),
        "gaps": history.get("gaps", []),
        "schema_version": history.get("schema_version", 1),
    }


def load_scoped_compat_dashboard() -> dict[str, Any]:
    """Return the legacy aggregate shape without out-of-scope sports records."""
    from .dashboard_data import build_dashboard_payload
    from .managed_pipeline import load_latest_dashboard

    latest = load_latest_dashboard()
    payload = latest if isinstance(latest, dict) and latest.get("multi_agent") else build_dashboard_payload()
    return scoped_compat_dashboard(payload)


def scoped_compat_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep old UI consumers working while enforcing the three-section scope."""
    multi_agent = payload.get("multi_agent", {}) if isinstance(payload.get("multi_agent"), dict) else {}
    metrics = multi_agent.get("metrics", {}) if isinstance(multi_agent.get("metrics"), dict) else {}
    scoped = dict(payload)
    scoped["research_only"] = True
    scoped["paper_trading_only"] = True
    scoped["active_sections"] = list(ACTIVE_CATEGORIES)
    scoped["scope_notice"] = (
        "Aggregate dashboard payload is limited to macroeconomics, politics, and stocks/trade. "
        "Legacy sports backtest root fields are disabled."
    )
    scoped["metrics"] = _scoped_root_metrics(metrics)
    scoped["forecasts"] = []
    scoped["trades"] = []
    scoped["odds_history"] = []
    scoped["legacySportsDisabled"] = True
    return scoped


def legacy_scope_disabled_payload(section: str) -> dict[str, Any]:
    """Compatibility response for legacy backtest routes outside active scope."""
    payload: dict[str, Any] = {
        "ok": True,
        "research_only": True,
        "paper_trading_only": True,
        "active_sections": list(ACTIVE_CATEGORIES),
        "disabled": True,
        "legacySportsDisabled": True,
        "section": section,
        "message": (
            "This legacy sports/backtest route is disabled for the current Polymarket scope. "
            "Use /api/dashboard-contract or the section contract APIs for macroeconomics, politics, and stocks/trade."
        ),
    }
    metrics = _scoped_root_metrics({})
    if section in {"summary", "performance"}:
        payload["metrics"] = metrics
    if section == "forecasts":
        payload["forecasts"] = []
    if section == "performance":
        payload["trades"] = []
    if section == "odds-history":
        payload["odds_history"] = []
    return payload


def _candidate_rows(markets: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions_by_market = {row.get("market_id"): row for row in decisions}
    rows = []
    for market in markets:
        decision = decisions_by_market.get(market.get("market_id"), {})
        rows.append(
            {
                "candidateId": decision.get("candidate_id") or market.get("market_id"),
                "marketId": market.get("market_id"),
                "question": market.get("question"),
                "category": market.get("category"),
                "bestBid": market.get("best_bid"),
                "bestAsk": market.get("best_ask"),
                "spread": market.get("spread"),
                "liquidity": market.get("liquidity"),
                "volume24h": market.get("volume_24h"),
                "timeToResolutionHours": market.get("time_to_resolution_hours"),
                "decision": decision.get("decision", "watchlist"),
                "reasons": decision.get("reasons", []),
                "sourceUrl": market.get("source_url"),
                "rawRef": market.get("raw_ref"),
            }
        )
    return rows


def _scoped_root_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "research_only": True,
        "paper_trading_only": True,
        "active_sections": list(ACTIVE_CATEGORIES),
        "legacy_sports_disabled": True,
        "forecast_count": 0,
        "paper_trade_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "simulated_roi": 0.0,
        "total_staked_units": float(metrics.get("total_staked_units") or 0.0),
        "total_pnl_units": 0.0,
        "ending_bankroll_units": float(metrics.get("ending_bankroll_units") or 100.0),
        "max_drawdown": float(metrics.get("max_drawdown") or 0.0),
        "brier_score": float(metrics.get("brier_score") or 0.0),
        "calibration": [],
        "candidate_count": int(metrics.get("candidate_count") or 0),
        "paper_bet_count": int(metrics.get("paper_bet_count") or 0),
        "watchlist_count": int(metrics.get("watchlist_count") or 0),
        "rejected_count": int(metrics.get("rejected_count") or 0),
        "deployment_budget_units": float(metrics.get("deployment_budget_units") or 100.0),
        "unallocated_budget_units": float(metrics.get("unallocated_budget_units") or 0.0),
    }


def _model_disagreement(model_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_candidate: dict[str, list[float]] = {}
    for row in model_outputs:
        probability = row.get("probability")
        if probability is None:
            continue
        by_candidate.setdefault(str(row.get("candidate_id")), []).append(float(probability))
    rows = {}
    for candidate_id, probabilities in by_candidate.items():
        if not probabilities:
            continue
        rows[candidate_id] = {
            "minProbability": min(probabilities),
            "maxProbability": max(probabilities),
            "range": max(probabilities) - min(probabilities),
            "modelCount": len(probabilities),
        }
    return {"byCandidate": rows, "status": "contract_only" if not rows else "available"}


def _warnings(payload: dict[str, Any], data_agent: dict[str, Any]) -> list[str]:
    warnings = []
    warnings.extend(payload.get("cronRun", {}).get("warnings", []))
    warnings.extend(payload.get("warnings", []))
    warnings.extend(data_agent.get("warnings", []))
    warnings.extend(data_agent.get("freshness", {}).get("warnings", []))
    return sorted(set(str(item) for item in warnings if item))


def _errors(payload: dict[str, Any], data_agent: dict[str, Any]) -> list[Any]:
    errors = []
    errors.extend(payload.get("cronRun", {}).get("errors", []))
    errors.extend(payload.get("schemaValidation", {}).get("errors", []))
    errors.extend(data_agent.get("errors", []))
    return errors


def _by_key(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key, "unknown")), []).append(row)
    return grouped


def _empty_freshness() -> dict[str, Any]:
    return {
        "marketSnapshotCount": 0,
        "orderBookSnapshotCount": 0,
        "externalObservationCount": 0,
        "categories": {},
        "warnings": ["No Data Agent freshness payload is available."],
    }


def _performance_payload(payload: dict[str, Any]) -> dict[str, Any]:
    previous = payload.get("previousEvaluation", {}) if isinstance(payload.get("previousEvaluation"), dict) else {}
    return {
        "status": previous.get("status", "pending_resolved_outcomes"),
        "summary": previous.get("metrics", {}),
        "resolvedOutcomes": payload.get("resolvedOutcomes", previous.get("resolvedOutcomes", [])),
        "paperTradingHistory": previous.get("paperTradingHistory", []),
        "calibration": previous.get("calibration", {"status": "pending_resolved_outcomes"}),
        "drawdown": previous.get("drawdown", {"currentDrawdownPct": 0.0, "status": "no_resolved_paper_bets_yet"}),
        "knowledgeLessons": payload.get("knowledgeLessons", previous.get("knowledgeLessons", [])),
        "currentPaperBets": payload.get("currentPaperBets", []),
    }
