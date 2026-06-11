from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .production_readiness import build_production_readiness
from .research_scope import ACTIVE_CATEGORIES, AGENT_CONTRACT, OUT_OF_SCOPE_CATEGORIES
from .schemas import MODEL_FAMILIES


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_PROOF_PATH = "docs/ai/proofs/20260611_postgres_migration_proof.json"
PRODUCTION_CRON_PROOF_PATH = "docs/ai/proofs/20260611_production_cron_run.json"
LIVE_SOURCE_PROOF_PATH = "docs/ai/proofs/20260611_live_source_validation.json"
DURABLE_DAILY_PROOF_PATH = "docs/ai/proofs/20260611_durable_daily_write.json"

MILESTONE_TABLES = (
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


REQUIREMENTS = [
    ("paper_only_safety", "No wallet/signing/order execution and default paper-only mode.", ["sports_edge/safety.py", "tests/test_pipeline.py"]),
    ("three_sections", "Scope limited to macroeconomics, politics, and stocks/trade.", ["sports_edge/research_scope.py", "AGENTS.md"]),
    ("three_agents", "Context, Data, and Decision Agent contracts exist and are wired.", ["sports_edge/context_agent.py", "sports_edge/data_agent.py", "sports_edge/decision_agent.py", "sports_edge/orchestrator.py"]),
    ("model_families", "At least 3-4 model families with disagreement reporting.", ["sports_edge/model_scoring.py", "sports_edge/schemas.py"]),
    ("daily_run_order", "Daily run evaluates prior bets, context, data, models, bet-specific context, decisions, and output persistence.", ["sports_edge/orchestrator.py", "sports_edge/outcome_evaluator.py"]),
    ("durable_daily_write_proof", "Daily analytical runs have proven duplicate-safe durable persistence.", ["sports_edge/orchestrator.py", DURABLE_DAILY_PROOF_PATH]),
    ("collector_15m", "15-minute collector contract with idempotency.", ["sports_edge/orchestrator.py", ".github/workflows/polymarket-15m.yml"]),
    ("sofia_daily", "09:00 Europe/Sofia daily analytical schedule or UTC equivalent.", ["sports_edge/orchestrator.py", ".github/workflows/polymarket-15m.yml"]),
    ("dashboard_api", "Dashboard/API exposes status, freshness, context, candidates, decisions, models, sources, portfolio, performance, warnings, errors.", ["sports_edge/dashboard_api.py", "api/dashboard-contract.py", "web/app.js"]),
    ("storage_schemas", "Structured schemas and migration definitions exist for core records.", ["sports_edge/schemas.py", "sports_edge/migrations.py", "sports_edge/state_store.py"]),
    ("tests_validation", "Tests and local dry-runs cover contracts, collectors, models, decisions, safety, cron, dashboard shape.", ["tests/test_pipeline.py", "README.md"]),
    ("live_official_adapters", "Read-only live official external adapters are implemented and source/ToS reviewed.", ["sports_edge/external_adapters.py", LIVE_SOURCE_PROOF_PATH]),
    ("live_resolution_proof", "Live resolved-outcome proof ingestion exists.", ["sports_edge/outcome_evaluator.py", LIVE_SOURCE_PROOF_PATH]),
    ("postgres_apply_proof", "Postgres migrations have been applied and verified against a real DB.", ["sports_edge/cli.py", "sports_edge/state_store.py", POSTGRES_PROOF_PATH]),
    ("deployed_cron_proof", "GitHub/Vercel scheduled jobs have run successfully in production.", [".github/workflows/polymarket-15m.yml", "vercel.json", PRODUCTION_CRON_PROOF_PATH]),
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
    if requirement_id == "postgres_apply_proof":
        return "proven" if all(row.get("passed") for row in checks) else "missing"
    if requirement_id == "deployed_cron_proof":
        return "proven" if all(row.get("passed") for row in checks) else "missing"
    if requirement_id == "durable_daily_write_proof":
        return "proven" if all(row.get("passed") for row in checks) else "missing"
    if requirement_id in {"live_official_adapters", "live_resolution_proof"}:
        return "proven" if all(row.get("passed") for row in checks) else "partial"
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
    if requirement_id == "durable_daily_write_proof":
        proof = _read_json(DURABLE_DAILY_PROOF_PATH)
        return [
            _check("daily_write_path_exists", "run_daily_analysis" in _read_text("sports_edge/orchestrator.py") and "duplicate_skipped" in _read_text("sports_edge/orchestrator.py")),
            _check(
                "durable_daily_write_proof",
                _durable_daily_proof_valid(proof),
                {"proofItem": "durable_daily_write_proof", "proofPath": DURABLE_DAILY_PROOF_PATH},
            ),
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
        return [
            _check("migration_tables_present", all(table in migrations for table in MILESTONE_TABLES), {"tableCount": len(MILESTONE_TABLES)}),
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
        proof = _read_json(LIVE_SOURCE_PROOF_PATH)
        return [
            _check(
                "live_adapter_code_exists",
                "source_mode == \"fixture\"" in adapters
                and "live_external_observations(" in adapters
                and "_safe_public_fetch" in adapters
                and "official_source_http_ok" in adapters,
            ),
            _check("health_rows_not_decision_evidence", "source_health_not_decision_evidence" in adapters and "_is_decision_evidence" in model_scoring),
            _check(
                "approved_live_source_validation",
                _live_source_proof_valid(proof, require_resolution=False),
                {"proofItem": "approved_live_source_validation", "proofPath": LIVE_SOURCE_PROOF_PATH},
            ),
        ]
    if requirement_id == "live_resolution_proof":
        evaluator = _read_text("sports_edge/outcome_evaluator.py")
        proof = _read_json(LIVE_SOURCE_PROOF_PATH)
        return [
            _check("stored_resolution_evaluator_exists", "resolvedOutcomes" in evaluator and "resolution" in evaluator.lower()),
            _check(
                "approved_live_resolution_validation",
                _live_source_proof_valid(proof, require_resolution=True),
                {"proofItem": "approved_live_source_validation", "proofPath": LIVE_SOURCE_PROOF_PATH},
            ),
        ]
    if requirement_id == "postgres_apply_proof":
        proof = _read_json(POSTGRES_PROOF_PATH)
        return [
            _check("migration_apply_path_exists", "apply_schema_migration" in _read_text("sports_edge/state_store.py")),
            _check(
                "postgres_migration_proof",
                _postgres_migration_proof_valid(proof),
                {"proofItem": "postgres_apply_proof", "proofPath": POSTGRES_PROOF_PATH, "command": "python3 -m sports_edge.cli migrate"},
            ),
        ]
    if requirement_id == "deployed_cron_proof":
        proof = _read_json(PRODUCTION_CRON_PROOF_PATH)
        return [
            _check("local_workflow_ready", readiness_status.get("collector_15m_live") == "pass" and readiness_status.get("daily_live_readonly") == "pass"),
            _check(
                "production_cron_run_proof",
                _production_cron_proof_valid(proof),
                {"proofItem": "production_cron_run_proof", "proofPath": PRODUCTION_CRON_PROOF_PATH},
            ),
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
        "live_official_adapters": f"Adapters are read-only and callable, but live source parsing/ToS-specific numeric extraction still requires approved network validation in `{LIVE_SOURCE_PROOF_PATH}`.",
        "live_resolution_proof": f"Stored closed-market snapshot resolution exists; live proof URL ingestion still needs approved public endpoint validation in `{LIVE_SOURCE_PROOF_PATH}`.",
        "durable_daily_write_proof": f"Run an approved durable fixture daily write plus duplicate rerun, sanitize the evidence, and write `{DURABLE_DAILY_PROOF_PATH}` with `python3 -m sports_edge.cli durable-daily-proof --evidence-in <sanitized-daily-evidence.json>`.",
        "postgres_apply_proof": f"Run `python3 -m sports_edge.cli migrate` with an approved database URL and save sanitized proof to `{POSTGRES_PROOF_PATH}`.",
        "deployed_cron_proof": f"Run scheduled jobs, sanitize the evidence, and write `{PRODUCTION_CRON_PROOF_PATH}` with `python3 -m sports_edge.cli production-cron-proof --evidence-in <sanitized-cron-evidence.json>`.",
        "deployed_dashboard_proof": "Deploy and verify public Vercel dashboard/API endpoints.",
    }
    return gaps.get(requirement_id, "Evidence is missing or incomplete.")


def _postgres_migration_proof_valid(proof: dict[str, Any]) -> bool:
    checks = proof.get("checks", {}) if isinstance(proof.get("checks"), dict) else {}
    migration = proof.get("migration", {}) if isinstance(proof.get("migration"), dict) else {}
    storage = proof.get("storage", {}) if isinstance(proof.get("storage"), dict) else {}
    verified_tables = set(migration.get("verifiedTables", []) or storage.get("verifiedTables", []))
    missing_tables = migration.get("missingTables", storage.get("missingTables", []))
    return (
        bool(proof)
        and proof.get("proof_id", "").startswith("postgres_migration_")
        and proof.get("researchOnly") is True
        and proof.get("paperTradingOnly") is True
        and migration.get("ok") is True
        and migration.get("applied") is True
        and storage.get("durable") is True
        and missing_tables == []
        and set(MILESTONE_TABLES).issubset(verified_tables)
        and checks.get("database_url_value_exposed") is False
        and checks.get("logs_contain_credentials") is False
        and checks.get("wallet_or_order_execution_enabled") is False
    )


def _production_cron_proof_valid(proof: dict[str, Any]) -> bool:
    checks = proof.get("checks", {}) if isinstance(proof.get("checks"), dict) else {}
    run = proof.get("run", {}) if isinstance(proof.get("run"), dict) else {}
    scheduled_jobs = proof.get("scheduledJobs", {}) if isinstance(proof.get("scheduledJobs"), dict) else {}
    collector = scheduled_jobs.get("collector_15m", {}) if isinstance(scheduled_jobs.get("collector_15m"), dict) else {}
    daily = scheduled_jobs.get("sofia_daily", {}) if isinstance(scheduled_jobs.get("sofia_daily"), dict) else {}
    return (
        bool(proof)
        and proof.get("proof_id", "").startswith("production_cron_run_")
        and proof.get("researchOnly") is True
        and proof.get("paperTradingOnly") is True
        and run.get("event") in {"schedule", "vercel_cron"}
        and run.get("status") in {"completed", "success"}
        and run.get("conclusion") in {"success", None}
        and collector.get("observed") is True
        and collector.get("status") in {"success", "duplicate_skipped"}
        and collector.get("sourceMode") == "live"
        and daily.get("observed") is True
        and daily.get("status") in {"success", "duplicate_skipped"}
        and daily.get("sourceMode") == "live"
        and checks.get("collector_15m_completed") is True
        and checks.get("sofia_daily_completed") is True
        and checks.get("source_mode_live") is True
        and checks.get("paper_trading_only") is True
        and checks.get("durable_storage_gate_passed") is True
        and checks.get("logs_contain_credentials") is False
        and checks.get("dashboard_reflects_run") is True
        and checks.get("wallet_or_order_execution_enabled") is False
    )


def _durable_daily_proof_valid(proof: dict[str, Any]) -> bool:
    checks = proof.get("checks", {}) if isinstance(proof.get("checks"), dict) else {}
    first_run = proof.get("firstRun", {}) if isinstance(proof.get("firstRun"), dict) else {}
    duplicate_run = proof.get("duplicateRun", {}) if isinstance(proof.get("duplicateRun"), dict) else {}
    storage = proof.get("storage", {}) if isinstance(proof.get("storage"), dict) else {}
    return (
        bool(proof)
        and proof.get("proof_id", "").startswith("durable_daily_write_")
        and proof.get("researchOnly") is True
        and proof.get("paperTradingOnly") is True
        and first_run.get("sourceMode") == "fixture"
        and first_run.get("status") == "success"
        and first_run.get("storageWritten") is True
        and isinstance(first_run.get("idempotencyKey"), str)
        and first_run.get("idempotencyKey", "").startswith("daily:")
        and duplicate_run.get("status") == "duplicate_skipped"
        and duplicate_run.get("storageWritten") is False
        and duplicate_run.get("idempotencyKey") == first_run.get("idempotencyKey")
        and storage.get("durable") is True
        and checks.get("duplicate_write_protected") is True
        and checks.get("dry_run") is False
        and checks.get("logs_contain_credentials") is False
        and checks.get("wallet_or_order_execution_enabled") is False
    )


def _live_source_proof_valid(proof: dict[str, Any], *, require_resolution: bool) -> bool:
    checks = proof.get("checks", {}) if isinstance(proof.get("checks"), dict) else {}
    categories = proof.get("categories", {}) if isinstance(proof.get("categories"), dict) else {}
    run = proof.get("run", {}) if isinstance(proof.get("run"), dict) else {}
    required_categories = {"macroeconomics", "politics", "stocks_trade"}
    category_rows_ok = all(
        isinstance(categories.get(category), dict)
        and categories[category].get("observed") is True
        and categories[category].get("sourceCount", 0) >= 1
        for category in required_categories
    )
    base_ok = (
        bool(proof)
        and proof.get("proof_id", "").startswith("live_source_validation_")
        and proof.get("researchOnly") is True
        and proof.get("paperTradingOnly") is True
        and run.get("sourceMode") == "live"
        and category_rows_ok
        and checks.get("read_only_public_sources") is True
        and checks.get("tos_review_completed") is True
        and checks.get("parser_verified_numeric_observations") is True
        and checks.get("source_health_only_not_decision_evidence") is True
        and checks.get("rules_resolution_captured") is True
        and checks.get("wallet_or_order_execution_enabled") is False
        and checks.get("logs_contain_credentials") is False
    )
    if not require_resolution:
        return base_ok
    return (
        base_ok
        and checks.get("live_resolution_proof_validated") is True
        and checks.get("resolved_outcome_public_proof_url_captured") is True
    )


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
