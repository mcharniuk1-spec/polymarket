from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents import ACTIVE_CATEGORIES, MultiAgentPipeline
from .backtesting import Backtester
from .bet_research import BetResearchPlanner
from .codex_queue import drain_codex_queue, queue_summary
from .full_scan import run_full_scan
from .intelligence import run_intelligence_cycle
from .managed_pipeline import load_correlations, load_model_state, load_run_history, run_agent_replay, run_managed_cycle, run_ml_update
from .reporting import PerformanceReporter
from .source_registry import SourceRegistry


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


def run_managed(source: str, target_count: int, cycle_type: str, global_review: bool) -> int:
    payload = run_managed_cycle(
        cycle_type=cycle_type,
        source_mode=source,
        target_count=target_count,
        global_review=global_review,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Sports odds research MVP")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run-demo", help="Run backtest, write paper log, and generate report")
    multi_agent = subparsers.add_parser("run-multi-agent", help="Run Polymarket multi-agent paper analytics")
    multi_agent.add_argument("--source", choices=["fixture", "live"], default="fixture")
    multi_agent.add_argument("--target-count", type=int, default=600)
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
    full_scan_parser = subparsers.add_parser("run-full-scan", help="Run a public read-only full Gamma scan and top-100 paper ranking")
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
    subparsers.add_parser("run-agent-replay", help="Replay unprocessed persisted runs chronologically")
    ml_parser = subparsers.add_parser("run-ml-update", help="Update online ML and correlation state from persisted runs")
    ml_parser.add_argument("--global-review", action="store_true")
    state_parser = subparsers.add_parser("managed-state", help="Print managed pipeline state")
    state_parser.add_argument("kind", choices=["run-history", "model-state", "correlations"])
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
        return run_managed(args.source, args.target_count, args.cycle_type, args.global_review)
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
        )
    if args.command == "run-agent-replay":
        return run_agents_replay_cli()
    if args.command == "run-ml-update":
        return run_ml_update_cli(args.global_review)
    if args.command == "managed-state":
        return show_managed_state(args.kind)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
