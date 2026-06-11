from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .agents import ACTIVE_CATEGORIES, MultiAgentPipeline
from .backtesting import Backtester
from .bet_research import BetResearchPlanner
from .codex_queue import drain_codex_queue, queue_summary
from .dashboard_data import build_dashboard_payload
from .external_proof import build_external_proof_bundle
from .full_scan import run_full_scan
from .goal_audit import POSTGRES_PROOF_PATH, PRODUCTION_CRON_PROOF_PATH, build_goal_audit
from .intelligence import run_intelligence_cycle
from .managed_pipeline import load_correlations, load_model_state, load_run_history, run_agent_replay, run_managed_cycle, run_ml_update
from .migrations import MILESTONE1_MIGRATION_ID, MILESTONE1_POSTGRES_SQL
from .orchestrator import CollectorRunConfig, DailyRunConfig, run_collector, run_daily_analysis
from .production_readiness import build_production_readiness
from .proof_capture import load_json_file, write_production_cron_proof
from .reporting import PerformanceReporter
from .source_registry import SourceRegistry
from .state_store import PostgresStateStore, configured_database_url


def run_demo() -> int:
    result = Backtester().run(write_log=True)
    PerformanceReporter().write(result)
    print("Research-only sports odds MVP run complete.")
    print(f"Forecasts: {result.metrics['forecast_count']}")
    print(f"Paper trades: {result.metrics['paper_trade_count']}")
    print(f"Simulated ROI: {result.metrics['simulated_roi']:.1%}")
    print("Wrote data/paper_trades.jsonl and reports/performance_report.md")
    return 0


def run_multi_agent(source: str, target_count: int) -> int:
    result = MultiAgentPipeline().run(source_mode=source, target_count=target_count)
    output_path = Path("reports/multi_agent_run.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    PerformanceReporter().write_multi_agent(result)
    print("Polymarket multi-agent paper run complete.")
    print(f"Source: {result.source_mode} ({result.source_note})")
    print(f"Candidates: {result.metrics['candidate_count']}")
    print(f"Paper bets: {result.metrics['paper_bet_count']}")
    print(f"Top bets: {len(result.top_bets)}")
    print(f"Paper ROI: {result.metrics['simulated_roi']:.1%}")
    print("Wrote reports/multi_agent_run.json and reports/multi_agent_report.md")
    return 0


def list_sources(category: str | None, allowed_only: bool = False) -> int:
    registry = SourceRegistry()
    registry.require_valid()
    if category:
        sources = registry.for_category(
            category,
            include_global=category in ACTIVE_CATEGORIES,
            include_polymarket=category in ACTIVE_CATEGORIES,
            allowed_only=allowed_only,
        )
    else:
        sources = [source for source in registry.sources if source.allowed_by_default or not allowed_only]
    print(json.dumps([source.to_dict() for source in sources], indent=2, sort_keys=True))
    return 0


def research_bet(candidate_id: str) -> int:
    brief = BetResearchPlanner().brief_for_candidate_id(candidate_id)
    print(json.dumps(brief.to_dict(), indent=2, sort_keys=True))
    return 0


def research_topic(category: str, topic: str) -> int:
    brief = BetResearchPlanner().brief_for_topic(category, topic)
    print(json.dumps(brief.to_dict(), indent=2, sort_keys=True))
    return 0


def run_intelligence(source: str, target_count: int, cycle_type: str, no_codex: bool, no_queue: bool) -> int:
    payload = run_intelligence_cycle(
        cycle_type=cycle_type,
        source_mode=source,
        target_count=target_count,
        persist=True,
        allow_codex=not no_codex,
        queue_codex=not no_queue,
    )
    print(
        json.dumps(
            {
                "id": payload["id"],
                "status": payload["status"],
                "marketCount": payload["summary"]["marketCount"],
                "averageReliability": payload["summary"]["averageReliability"],
                "localCodexStatus": payload["localCodex"]["status"],
                "codexQueueStatus": payload.get("codexQueue", {}).get("status"),
                "codexQueuePendingCount": payload.get("codexQueue", {}).get("pendingCount"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] in {"success", "partial"} else 1


def run_codex_queue(limit: int, summary_only: bool) -> int:
    payload = queue_summary() if summary_only else drain_codex_queue(limit=limit)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status", "success") in {"success", "partial", "empty", "skipped"} else 1


def run_managed(source: str, target_count: int, cycle_type: str, global_review: bool, dry_run: bool) -> int:
    if dry_run:
        if source != "fixture":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "dryRun": True,
                        "reason": "Milestone 1 managed dry-run only supports fixture source to avoid live API calls.",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 2
        dashboard_payload = build_dashboard_payload(source_mode=source, target_count=target_count, use_cache=False)
        payload = {
            "ok": True,
            "dryRun": True,
            "research_only": True,
            "paper_trading_only": True,
            "cycleType": cycle_type,
            "sourceMode": source,
            "targetCount": target_count,
            "globalReview": global_review,
            "candidate_count": dashboard_payload["multi_agent"]["metrics"]["candidate_count"],
            "paper_bet_count": dashboard_payload["multi_agent"]["metrics"]["paper_bet_count"],
            "storage": {"written": False, "reason": "dry_run"},
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    payload = run_managed_cycle(
        cycle_type=cycle_type,
        source_mode=source,
        target_count=target_count,
        global_review=global_review,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def run_daily(source: str, target_count: int, dry_run: bool, as_of: str | None, force: bool) -> int:
    payload = run_daily_analysis(
        DailyRunConfig(
            source_mode=source,
            target_count=target_count,
            dry_run=dry_run,
            as_of=as_of,
            force=force,
        )
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def run_collector_cli(source: str, target_count: int, dry_run: bool, as_of: str | None, force: bool) -> int:
    payload = run_collector(
        CollectorRunConfig(
            source_mode=source,
            target_count=target_count,
            dry_run=dry_run,
            as_of=as_of,
            force=force,
        )
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def run_full_scan_cli(
    max_pages: int,
    page_size: int,
    top_limit: int,
    scan_date: str | None,
    all_active: bool,
    min_liquidity: float,
    max_spread: float,
    history_sample_limit: int,
    history_hours: int,
    history_fidelity: int,
    no_intelligence: bool,
    require_approved_top_limit: bool,
) -> int:
    payload = run_full_scan(
        max_pages=max_pages,
        page_size=page_size,
        top_limit=top_limit,
        scan_date=scan_date,
        current_day_only=not all_active,
        min_liquidity=min_liquidity,
        max_spread=max_spread,
        history_sample_limit=history_sample_limit,
        history_hours=history_hours,
        history_fidelity=history_fidelity,
        persist=True,
        run_intelligence=not no_intelligence,
    )
    print(json.dumps({"ok": True, **payload["summary"], "artifactPaths": payload.get("artifactPaths", {})}, indent=2, sort_keys=True))
    if require_approved_top_limit and not payload["summary"].get("topRecommendationTargetMet"):
        return 2
    return 0


def run_agents_replay_cli() -> int:
    payload = run_agent_replay()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def run_ml_update_cli(global_review: bool) -> int:
    payload = run_ml_update(global_review=global_review)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "success" else 1


def show_managed_state(kind: str) -> int:
    payload = {
        "run-history": load_run_history,
        "model-state": load_model_state,
        "correlations": load_correlations,
    }[kind]()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def run_migrations(dry_run: bool, proof_out: str | None = None) -> int:
    tables = sorted(set(re.findall(r"create table if not exists\s+([a-z_]+)", MILESTONE1_POSTGRES_SQL, flags=re.IGNORECASE)))
    indexes = sorted(set(re.findall(r"create (?:unique )?index if not exists\s+([a-z_]+)", MILESTONE1_POSTGRES_SQL, flags=re.IGNORECASE)))
    payload = {
        "ok": True,
        "dryRun": dry_run,
        "migrationId": MILESTONE1_MIGRATION_ID,
        "tableCount": len(tables),
        "tables": tables,
        "indexCount": len(indexes),
        "indexes": indexes,
        "researchOnly": True,
        "paperTradingOnly": True,
        "applied": False,
    }
    if dry_run:
        if proof_out:
            payload["proof"] = {"written": False, "reason": "dry_run"}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    database_url = configured_database_url()
    if not database_url:
        payload.update(
            {
                "ok": False,
                "error": "DATABASE_URL/POSTGRES_URL is not configured; no migration was applied.",
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2
    store = PostgresStateStore(database_url=database_url)
    result = store.apply_schema_migration(
        migration_id=MILESTONE1_MIGRATION_ID,
        sql=MILESTONE1_POSTGRES_SQL,
        required_tables=tables,
    )
    payload["storage"] = result
    payload["applied"] = bool(result.get("applied"))
    payload["verifiedTables"] = result.get("verifiedTables", [])
    payload["missingTables"] = result.get("missingTables", tables)
    payload["ok"] = bool(result.get("ok") and result.get("durable"))
    if proof_out:
        if payload["ok"]:
            proof_path = Path(proof_out)
            proof_path.parent.mkdir(parents=True, exist_ok=True)
            proof_payload = _build_postgres_migration_proof(payload)
            proof_path.write_text(json.dumps(proof_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload["proof"] = {"written": True, "path": str(proof_path)}
        else:
            payload["proof"] = {"written": False, "reason": "migration_not_ok", "path": proof_out}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def _build_postgres_migration_proof(migration_payload: dict[str, object]) -> dict[str, object]:
    storage = migration_payload.get("storage", {})
    storage_payload = storage if isinstance(storage, dict) else {}
    return {
        "proof_id": f"postgres_migration_{MILESTONE1_MIGRATION_ID}",
        "researchOnly": True,
        "paperTradingOnly": True,
        "migration": {
            "ok": bool(migration_payload.get("ok")),
            "applied": bool(migration_payload.get("applied")),
            "migrationId": migration_payload.get("migrationId"),
            "verifiedTables": migration_payload.get("verifiedTables", []),
            "missingTables": migration_payload.get("missingTables", []),
            "tableCount": migration_payload.get("tableCount"),
        },
        "storage": {
            "durable": bool(storage_payload.get("durable")),
            "storageMode": storage_payload.get("storageMode"),
        },
        "checks": {
            "database_url_value_exposed": False,
            "logs_contain_credentials": False,
            "wallet_or_order_execution_enabled": False,
        },
        "notes": [
            "Generated from sanitized migrate output only.",
            "No database URL, password, token, or credential value is stored in this proof artifact.",
        ],
    }


def run_goal_audit() -> int:
    payload = build_goal_audit()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def run_production_readiness() -> int:
    payload = build_production_readiness()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def run_external_proof_bundle(as_of: str | None) -> int:
    payload = build_external_proof_bundle(as_of=as_of)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def run_production_cron_proof(evidence_in: str, proof_out: str, dry_run: bool) -> int:
    evidence = load_json_file(evidence_in)
    payload = write_production_cron_proof(evidence, proof_out=proof_out, dry_run=dry_run)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Polymarket research-only paper analytics MVP")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run-demo", help="Run backtest, write paper log, and generate report")
    multi_agent = subparsers.add_parser("run-multi-agent", help="Run Polymarket multi-agent paper analytics")
    multi_agent.add_argument("--source", choices=["fixture", "live"], default="fixture")
    multi_agent.add_argument("--target-count", type=int, default=300)
    list_sources_parser = subparsers.add_parser("list-sources", help="List project source registry entries")
    list_sources_parser.add_argument("--category", choices=[*ACTIVE_CATEGORIES, "global", "polymarket"], default=None)
    list_sources_parser.add_argument("--allowed-only", action="store_true", help="Show only sources allowed by default")
    research_bet_parser = subparsers.add_parser("research-bet", help="Build a fixture-backed research brief for a candidate")
    research_bet_parser.add_argument("--candidate-id", required=True)
    research_topic_parser = subparsers.add_parser("research-topic", help="Build a fixture-backed research plan for a category/topic")
    research_topic_parser.add_argument("--category", choices=ACTIVE_CATEGORIES, required=True)
    research_topic_parser.add_argument("--topic", required=True)
    intelligence_parser = subparsers.add_parser("run-intelligence", help="Run deterministic/local-Codex intelligence analysis")
    intelligence_parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    intelligence_parser.add_argument("--target-count", type=int, default=300)
    intelligence_parser.add_argument("--cycle-type", choices=["scheduled_15m", "post_ingestion", "manual"], default="manual")
    intelligence_parser.add_argument("--no-codex", action="store_true")
    intelligence_parser.add_argument("--no-queue", action="store_true")
    codex_queue_parser = subparsers.add_parser("drain-codex-queue", help="Drain queued local Codex intelligence backfills")
    codex_queue_parser.add_argument("--limit", type=int, default=12)
    codex_queue_parser.add_argument("--summary", action="store_true")
    managed_parser = subparsers.add_parser("run-managed-cycle", help="Run one durable managed collection/agent/ML cycle")
    managed_parser.add_argument("--source", choices=["fixture", "live"], default="live")
    managed_parser.add_argument("--target-count", type=int, default=300)
    managed_parser.add_argument("--cycle-type", choices=["scheduled_15m", "post_ingestion", "manual"], default="scheduled_15m")
    managed_parser.add_argument("--global-review", action="store_true")
    managed_parser.add_argument("--dry-run", action="store_true", help="Build the managed payload without writing state")
    daily_parser = subparsers.add_parser("run-daily", help="Run the fixture-first daily analytical orchestrator contract")
    daily_parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    daily_parser.add_argument("--target-count", type=int, default=30)
    daily_parser.add_argument("--dry-run", action="store_true", help="Validate the daily run without writing state")
    daily_parser.add_argument("--as-of", default=None, help="ISO date or datetime used for the Europe/Sofia 09:00 run key")
    daily_parser.add_argument("--force", action="store_true", help="Allow a non-dry-run write even when the idempotency key exists")
    collector_parser = subparsers.add_parser("run-collector", help="Run the 15-minute read-only Data Agent collector")
    collector_parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    collector_parser.add_argument("--target-count", type=int, default=30)
    collector_parser.add_argument("--dry-run", action="store_true", help="Collect and validate without writing state")
    collector_parser.add_argument("--as-of", default=None, help="ISO date or datetime used for the 15-minute UTC bucket key")
    collector_parser.add_argument("--force", action="store_true", help="Allow a non-dry-run write even when the idempotency key exists")
    full_scan_parser = subparsers.add_parser("run-full-scan", help="Run a public read-only full Gamma scan and top approved paper-bet ranking")
    full_scan_parser.add_argument("--max-pages", type=int, default=30)
    full_scan_parser.add_argument("--page-size", type=int, default=100)
    full_scan_parser.add_argument("--top-limit", type=int, default=100)
    full_scan_parser.add_argument("--scan-date", default=None)
    full_scan_parser.add_argument("--all-active", action="store_true")
    full_scan_parser.add_argument("--min-liquidity", type=float, default=1.0)
    full_scan_parser.add_argument("--max-spread", type=float, default=0.25)
    full_scan_parser.add_argument("--history-sample-limit", type=int, default=200)
    full_scan_parser.add_argument("--history-hours", type=int, default=24)
    full_scan_parser.add_argument("--history-fidelity", type=int, default=60)
    full_scan_parser.add_argument("--no-intelligence", action="store_true")
    full_scan_parser.add_argument(
        "--require-approved-top-limit",
        action="store_true",
        help="Exit non-zero unless the top output contains top-limit approved PAPER_BET rows with positive stake.",
    )
    subparsers.add_parser("run-agent-replay", help="Replay unprocessed persisted runs chronologically")
    ml_parser = subparsers.add_parser("run-ml-update", help="Update online ML and correlation state from persisted runs")
    ml_parser.add_argument("--global-review", action="store_true")
    state_parser = subparsers.add_parser("managed-state", help="Print managed pipeline state")
    state_parser.add_argument("kind", choices=["run-history", "model-state", "correlations"])
    migrate_parser = subparsers.add_parser("migrate", help="Validate or apply Postgres schema migrations")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Validate migration metadata without applying SQL")
    migrate_parser.add_argument(
        "--proof-out",
        default=None,
        help=f"Write sanitized Postgres migration proof after a successful real migration, for example {POSTGRES_PROOF_PATH}",
    )
    subparsers.add_parser("goal-audit", help="Audit current repo evidence against the active Polymarket system goal")
    subparsers.add_parser("production-readiness", help="Validate local GitHub Actions/Vercel readiness without deploying")
    proof_parser = subparsers.add_parser(
        "external-proof-bundle",
        help="Print the remaining external proof checklist without writing, deploying, or calling live APIs",
    )
    proof_parser.add_argument("--as-of", default=None, help="Optional ISO timestamp/date to include in the proof bundle")
    cron_proof_parser = subparsers.add_parser(
        "production-cron-proof",
        help="Build sanitized production cron proof from approved evidence JSON without fetching logs",
    )
    cron_proof_parser.add_argument("--evidence-in", required=True, help="Path to operator-approved sanitized cron evidence JSON")
    cron_proof_parser.add_argument(
        "--proof-out",
        default=PRODUCTION_CRON_PROOF_PATH,
        help=f"Path for sanitized proof output, default {PRODUCTION_CRON_PROOF_PATH}",
    )
    cron_proof_parser.add_argument("--dry-run", action="store_true", help="Validate and print proof without writing it")
    args = parser.parse_args()

    if args.command == "run-demo":
        return run_demo()
    if args.command == "run-multi-agent":
        return run_multi_agent(args.source, args.target_count)
    if args.command == "list-sources":
        return list_sources(args.category, args.allowed_only)
    if args.command == "research-bet":
        return research_bet(args.candidate_id)
    if args.command == "research-topic":
        return research_topic(args.category, args.topic)
    if args.command == "run-intelligence":
        return run_intelligence(args.source, args.target_count, args.cycle_type, args.no_codex, args.no_queue)
    if args.command == "drain-codex-queue":
        return run_codex_queue(args.limit, args.summary)
    if args.command == "run-managed-cycle":
        return run_managed(args.source, args.target_count, args.cycle_type, args.global_review, args.dry_run)
    if args.command == "run-daily":
        return run_daily(args.source, args.target_count, args.dry_run, args.as_of, args.force)
    if args.command == "run-collector":
        return run_collector_cli(args.source, args.target_count, args.dry_run, args.as_of, args.force)
    if args.command == "run-full-scan":
        return run_full_scan_cli(
            args.max_pages,
            args.page_size,
            args.top_limit,
            args.scan_date,
            args.all_active,
            args.min_liquidity,
            args.max_spread,
            args.history_sample_limit,
            args.history_hours,
            args.history_fidelity,
            args.no_intelligence,
            args.require_approved_top_limit,
        )
    if args.command == "run-agent-replay":
        return run_agents_replay_cli()
    if args.command == "run-ml-update":
        return run_ml_update_cli(args.global_review)
    if args.command == "managed-state":
        return show_managed_state(args.kind)
    if args.command == "migrate":
        return run_migrations(args.dry_run, args.proof_out)
    if args.command == "goal-audit":
        return run_goal_audit()
    if args.command == "production-readiness":
        return run_production_readiness()
    if args.command == "external-proof-bundle":
        return run_external_proof_bundle(args.as_of)
    if args.command == "production-cron-proof":
        return run_production_cron_proof(args.evidence_in, args.proof_out, args.dry_run)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
