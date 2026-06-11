from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .production_readiness import build_production_readiness
from .research_scope import ACTIVE_CATEGORIES, AGENT_CONTRACT, OUT_OF_SCOPE_CATEGORIES
from .schemas import MODEL_FAMILIES


REPO_ROOT = Path(__file__).resolve().parents[1]


REQUIREMENTS = [
    ("paper_only_safety", "No wallet/signing/order execution and default paper-only mode.", ["sports_edge/safety.py", "tests/test_pipeline.py"]),
    ("three_sections", "Scope limited to macroeconomics, politics, and stocks/trade.", ["sports_edge/research_scope.py", "AGENTS.md"]),
    ("three_agents", "Context, Data, and Decision Agent contracts exist and are wired.", ["sports_edge/context_agent.py", "sports_edge/data_agent.py", "sports_edge/decision_agent.py", "sports_edge/orchestrator.py"]),
    ("model_families", "At least 3-4 model families with disagreement reporting.", ["sports_edge/model_scoring.py", "sports_edge/schemas.py"]),
    ("daily_run_order", "Daily run evaluates prior bets, context, data, models, bet-specific context, decisions, and output persistence.", ["sports_edge/orchestrator.py", "sports_edge/outcome_evaluator.py"]),
    ("collector_15m", "15-minute collector contract with idempotency.", ["sports_edge/orchestrator.py", ".github/workflows/polymarket-15m.yml"]),
    ("sofia_daily", "09:00 Europe/Sofia daily analytical schedule or UTC equivalent.", ["sports_edge/orchestrator.py", ".github/workflows/polymarket-15m.yml"]),
    ("dashboard_api", "Dashboard/API exposes status, freshness, context, candidates, decisions, models, sources, portfolio, performance, warnings, errors.", ["sports_edge/dashboard_api.py", "api/dashboard-contract.py", "web/app.js"]),
    ("storage_schemas", "Structured schemas and migration definitions exist for core records.", ["sports_edge/schemas.py", "sports_edge/migrations.py", "sports_edge/state_store.py"]),
    ("tests_validation", "Tests and local dry-runs cover contracts, collectors, models, decisions, safety, cron, dashboard shape.", ["tests/test_pipeline.py", "README.md"]),
    ("live_official_adapters", "Read-only live official external adapters are implemented and source/ToS reviewed.", ["sports_edge/external_adapters.py"]),
    ("live_resolution_proof", "Live resolved-outcome proof ingestion exists.", ["sports_edge/outcome_evaluator.py"]),
    ("postgres_apply_proof", "Postgres migrations have been applied and verified against a real DB.", ["sports_edge/cli.py", "sports_edge/state_store.py"]),
    ("deployed_cron_proof", "GitHub/Vercel scheduled jobs have run successfully in production.", [".github/workflows/polymarket-15m.yml", "vercel.json"]),
    ("deployed_dashboard_proof", "Vercel dashboard/API is deployed and externally verified.", ["vercel.json", "web/app.js", "docs/ai/proofs/20260611_vercel_dashboard_smoke.json"]),
]


def build_goal_audit() -> dict[str, Any]:
    readiness = build_production_readiness()
    readiness_status = {row["id"]: row["status"] for row in readiness.get("checks", [])}
    rows = []
    for requirement_id, description, paths in REQUIREMENTS:
        evidence = [_path_evidence(path) for path in paths]
        checks = _requirement_checks(requirement_id, readiness_status)
        status = _status_for_requirement(requirement_id, evidence, checks)
        rows.append(
            {
                "id": requirement_id,
                "description": description,
                "status": status,
                "evidence": evidence,
                "checks": checks,
                "gap": _gap_for_requirement(requirement_id, status),
            }
        )
    complete = all(row["status"] == "proven" for row in rows)
    return {
        "ok": True,
        "complete": complete,
        "summary": {
            "proven": sum(1 for row in rows if row["status"] == "proven"),
            "partial": sum(1 for row in rows if row["status"] == "partial"),
            "missing": sum(1 for row in rows if row["status"] == "missing"),
        },
        "externalProofCommand": "python3 -m sports_edge.cli external-proof-bundle --as-of <YYYY-MM-DD>",
        "requirements": rows,
    }


def _path_evidence(path: str) -> dict[str, Any]:
    file_path = REPO_ROOT / path
    return {
        "path": path,
        "exists": file_path.exists(),
        "size": file_path.stat().st_size if file_path.exists() else 0,
    }


def _status_for_requirement(requirement_id: str, evidence: list[dict[str, Any]], checks: list[dict[str, Any]]) -> str:
    if requirement_id in {"postgres_apply_proof", "deployed_cron_proof"}:
        return "missing"
    if requirement_id in {"live_official_adapters", "live_resolution_proof"}:
        return "partial"
    file_evidence_ok = all(row["exists"] and row["size"] > 0 for row in evidence)
    checks_ok = all(row.get("passed") for row in checks)
    return "proven" if file_evidence_ok and checks_ok else "missing"


def _requirement_checks(requirement_id: str, readiness_status: dict[str, str]) -> list[dict[str, Any]]:
    if requirement_id == "paper_only_safety":
        safety = _read_text("sports_edge/safety.py")
        tests = _read_text("tests/test_pipeline.py")
        return [
            _check("safety_gate_blocks_live_flags", "SafetyGateError" in safety and "liveTradingEnabled" in safety),
            _check("wallet_and_order_envs_checked", "WALLET_PRIVATE_KEY" in safety and "POLYMARKET_ORDER_EXECUTION" in safety),
            _check("paper_only_tests_exist", "assert_paper_trading_only" in tests and "SafetyGateError" in tests),
        ]
    if requirement_id == "three_sections":
        return [
            _check("active_categories_exact", tuple(ACTIVE_CATEGORIES) == ("macroeconomics", "politics", "stocks_trade"), {"activeCategories": list(ACTIVE_CATEGORIES)}),
            _check("out_of_scope_categories_rejected", {"sports", "crypto", "weather", "culture"}.issubset(set(OUT_OF_SCOPE_CATEGORIES))),
            _check("three_agent_contract_sections", [row["id"] for row in AGENT_CONTRACT["sections"]] == list(ACTIVE_CATEGORIES)),
        ]
    if requirement_id == "three_agents":
        orchestrator = _read_text("sports_edge/orchestrator.py")
        return [
            _check("context_agent_wired", "ContextAgent" in orchestrator and "broad_context_reports" in orchestrator),
            _check("data_agent_wired", "DataAgent" in orchestrator and "collect(" in orchestrator),
            _check("decision_agent_wired", "DecisionAgent" in orchestrator and "decide(" in orchestrator),
            _check("user_facing_three_agents", [row["id"] for row in AGENT_CONTRACT["agents"]] == ["context_agent", "data_agent", "decision_agent"]),
        ]
    if requirement_id == "model_families":
        model_scoring = _read_text("sports_edge/model_scoring.py")
        required = {
            "market_implied_probability",
            "liquidity_microstructure",
            "base_rate_event_history",
            "bayesian_consensus",
            "news_catalyst_sentiment",
            "portfolio_ev_risk",
        }
        return [
            _check("model_family_count", len(MODEL_FAMILIES) >= 6, {"modelFamilies": sorted(MODEL_FAMILIES)}),
            _check("required_model_families_present", required.issubset(MODEL_FAMILIES)),
            _check("disagreement_reported", "_disagreement" in model_scoring and "high_model_disagreement" in model_scoring),
        ]
    if requirement_id == "daily_run_order":
        orchestrator = _read_text("sports_edge/orchestrator.py")
        context_agent = _read_text("sports_edge/context_agent.py")
        return [
            _check("evaluates_previous_bets", "evaluate_previous_paper_bets" in orchestrator),
            _check("runs_broad_context_before_models", "broad_context_reports" in orchestrator and "score_market_candidates" in orchestrator),
            _check("gates_bet_specific_context", "bet_specific_context_reports" in orchestrator and "relevant_candidates" in context_agent),
            _check("validates_schema", "_validate_contracts" in orchestrator and "schemaValidation" in orchestrator),
            _check("writes_daily_payload", "daily_runs/latest.json" in orchestrator and "state_store.write_json" in orchestrator),
        ]
    if requirement_id == "collector_15m":
        return [
            _check("collector_readiness_pass", readiness_status.get("collector_15m_live") == "pass"),
            _check("durable_storage_gate_pass", readiness_status.get("durable_storage_gate") == "pass"),
        ]
    if requirement_id == "sofia_daily":
        return [
            _check("sofia_windows_pass", readiness_status.get("sofia_daily_windows") == "pass"),
            _check("daily_live_readonly_pass", readiness_status.get("daily_live_readonly") == "pass"),
        ]
    if requirement_id == "dashboard_api":
        dashboard = _read_text("sports_edge/dashboard_api.py")
        return [
            _check("contract_routes_pass", readiness_status.get("dashboard_contract_routes") == "pass"),
            _check("runtime_scope_boundary_pass", readiness_status.get("runtime_scope_boundary") == "pass"),
            _check("dashboard_sections_present", all(key in dashboard for key in ("status", "freshness", "context", "candidates", "decisions", "models", "sources", "portfolio", "performance", "warnings", "errors"))),
        ]
    if requirement_id == "storage_schemas":
        migrations = _read_text("sports_edge/migrations.py")
        schemas = _read_text("sports_edge/schemas.py")
        required_tables = (
            "cron_runs",
            "market_snapshots",
            "order_book_snapshots",
            "external_source_records",
            "external_observations",
            "context_reports",
            "model_outputs",
            "decision_signals",
            "paper_bets",
            "portfolio_snapshots",
            "resolved_outcomes",
            "decision_notes",
            "knowledge_lessons",
        )
        return [
            _check("migration_tables_present", all(table in migrations for table in required_tables), {"tableCount": len(required_tables)}),
            _check("schema_validate_methods_present", schemas.count("def validate") >= 10),
            _check("cron_run_statuses_validated", "duplicate_skipped" in schemas and "dry_run" in schemas),
        ]
    if requirement_id == "tests_validation":
        tests = _read_text("tests/test_pipeline.py")
        readme = _read_text("README.md")
        required_terms = [
            "test_data_agent",
            "test_model_scoring",
            "test_decision_agent",
            "test_no_live",
            "run-daily",
            "run-collector",
            "dashboard",
        ]
        return [
            _check("required_test_topics_present", all(term in tests for term in required_terms)),
            _check("verification_commands_documented", "python3 -m unittest discover -s tests" in readme and "external-proof-bundle" in readme),
        ]
    if requirement_id == "live_official_adapters":
        adapters = _read_text("sports_edge/external_adapters.py")
        model_scoring = _read_text("sports_edge/model_scoring.py")
        return [
            _check(
                "live_adapter_code_exists",
                "source_mode == \"fixture\"" in adapters
                and "live_external_observations(" in adapters
                and "_safe_public_fetch" in adapters
                and "official_source_http_ok" in adapters,
            ),
            _check("health_rows_not_decision_evidence", "source_health_not_decision_evidence" in adapters and "_is_decision_evidence" in model_scoring),
            _check("external_proof_required", True, {"proofItem": "approved_live_source_validation"}),
        ]
    if requirement_id == "live_resolution_proof":
        evaluator = _read_text("sports_edge/outcome_evaluator.py")
        return [
            _check("stored_resolution_evaluator_exists", "resolvedOutcomes" in evaluator and "resolution" in evaluator.lower()),
            _check("external_proof_required", True, {"proofItem": "approved_live_source_validation"}),
        ]
    if requirement_id == "postgres_apply_proof":
        return [
            _check("migration_apply_path_exists", "apply_schema_migration" in _read_text("sports_edge/state_store.py")),
            _check("external_proof_required", False, {"proofItem": "postgres_apply_proof", "command": "python3 -m sports_edge.cli migrate"}),
        ]
    if requirement_id == "deployed_cron_proof":
        return [
            _check("local_workflow_ready", readiness_status.get("collector_15m_live") == "pass" and readiness_status.get("daily_live_readonly") == "pass"),
            _check("external_proof_required", False, {"proofItem": "production_cron_run_proof"}),
        ]
    if requirement_id == "deployed_dashboard_proof":
        proof = _read_json("docs/ai/proofs/20260611_vercel_dashboard_smoke.json")
        proof_checks = proof.get("checks", {}) if isinstance(proof.get("checks"), dict) else {}
        return [
            _check("local_vercel_surface_ready", readiness_status.get("vercel_static_and_functions") == "pass" and readiness_status.get("dashboard_contract_routes") == "pass"),
            _check(
                "vercel_dashboard_smoke_proof",
                bool(proof)
                and proof_checks.get("root_http_status") == 200
                and proof_checks.get("health_http_status") == 200
                and proof_checks.get("dashboard_contract_http_status") == 200
                and proof_checks.get("runs_latest_http_status") == 200
                and proof_checks.get("unauthenticated_cron_daily_http_status") == 401
                and proof_checks.get("health_ok") is True
                and proof_checks.get("health_cron_secret_configured") is True
                and proof_checks.get("health_durable_storage_configured") is True
                and proof_checks.get("runs_latest_paper_trading_only") is True
                and proof_checks.get("dashboard_contract_paper_trading_only") is True
                and proof_checks.get("dashboard_contract_contains_known_sports_leak") is False,
                {"proofItem": "vercel_dashboard_smoke_proof", "proofPath": "docs/ai/proofs/20260611_vercel_dashboard_smoke.json"},
            ),
        ]
    return []


def _check(check_id: str, passed: bool, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {"id": check_id, "passed": bool(passed)}
    if evidence is not None:
        row["evidence"] = evidence
    return row


def _gap_for_requirement(requirement_id: str, status: str) -> str | None:
    if status == "proven":
        return None
    gaps = {
        "live_official_adapters": "Adapters are read-only and callable, but live source parsing/ToS-specific numeric extraction still requires approved network validation.",
        "live_resolution_proof": "Stored closed-market snapshot resolution exists; live proof URL ingestion still needs approved public endpoint validation.",
        "postgres_apply_proof": "Run `python3 -m sports_edge.cli migrate` with an approved database URL and verify durable writes.",
        "deployed_cron_proof": "Run GitHub Actions/Vercel scheduled jobs and inspect production logs.",
        "deployed_dashboard_proof": "Deploy and verify public Vercel dashboard/API endpoints.",
    }
    return gaps.get(requirement_id, "Evidence is missing or incomplete.")


def _read_text(path: str) -> str:
    try:
        return (REPO_ROOT / path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: str) -> dict[str, Any]:
    try:
        payload = json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
