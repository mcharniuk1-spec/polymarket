from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from sports_edge.backtesting import Backtester
from sports_edge.agents import ACTIVE_CATEGORIES, MarketDataAgent, MultiAgentPipeline
from sports_edge.app import health_payload
from sports_edge.bet_research import BetResearchPlanner
from sports_edge.codex_queue import drain_codex_queue, enqueue_codex_review, queue_summary
from sports_edge.cli import run_durable_daily_proof, run_live_source_proof, run_migrations, run_production_cron_proof
from sports_edge.dashboard_data import build_dashboard_payload, build_report_text
from sports_edge.dashboard_api import (
    dashboard_contract_from_daily,
    legacy_scope_disabled_payload,
    load_dashboard_contract,
    runs_history_payload,
    runs_latest_payload,
    scoped_compat_dashboard,
    section_payload,
)
from sports_edge.context_agent import ContextAgent
from sports_edge.data_agent import DataAgent, infer_market_category, normalize_gamma_market, normalize_order_book
from sports_edge.decision_agent import DecisionAgent, PortfolioRules
from sports_edge.external_adapters import collect_external_adapter_bundle
from sports_edge.external_proof import build_external_proof_bundle
import sports_edge.goal_audit as goal_audit_module
from sports_edge.full_scan import run_full_scan
from sports_edge.goal_audit import build_goal_audit
from sports_edge.full_scan import _normalize_category as normalize_full_scan_category
from sports_edge.intelligence import run_intelligence_cycle, validate_news_sources
from sports_edge.managed_pipeline import run_agent_replay, run_managed_cycle, run_ml_update
from sports_edge.managed_pipeline import _correlation_pairs
from sports_edge.migrations import MILESTONE1_MIGRATION_ID, MILESTONE1_POSTGRES_SQL
from sports_edge.model_scoring import score_market_candidates
from sports_edge.odds_math import american_to_decimal, american_to_implied_probability
from sports_edge.orchestrator import CollectorRunConfig, DailyRunConfig, run_collector, run_daily_analysis
from sports_edge.outcome_evaluator import evaluate_previous_paper_bets
from sports_edge.production_readiness import build_production_readiness
from sports_edge.proof_capture import (
    build_durable_daily_proof,
    build_live_source_proof,
    build_production_cron_proof,
    validate_durable_daily_proof,
    validate_live_source_proof,
    validate_production_cron_proof,
)
from sports_edge.reporting import PerformanceReporter
from sports_edge.risk_control import RESEARCH_ONLY_MODE, RiskControl
from sports_edge.safety import SafetyGateError, assert_paper_trading_only
from sports_edge.schemas import DecisionNote, KnowledgeLesson, MODEL_FAMILIES, PaperBet, ResolvedOutcome, stable_id
from sports_edge.source_registry import SourceRegistry
from sports_edge.state_store import JsonStateStore, PostgresStateStore
from sports_edge.vercel_api import cron_authorized


ROOT = Path(__file__).resolve().parents[1]


def _fake_gamma_market(index: int) -> dict[str, object]:
    price = 0.42 + ((index % 10) / 100.0)
    return {
        "id": str(1000 + index),
        "question": f"Will NVDA close above test threshold #{index}?",
        "conditionId": f"condition-{index}",
        "slug": f"fake-market-{index}",
        "resolutionSource": "https://example.com/resolution",
        "endDate": "2026-05-30T00:00:00Z",
        "liquidity": "10000",
        "liquidityNum": 10000 + index,
        "volume": "100",
        "volume24hr": 100 + index,
        "active": True,
        "closed": False,
        "archived": False,
        "createdAt": "2026-05-29T08:00:00Z",
        "updatedAt": "2026-05-29T08:05:00Z",
        "enableOrderBook": True,
        "acceptingOrders": True,
        "outcomes": '["Yes","No"]',
        "outcomePrices": json.dumps([round(price, 3), round(1.0 - price, 3)]),
        "clobTokenIds": json.dumps([f"token-{index}-yes", f"token-{index}-no"]),
        "bestBid": max(price - 0.01, 0.0),
        "bestAsk": min(price + 0.01, 1.0),
        "spread": 0.02,
        "oneHourPriceChange": 0.01,
        "oneDayPriceChange": -0.01,
        "oneWeekPriceChange": 0.02,
        "description": (
            "Fixture public market metadata for full-scan pagination test with explicit settlement wording, "
            "objective resolution source, and enough detail to avoid ambiguity rejects."
        ),
        "events": [
            {
                "id": f"event-{index // 2}",
                "slug": f"event-{index // 2}",
                "title": f"NVDA threshold event {index // 2}",
                "description": "Event metadata",
                "resolutionSource": "https://example.com/resolution",
                "createdAt": "2026-05-29T08:00:00Z",
                "updatedAt": "2026-05-29T08:05:00Z",
                "series": [{"title": "NVDA thresholds", "slug": "nvda-thresholds"}],
            }
        ],
    }


class OddsMathTests(unittest.TestCase):
    def test_american_odds_conversion(self) -> None:
        self.assertAlmostEqual(american_to_decimal(150), 2.5)
        self.assertAlmostEqual(american_to_decimal(-200), 1.5)
        self.assertAlmostEqual(american_to_implied_probability(150), 0.4)
        self.assertAlmostEqual(american_to_implied_probability(-200), 0.6666666, places=5)


class PipelineTests(unittest.TestCase):
    def test_multi_agent_pipeline_analyzes_categories_and_allocates_paper_budget(self) -> None:
        result = MultiAgentPipeline().run(source_mode="fixture", target_count=300)
        self.assertTrue(result.metrics["research_only"])
        self.assertTrue(result.metrics["paper_trading_only"])
        self.assertEqual(result.metrics["active_sections"], list(ACTIVE_CATEGORIES))
        self.assertEqual(result.metrics["candidate_count"], 300)
        self.assertEqual(len(result.category_stats), 3)
        self.assertTrue(all(row["candidate_count"] == 100 for row in result.category_stats))
        self.assertEqual([row["id"] for row in result.agent_contract["agents"]], ["context_agent", "data_agent", "decision_agent"])
        self.assertEqual(len(result.top_bets), 10)
        self.assertAlmostEqual(result.metrics["total_staked_units"], 100.0)
        self.assertAlmostEqual(result.metrics["deployment_budget_units"], 100.0)
        self.assertAlmostEqual(result.metrics["unallocated_budget_units"], 0.0)
        self.assertTrue(all(item["mode"] == "paper" if "mode" in item else True for item in result.top_bets))
        self.assertTrue(all("assessments" in item for item in result.recommendations))

    def test_dashboard_payload_has_explicit_bet_records_and_news_graph(self) -> None:
        payload = build_dashboard_payload(source_mode="fixture", target_count=300, use_cache=False)
        multi_agent = payload["multi_agent"]
        self.assertTrue(payload["research_only"])
        self.assertTrue(payload["paper_trading_only"])
        self.assertTrue(payload["legacySportsDisabled"])
        self.assertEqual(payload["active_sections"], list(ACTIVE_CATEGORIES))
        self.assertEqual(payload["forecasts"], [])
        self.assertEqual(payload["trades"], [])
        self.assertEqual(payload["odds_history"], [])
        self.assertEqual(payload["metrics"]["forecast_count"], 0)
        self.assertEqual(len(multi_agent["bet_detail_records"]), multi_agent["metrics"]["candidate_count"])
        self.assertEqual(multi_agent["portfolio_rules"]["target_bankroll_units"], 100.0)
        self.assertGreaterEqual(multi_agent["collection_plan"]["public_api_count"], 20)
        self.assertGreater(len(multi_agent["news_influence_graph"]["nodes"]), 0)
        self.assertGreater(len(multi_agent["event_groups"]), 0)
        first_record = multi_agent["bet_detail_records"][0]
        self.assertTrue(first_record["decision_steps"])
        self.assertTrue(first_record["source_review_ids"])
        self.assertTrue(multi_agent["source_reviews_by_category"])
        self.assertTrue(first_record["model_cards"])
        self.assertTrue(first_record["monitored_values"])

    def test_scoped_compat_dashboard_removes_legacy_sports_root_data(self) -> None:
        payload = build_dashboard_payload(source_mode="fixture", target_count=30, use_cache=False)
        scoped = scoped_compat_dashboard(payload)

        self.assertTrue(scoped["research_only"])
        self.assertTrue(scoped["paper_trading_only"])
        self.assertTrue(scoped["legacySportsDisabled"])
        self.assertEqual(scoped["active_sections"], list(ACTIVE_CATEGORIES))
        self.assertEqual(scoped["forecasts"], [])
        self.assertEqual(scoped["trades"], [])
        self.assertEqual(scoped["odds_history"], [])
        self.assertEqual(scoped["metrics"]["forecast_count"], 0)
        self.assertEqual(scoped["multi_agent"]["metrics"]["active_sections"], list(ACTIVE_CATEGORIES))

    def test_legacy_backtest_routes_are_scope_disabled(self) -> None:
        for section in ("summary", "forecasts", "odds-history"):
            payload = legacy_scope_disabled_payload(section)
            self.assertTrue(payload["disabled"])
            self.assertTrue(payload["legacySportsDisabled"])
            self.assertEqual(payload["active_sections"], list(ACTIVE_CATEGORIES))
        self.assertEqual(legacy_scope_disabled_payload("forecasts")["forecasts"], [])
        self.assertEqual(legacy_scope_disabled_payload("odds-history")["odds_history"], [])

    def test_dashboard_report_text_is_multi_agent_scoped(self) -> None:
        text = build_report_text(source_mode="fixture", target_count=30)
        self.assertIn("Polymarket Multi-Agent Paper Analytics Report", text)
        self.assertIn("paper-only research analytics", text)
        self.assertIn("macroeconomics", text)

    def test_backtest_writes_paper_log_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "paper_trades.jsonl"
            result = Backtester(paper_log_path=log_path).run(write_log=True)
            self.assertTrue(result.metrics["research_only"])
            self.assertGreater(result.metrics["forecast_count"], 0)
            self.assertGreater(result.metrics["paper_trade_count"], 0)
            self.assertTrue(log_path.exists())
            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), result.metrics["paper_trade_count"])
            self.assertTrue(all(row["mode"] == "paper" for row in rows))

    def test_reporter_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "performance_report.md"
            json_path = Path(temp_dir) / "performance_report.json"
            result = Backtester(paper_log_path=Path(temp_dir) / "paper.jsonl").run(write_log=True)
            PerformanceReporter(report_path=report_path, json_path=json_path).write(result)
            self.assertIn("research-only paper trading", report_path.read_text(encoding="utf-8"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("metrics", payload)
            self.assertIn("trades", payload)

    def test_risk_control_has_no_execution_mode(self) -> None:
        decision = RiskControl().evaluate(
            fair_probability=0.62,
            expected_value=0.10,
            confidence=0.20,
            american_odds=110,
            current_day_exposure=0.0,
        )
        self.assertEqual(RESEARCH_ONLY_MODE, "paper")
        self.assertIn(decision.decision, {"PAPER_TRADE", "NO_PLAY"})


class ProjectSkillsTests(unittest.TestCase):
    def test_project_skills_have_frontmatter(self) -> None:
        skill_paths = sorted((ROOT / "docs" / "ai" / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(skill_paths), 10)
        for path in skill_paths:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), path)
            frontmatter = text.split("---", 2)[1]
            fields = {}
            for line in frontmatter.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip()] = value.strip()
            self.assertTrue(fields.get("name"), path)
            self.assertTrue(fields.get("description"), path)


class SourceRegistryTests(unittest.TestCase):
    def test_source_registry_is_valid_and_covers_categories(self) -> None:
        registry = SourceRegistry()
        self.assertEqual(registry.validate(), [])
        for category in ACTIVE_CATEGORIES:
            sources = registry.for_category(category)
            high_reliability = [source for source in sources if source.reliability_tier in {"primary", "high"}]
            self.assertGreaterEqual(len(sources), 5, category)
            self.assertGreaterEqual(len(high_reliability), 2, category)

    def test_per_bet_research_briefs_cover_each_category(self) -> None:
        planner = BetResearchPlanner()
        candidates = MarketDataAgent().load_candidates(source_mode="fixture", target_count=300)
        first_by_category = {}
        for candidate in candidates:
            first_by_category.setdefault(candidate.category, candidate)

        for category in ACTIVE_CATEGORIES:
            brief = planner.brief_for_candidate(first_by_category[category])
            payload = brief.to_dict()
            self.assertEqual(payload["category"], category)
            self.assertGreaterEqual(payload["source_coverage"]["category_source_count"], 5)
            self.assertGreater(payload["source_coverage"]["planned_source_count"], 0)
            self.assertTrue(payload["planned_queries"])
            self.assertIn("global_context_score", payload)
            self.assertIn("category_context_score", payload)
            self.assertIn("bet_research_score", payload)

    def test_intelligence_sources_and_fallback_schema(self) -> None:
        self.assertEqual(validate_news_sources(), [])
        payload = run_intelligence_cycle(
            cycle_type="manual",
            source_mode="fixture",
            target_count=24,
            persist=False,
            allow_codex=False,
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["localCodex"]["status"], "skipped")
        self.assertEqual(payload["summary"]["marketCount"], 24)
        first = payload["marketAnalysisResults"][0]
        self.assertIn(first["decisionCommentary"]["signal"], {"watch", "bullish", "bearish", "neutral", "avoid"})
        self.assertTrue(first["decisionCommentary"]["notFinancialAdvice"])
        self.assertIn(first["reliability"]["label"], {"reliable", "possible/probable", "unreliable/reject"})
        self.assertIn("forecastChart", first)
        self.assertIn("strongestSources", first["newsContext"])
        self.assertEqual(payload["codexQueue"]["status"], "emitted_not_persisted")
        self.assertFalse(payload["codexQueue"]["durable"])

    def test_full_scan_uses_paginated_gamma_and_top_limit(self) -> None:
        class FakeFullScanClient:
            def __init__(self) -> None:
                self.pages = [
                    [_fake_gamma_market(index) for index in range(60)],
                    [_fake_gamma_market(index) for index in range(60, 120)],
                    [],
                ]
                self.calls = []

            def fetch_gamma_markets(self, limit: int, offset: int, active: bool, closed: bool, order: str):
                self.calls.append({"limit": limit, "offset": offset, "active": active, "closed": closed, "order": order})
                page_index = 0 if offset == 0 else 1 if offset == 60 else 2
                return self.pages[page_index]

            def fetch_price_history(self, token_id: str, start_ts: int | None = None, end_ts: int | None = None, fidelity: int = 60):
                return {
                    "history": [
                        {"t": 1780041600, "p": 0.41},
                        {"t": 1780045200, "p": 0.43},
                        {"t": 1780048800, "p": 0.45},
                    ]
                }

        client = FakeFullScanClient()
        payload = run_full_scan(
            max_pages=3,
            page_size=60,
            top_limit=25,
            scan_date="2026-05-29",
            current_day_only=True,
            persist=False,
            run_intelligence=False,
            client=client,
        )
        self.assertTrue(payload["summary"]["research_only"])
        self.assertEqual(payload["summary"]["rawMarketCount"], 120)
        self.assertEqual(payload["summary"]["candidateOutcomeCount"], 240)
        self.assertEqual(payload["summary"]["topRecommendationCount"], 25)
        self.assertTrue(payload["summary"]["topRecommendationTargetMet"])
        self.assertEqual(payload["summary"]["approvedPaperBetShortfall"], 0)
        self.assertTrue(all(row["decision"] == "PAPER_BET" and row["stake_units"] > 0 for row in payload["top100"]))
        self.assertAlmostEqual(payload["summary"]["paperBetCount"], 25)
        self.assertAlmostEqual(payload["multiAgent"]["metrics"]["total_staked_units"], 100.0)
        self.assertGreater(payload["summary"]["eventGroupCount"], 0)
        self.assertEqual(payload["summary"]["timeSeries"]["observedHistoryCount"], 200)
        self.assertTrue(payload["agentSourceMatrix"]["rows"])
        self.assertTrue(payload["correlations"]["categories"])
        self.assertEqual(client.calls[0]["offset"], 0)
        self.assertEqual(client.calls[1]["offset"], 60)

    def test_full_scan_category_classifier_uses_active_scope_and_rejects_out_of_scope(self) -> None:
        self.assertIsNone(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will Warsaw reach the daily weather temperature threshold?",
                {"title": "Warsaw Daily Weather", "series": [{"title": "Warsaw Daily Weather"}]},
            )
        )
        self.assertIsNone(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will Team A win in the T20 Blast?",
                {"title": "T20 Blast", "series": [{"title": "T20 Blast"}]},
            )
        )
        self.assertIsNone(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will HYPE go up in this five minute window?",
                {"title": "HYPE Up or Down 5m", "series": [{"title": "HYPE Up or Down 5m"}]},
            )
        )
        self.assertEqual(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will Google (GOOGL) close above $390 on June 1?",
                {"title": "GOOGL Multi Strikes Weekly", "series": [{"title": "GOOGL Multi Strikes Weekly"}]},
            ),
            "stocks_trade",
        )
        self.assertIsNone(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will the home team win in Germany BBL this weekend?",
                {"title": "Germany BBL", "series": [{"title": "Germany BBL"}]},
            )
        )
        self.assertEqual(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will CPI resolve above consensus in the release window?",
                {"title": "CPI release", "series": [{"title": "CPI release"}]},
            ),
            "macroeconomics",
        )
        self.assertEqual(
            normalize_full_scan_category(
                {"category": "", "tags": ""},
                "Will the Senate pass the tariff bill before the deadline?",
                {"title": "Congress policy", "series": [{"title": "US Politics"}]},
            ),
            "stocks_trade",
        )

    def test_correlation_pairs_mark_endogenous_and_fallback_history_as_diagnostic_only(self) -> None:
        base_history = [
            {"time": "2026-05-29T10:00:00Z", "price": 0.40, "source": "clob-prices-history"},
            {"time": "2026-05-29T10:10:00Z", "price": 0.43, "source": "clob-prices-history"},
            {"time": "2026-05-29T10:20:00Z", "price": 0.45, "source": "clob-prices-history"},
            {"time": "2026-05-29T10:30:00Z", "price": 0.47, "source": "clob-prices-history"},
        ]
        same_event = [
            {"candidate_id": "a", "event_id": "event-1", "market_title": "Team A wins", "actors": ["Team A"], "odds_history": base_history},
            {"candidate_id": "b", "event_id": "event-1", "market_title": "Team B wins", "actors": ["Team B"], "odds_history": base_history},
        ]
        pair = _correlation_pairs(same_event)[0]
        self.assertEqual(pair["influenceRole"], "exposure_only_endogenous_sibling")
        self.assertEqual(pair["contextWeight"], 0.0)

        fallback = [
            {"candidate_id": "c", "event_id": "event-2", "market_title": "Team C wins", "actors": ["Team C"], "odds_history": [{**row, "source": "gamma-one-hour-change"} for row in base_history]},
            {"candidate_id": "d", "event_id": "event-3", "market_title": "Team C threshold", "actors": ["Team C"], "odds_history": [{**row, "source": "gamma-one-hour-change"} for row in base_history]},
        ]
        pair = _correlation_pairs(fallback)[0]
        self.assertEqual(pair["influenceRole"], "diagnostic_only_fallback_history")
        self.assertEqual(pair["contextWeight"], 0.0)

    def test_codex_queue_persists_pending_work_and_skips_when_codex_disabled(self) -> None:
        payload = run_intelligence_cycle(
            cycle_type="manual",
            source_mode="fixture",
            target_count=6,
            persist=False,
            allow_codex=False,
            queue_codex=False,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_dir = Path(temp_dir) / "queue"
            result = enqueue_codex_review(payload, reason="test", queue_dir=queue_dir)
            self.assertEqual(result["status"], "queued")
            self.assertEqual(queue_summary(queue_dir=queue_dir)["pendingCount"], 1)
            with mock.patch.dict(os.environ, {"ENABLE_LOCAL_CODEX_ANALYSIS": "false"}, clear=False):
                drain = drain_codex_queue(queue_dir=queue_dir)
            self.assertEqual(drain["status"], "skipped")
            self.assertEqual(drain["pendingCount"], 1)

    def test_cron_authorization_uses_bearer_secret_when_configured(self) -> None:
        with mock.patch.dict(os.environ, {"CRON_SECRET": "secret-value"}, clear=False):
            self.assertTrue(cron_authorized({"Authorization": "Bearer secret-value"}))
            self.assertFalse(cron_authorized({"Authorization": "Bearer wrong"}))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(cron_authorized({}))

    def test_managed_cycle_persists_chronological_agent_and_ml_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            first = run_managed_cycle(cycle_type="manual", source_mode="fixture", target_count=18, store=store)
            second = run_managed_cycle(cycle_type="manual", source_mode="fixture", target_count=24, store=store)
            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            history = store.read_json("run_history.json")
            self.assertEqual(len(history["runs"]), 2)
            self.assertEqual(history["runs"][1]["previousRunId"], history["runs"][0]["id"])
            replay = run_agent_replay(store=store)
            self.assertIn("processedRunCount", replay)
            agent_state = store.read_json("agent_decisions.json")
            self.assertTrue(agent_state["processedRunIds"])
            for timeline in agent_state["betTimelines"].values():
                for entry in timeline:
                    for news in entry["sourceContext"]["newsItems"]:
                        self.assertLessEqual(news.get("time", ""), entry["timestamp"])
            ml = run_ml_update(store=store, global_review=True)
            self.assertGreater(ml["updatedModelCount"], 0)
            self.assertIn("categories", ml["correlations"])

    def test_cli_research_and_source_commands(self) -> None:
        commands = [
            [sys.executable, "-m", "sports_edge.cli", "list-sources", "--category", "stocks_trade"],
            [sys.executable, "-m", "sports_edge.cli", "research-bet", "--candidate-id", "fixture-stocks_trade-001"],
            [
                sys.executable,
                "-m",
                "sports_edge.cli",
                "research-topic",
                "--category",
                "politics",
                "--topic",
                "election certification deadline",
            ],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload)


def _valid_cron_evidence() -> dict[str, object]:
    return {
        "asOf": "2026-06-11",
        "run": {
            "id": "27327476929",
            "event": "schedule",
            "status": "completed",
            "conclusion": "success",
            "workflow": "Polymarket 15m Research Cycle",
            "url": "https://github.com/example/polymarket/actions/runs/27327476929?token=secret-token",
        },
        "scheduledJobs": {
            "collector_15m": {
                "observed": True,
                "status": "success",
                "sourceMode": "live",
                "idempotencyKey": "collector:2026-06-11T06:00:00Z",
                "runId": "collector-20260611T060000Z",
                "scheduledFor": "2026-06-11T06:00:00Z",
            },
            "sofia_daily": {
                "observed": True,
                "status": "success",
                "sourceMode": "live",
                "idempotencyKey": "daily:2026-06-11",
                "runId": "daily-2026-06-11",
                "scheduledFor": "2026-06-11T06:00:00Z",
            },
        },
        "checks": {
            "paper_trading_only": True,
            "durable_storage_gate_passed": True,
            "logs_contain_credentials": False,
            "dashboard_reflects_run": True,
            "wallet_or_order_execution_enabled": False,
        },
    }


def _valid_live_source_evidence() -> dict[str, object]:
    return {
        "asOf": "2026-06-11",
        "run": {
            "id": "live-dry-run-20260611",
            "sourceMode": "live",
            "asOf": "2026-06-11T06:00:00Z",
            "command": "python3 -m sports_edge.cli run-daily --source live --dry-run",
        },
        "categories": {
            "macroeconomics": {
                "observed": True,
                "sourceCount": 3,
                "parserVerifiedObservationCount": 2,
                "marketRuleCount": 4,
                "resolutionProofCount": 1,
            },
            "politics": {
                "observed": True,
                "sourceCount": 3,
                "parserVerifiedObservationCount": 2,
                "marketRuleCount": 4,
                "resolutionProofCount": 1,
            },
            "stocks_trade": {
                "observed": True,
                "sourceCount": 3,
                "parserVerifiedObservationCount": 2,
                "marketRuleCount": 4,
                "resolutionProofCount": 1,
            },
        },
        "checks": {
            "read_only_public_sources": True,
            "tos_review_completed": True,
            "parser_verified_numeric_observations": True,
            "source_health_only_not_decision_evidence": True,
            "rules_resolution_captured": True,
            "live_resolution_proof_validated": True,
            "resolved_outcome_public_proof_url_captured": True,
            "wallet_or_order_execution_enabled": False,
            "logs_contain_credentials": False,
        },
    }


def _valid_durable_daily_evidence() -> dict[str, object]:
    return {
        "asOf": "2026-06-10",
        "firstRun": {
            "runId": "daily-2026-06-10-first",
            "sourceMode": "fixture",
            "status": "success",
            "idempotencyKey": "daily:2026-06-10",
            "storageWritten": True,
        },
        "duplicateRun": {
            "runId": "daily-2026-06-10-duplicate",
            "sourceMode": "fixture",
            "status": "duplicate_skipped",
            "idempotencyKey": "daily:2026-06-10",
            "storageWritten": False,
        },
        "storage": {
            "durable": True,
            "storageMode": "postgres",
        },
        "checks": {
            "duplicate_write_protected": True,
            "dry_run": False,
            "logs_contain_credentials": False,
            "wallet_or_order_execution_enabled": False,
        },
    }


class MilestoneOneContractTests(unittest.TestCase):
    def test_daily_orchestrator_dry_run_validates_contract_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            with mock.patch.dict(os.environ, {}, clear=True):
                payload = run_daily_analysis(
                    DailyRunConfig(source_mode="fixture", target_count=30, dry_run=True, as_of="2026-06-10"),
                    store=store,
                )

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["dryRun"])
            self.assertFalse(payload["storage"]["written"])
            self.assertEqual(payload["cronRun"]["status"], "dry_run")
            self.assertEqual(payload["cronRun"]["scheduled_for"], "2026-06-10T06:00:00Z")
            self.assertEqual(payload["activeSections"], list(ACTIVE_CATEGORIES))
            broad_reports = [row for row in payload["contextReports"] if row["scope"] == "broad_category"]
            bet_reports = [row for row in payload["contextReports"] if row["scope"] == "bet_specific"]
            self.assertEqual(len(broad_reports), len(ACTIVE_CATEGORIES))
            self.assertGreaterEqual(len(bet_reports), 1)
            self.assertEqual(len(payload["modelOutputs"]), len(ACTIVE_CATEGORIES) * len(MODEL_FAMILIES))
            self.assertTrue(all(row["market_id"] in {market["market_id"] for market in payload["dataAgent"]["marketSnapshots"]} for row in payload["decisionSignals"]))
            self.assertTrue(all(row["decision"] in {"reject", "watchlist", "paper_bet"} for row in payload["decisionSignals"]))
            self.assertTrue(all(row["stake_units"] == 0.0 for row in payload["decisionSignals"]))
            self.assertTrue(any(row["model_family"] == "portfolio_ev_risk" for row in payload["modelOutputs"]))
            self.assertTrue(payload["schemaValidation"]["ok"])
            self.assertIsNone(store.read_json("daily_runs/latest.json", default=None))

    def test_daily_orchestrator_duplicate_run_protection_uses_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            config = DailyRunConfig(source_mode="fixture", target_count=30, dry_run=False, as_of="2026-06-10")
            with mock.patch.dict(os.environ, {}, clear=True):
                first = run_daily_analysis(config, store=store)
                second = run_daily_analysis(config, store=store)

            self.assertTrue(first["ok"])
            self.assertTrue(first["storage"]["written"])
            self.assertTrue(second["ok"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(second["cronRun"]["status"], "duplicate_skipped")
            self.assertFalse(second["storage"]["written"])
            self.assertEqual(first["idempotencyKey"], second["idempotencyKey"])

    def test_no_live_trading_safety_gate_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"POLYMARKET_ENABLE_LIVE_TRADING": "true"}, clear=True):
            with self.assertRaises(SafetyGateError):
                assert_paper_trading_only()
        with mock.patch.dict(os.environ, {"WALLET_PRIVATE_KEY": "masked-test-value"}, clear=True):
            with self.assertRaises(SafetyGateError):
                assert_paper_trading_only()
        with mock.patch.dict(os.environ, {"POLYMARKET_ENABLE_LIVE_TRADING": "false"}, clear=True):
            self.assertTrue(assert_paper_trading_only()["ok"])

    def test_milestone_one_postgres_migration_defines_required_tables(self) -> None:
        self.assertEqual(MILESTONE1_MIGRATION_ID, "20260610_milestone1_research_contracts")
        for table in [
            "cron_runs",
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
        ]:
            self.assertIn(f"create table if not exists {table}", MILESTONE1_POSTGRES_SQL)

    def test_cli_daily_dry_run_outputs_contract_json(self) -> None:
        env = dict(os.environ)
        for key in ["POLYMARKET_ENABLE_LIVE_TRADING", "ENABLE_LIVE_TRADING", "LIVE_TRADING_ENABLED", "WALLET_PRIVATE_KEY"]:
            env.pop(key, None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sports_edge.cli",
                "run-daily",
                "--source",
                "fixture",
                "--as-of",
                "2026-06-10",
                "--dry-run",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["idempotencyKey"], "daily:2026-06-10")

    def test_cli_managed_cycle_dry_run_does_not_write_state(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sports_edge.cli",
                "run-managed-cycle",
                "--source",
                "fixture",
                "--cycle-type",
                "manual",
                "--target-count",
                "6",
                "--dry-run",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertFalse(payload["storage"]["written"])

    def test_github_workflow_runs_contract_collector_and_sofia_daily(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "polymarket-15m.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "*/15 * * * *"', workflow)
        self.assertIn('cron: "0 6 * * *"', workflow)
        self.assertIn('cron: "0 7 * * *"', workflow)
        self.assertIn("CRON_SECRET", workflow)
        self.assertIn("VERCEL_CRON_URL", workflow)
        self.assertIn("/api/cron-collector?source=live", workflow)
        self.assertIn("/api/cron-daily?source=live", workflow)
        self.assertIn("Check scheduled execution credentials", workflow)
        self.assertIn("run-collector --source live", workflow)
        self.assertIn("run-daily --source live", workflow)
        self.assertIn("run-daily --source fixture --target-count 30 --dry-run", workflow)
        self.assertIn('if [ "${EVENT_NAME}" = "schedule" ]; then', workflow)
        self.assertIn("Missing scheduled cron execution credentials", workflow)
        self.assertIn("non_scheduled_fixture_dry_run", workflow)
        self.assertIn("dailyRunHourEuropeSofia", workflow)

    def test_production_readiness_contract_validates_local_deploy_surface(self) -> None:
        payload = build_production_readiness()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["deployed"])
        statuses = {row["id"]: row["status"] for row in payload["checks"]}
        self.assertEqual(statuses["collector_15m_live"], "pass")
        self.assertEqual(statuses["daily_live_readonly"], "pass")
        self.assertEqual(statuses["durable_storage_gate"], "pass")
        self.assertEqual(statuses["non_scheduled_dry_run_fallback"], "pass")
        self.assertEqual(statuses["vercel_crons"], "pass")
        self.assertEqual(statuses["vercel_hobby_function_budget"], "pass")
        self.assertEqual(statuses["dashboard_contract_routes"], "pass")
        self.assertEqual(statuses["runtime_scope_boundary"], "pass")
        self.assertIn("Vercel deployment URL smoke check", payload["externalProofRequired"])

    def test_vercel_crons_call_collector_and_sofia_daily_routes(self) -> None:
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        schedules = {(row["path"], row["schedule"]) for row in vercel["crons"]}
        self.assertIn(("/api/cron-daily", "0 6 * * *"), schedules)
        self.assertIn(("/api/cron-daily", "0 7 * * *"), schedules)
        self.assertNotIn(("/api/cron-collector", "*/15 * * * *"), schedules)
        self.assertTrue((ROOT / "api" / "cron-collector.py").exists())
        self.assertTrue((ROOT / "api" / "cron-daily.py").exists())

    def test_cli_migration_dry_run_reports_required_tables_without_database(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "sports_edge.cli", "migrate", "--dry-run"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertIn("cron_runs", payload["tables"])
        self.assertIn("external_observations", payload["tables"])
        self.assertIn("knowledge_lessons", payload["tables"])

    def test_cli_migration_apply_uses_postgres_store_without_printing_database_url(self) -> None:
        database_url = "postgresql://user:secret-password@localhost:5432/polymarket"
        with mock.patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=False):
            with mock.patch("sports_edge.cli.PostgresStateStore") as store_class:
                store_class.return_value.apply_schema_migration.return_value = {
                    "ok": True,
                    "migrationId": MILESTONE1_MIGRATION_ID,
                    "checksum": "test-checksum",
                    "storageMode": "postgres",
                    "durable": True,
                    "applied": True,
                    "verifiedTables": ["cron_runs", "market_snapshots"],
                    "missingTables": [],
                }
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    exit_code = run_migrations(dry_run=False)

        output = buffer.getvalue()
        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["applied"])
        self.assertNotIn(database_url, output)
        self.assertNotIn("secret-password", output)
        kwargs = store_class.return_value.apply_schema_migration.call_args.kwargs
        self.assertIn("cron_runs", kwargs["required_tables"])
        self.assertIn("knowledge_lessons", kwargs["required_tables"])

    def test_cli_migration_apply_can_write_sanitized_postgres_proof(self) -> None:
        database_url = "postgresql://user:secret-password@localhost:5432/polymarket"
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_path = Path(tmpdir) / "postgres-proof.json"
            with mock.patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=False):
                with mock.patch("sports_edge.cli.PostgresStateStore") as store_class:
                    store_class.return_value.apply_schema_migration.return_value = {
                        "ok": True,
                        "migrationId": MILESTONE1_MIGRATION_ID,
                        "checksum": "test-checksum",
                        "storageMode": "postgres",
                        "durable": True,
                        "applied": True,
                        "verifiedTables": list(goal_audit_module.MILESTONE_TABLES),
                        "missingTables": [],
                    }
                    buffer = io.StringIO()
                    with contextlib.redirect_stdout(buffer):
                        exit_code = run_migrations(dry_run=False, proof_out=str(proof_path))

            output = buffer.getvalue()
            payload = json.loads(output)
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof_text = json.dumps(proof, sort_keys=True)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["proof"]["written"])
        self.assertTrue(goal_audit_module._postgres_migration_proof_valid(proof))
        self.assertNotIn(database_url, output)
        self.assertNotIn("secret-password", output)
        self.assertNotIn(database_url, proof_text)
        self.assertNotIn("secret-password", proof_text)

    def test_cli_migration_dry_run_with_proof_out_does_not_write_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_path = Path(tmpdir) / "postgres-proof.json"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_migrations(dry_run=True, proof_out=str(proof_path))
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertFalse(proof_path.exists())
        self.assertEqual(payload["proof"], {"written": False, "reason": "dry_run"})

    def test_production_cron_proof_builder_requires_both_scheduled_jobs(self) -> None:
        proof = build_production_cron_proof(_valid_cron_evidence())
        proof_text = json.dumps(proof, sort_keys=True)

        self.assertEqual(validate_production_cron_proof(proof), [])
        self.assertTrue(goal_audit_module._production_cron_proof_valid(proof))
        self.assertTrue(proof["scheduledJobs"]["collector_15m"]["observed"])
        self.assertTrue(proof["scheduledJobs"]["sofia_daily"]["observed"])
        self.assertNotIn("secret-token", proof_text)
        self.assertNotIn("?token=", proof_text)

    def test_cli_production_cron_proof_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "cron-evidence.json"
            proof_path = Path(tmpdir) / "cron-proof.json"
            evidence_path.write_text(json.dumps(_valid_cron_evidence()), encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_production_cron_proof(str(evidence_path), str(proof_path), dry_run=True)
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertFalse(proof_path.exists())
        self.assertFalse(payload["written"])
        self.assertEqual(payload["reason"], "dry_run")
        self.assertEqual(payload["validationErrors"], [])

    def test_cli_production_cron_proof_rejects_incomplete_evidence(self) -> None:
        evidence = _valid_cron_evidence()
        evidence["scheduledJobs"]["sofia_daily"]["observed"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "cron-evidence.json"
            proof_path = Path(tmpdir) / "cron-proof.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_production_cron_proof(str(evidence_path), str(proof_path), dry_run=False)
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertFalse(proof_path.exists())
        self.assertFalse(payload["ok"])
        self.assertIn("sofia_daily.observed must be true", payload["validationErrors"])

    def test_durable_daily_proof_builder_requires_duplicate_skip(self) -> None:
        proof = build_durable_daily_proof(_valid_durable_daily_evidence())
        proof_text = json.dumps(proof, sort_keys=True)

        self.assertEqual(validate_durable_daily_proof(proof), [])
        self.assertTrue(goal_audit_module._durable_daily_proof_valid(proof))
        self.assertEqual(proof["firstRun"]["idempotencyKey"], proof["duplicateRun"]["idempotencyKey"])
        self.assertNotIn("DATABASE_URL", proof_text)
        self.assertNotIn("secret", proof_text.lower())

    def test_cli_durable_daily_proof_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "daily-evidence.json"
            proof_path = Path(tmpdir) / "daily-proof.json"
            evidence_path.write_text(json.dumps(_valid_durable_daily_evidence()), encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_durable_daily_proof(str(evidence_path), str(proof_path), dry_run=True)
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertFalse(proof_path.exists())
        self.assertFalse(payload["written"])
        self.assertEqual(payload["reason"], "dry_run")
        self.assertEqual(payload["validationErrors"], [])

    def test_cli_durable_daily_proof_rejects_mismatched_duplicate_key(self) -> None:
        evidence = _valid_durable_daily_evidence()
        evidence["duplicateRun"]["idempotencyKey"] = "daily:2026-06-11"
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "daily-evidence.json"
            proof_path = Path(tmpdir) / "daily-proof.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_durable_daily_proof(str(evidence_path), str(proof_path), dry_run=False)
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertFalse(proof_path.exists())
        self.assertFalse(payload["ok"])
        self.assertIn("duplicateRun.idempotencyKey must match firstRun.idempotencyKey", payload["validationErrors"])

    def test_live_source_proof_builder_requires_all_active_categories(self) -> None:
        proof = build_live_source_proof(_valid_live_source_evidence())
        proof_text = json.dumps(proof, sort_keys=True)

        self.assertEqual(validate_live_source_proof(proof), [])
        self.assertTrue(goal_audit_module._live_source_proof_valid(proof, require_resolution=False))
        self.assertTrue(goal_audit_module._live_source_proof_valid(proof, require_resolution=True))
        self.assertEqual(set(proof["categories"]), {"macroeconomics", "politics", "stocks_trade"})
        self.assertNotIn("DATABASE_URL", proof_text)
        self.assertNotIn("secret", proof_text.lower())

    def test_cli_live_source_proof_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "live-source-evidence.json"
            proof_path = Path(tmpdir) / "live-source-proof.json"
            evidence_path.write_text(json.dumps(_valid_live_source_evidence()), encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_live_source_proof(str(evidence_path), str(proof_path), dry_run=True)
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertFalse(proof_path.exists())
        self.assertFalse(payload["written"])
        self.assertEqual(payload["reason"], "dry_run")
        self.assertEqual(payload["validationErrors"], [])

    def test_cli_live_source_proof_rejects_missing_parser_evidence(self) -> None:
        evidence = _valid_live_source_evidence()
        evidence["categories"]["politics"]["parserVerifiedObservationCount"] = 0
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "live-source-evidence.json"
            proof_path = Path(tmpdir) / "live-source-proof.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = run_live_source_proof(str(evidence_path), str(proof_path), dry_run=False)
            payload = json.loads(buffer.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertFalse(proof_path.exists())
        self.assertFalse(payload["ok"])
        self.assertIn("categories.politics.parserVerifiedObservationCount must be at least 1", payload["validationErrors"])

    def test_external_proof_bundle_is_safe_and_secret_free(self) -> None:
        database_url = "postgresql://user:secret-password@localhost:5432/polymarket"
        with mock.patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=False):
            payload = build_external_proof_bundle(as_of="2026-06-10")
        encoded = json.dumps(payload, sort_keys=True)
        proof_ids = {row["id"] for row in payload["proofItems"]}

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["complete"])
        self.assertTrue(payload["researchOnly"])
        self.assertTrue(payload["paperTradingOnly"])
        self.assertTrue(payload["safeDefaults"]["doesNotDeploy"])
        self.assertTrue(payload["safeDefaults"]["doesNotWriteDatabase"])
        self.assertTrue(payload["configuredEnvironment"]["databaseUrlPresent"])
        self.assertFalse(payload["configuredEnvironment"]["databaseUrlValueExposed"])
        self.assertNotIn(database_url, encoded)
        self.assertNotIn("secret-password", encoded)
        self.assertIn("postgres_apply_proof", proof_ids)
        self.assertIn("approved_live_source_validation", proof_ids)
        self.assertIn("vercel_dashboard_smoke_proof", proof_ids)
        proof_paths = {row["id"]: row.get("proofPath") for row in payload["proofItems"]}
        self.assertEqual(proof_paths["postgres_apply_proof"], goal_audit_module.POSTGRES_PROOF_PATH)
        self.assertEqual(proof_paths["production_cron_run_proof"], goal_audit_module.PRODUCTION_CRON_PROOF_PATH)
        self.assertEqual(proof_paths["approved_live_source_validation"], goal_audit_module.LIVE_SOURCE_PROOF_PATH)
        self.assertEqual(proof_paths["durable_daily_write_proof"], goal_audit_module.DURABLE_DAILY_PROOF_PATH)
        approved_commands = {row["id"]: row.get("approvedCommand", "") for row in payload["proofItems"]}
        self.assertIn("production-cron-proof", approved_commands["production_cron_run_proof"])
        self.assertIn("live-source-proof", approved_commands["approved_live_source_validation"])
        self.assertIn("durable-daily-proof", approved_commands["durable_daily_write_proof"])
        self.assertTrue(all(row["status"] == "approval_required" for row in payload["proofItems"]))

    def test_cli_external_proof_bundle_outputs_no_secret_values(self) -> None:
        database_url = "postgresql://user:secret-password@localhost:5432/polymarket"
        result = subprocess.run(
            [sys.executable, "-m", "sports_edge.cli", "external-proof-bundle", "--as-of", "2026-06-10"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "DATABASE_URL": database_url},
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("postgres_apply_proof", {row["id"] for row in payload["proofItems"]})
        self.assertNotIn(database_url, result.stdout)
        self.assertNotIn("secret-password", result.stdout)

    def test_postgres_store_masks_database_url_in_errors(self) -> None:
        database_url = "postgresql://user:secret-password@localhost:5432/polymarket"
        store = PostgresStateStore(database_url=database_url)
        with mock.patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=False):
            message = store._safe_error(RuntimeError(f"could not connect to {database_url}"))
        self.assertNotIn(database_url, message)
        self.assertNotIn("secret-password", message)
        self.assertIn("<masked database url>", message)


class DataAgentAndDashboardApiTests(unittest.TestCase):
    def test_data_agent_fixture_collects_normalized_snapshots_without_live_calls(self) -> None:
        payload = DataAgent().collect(
            run_id="test-run",
            source_mode="fixture",
            target_count=30,
            observed_at="2026-06-10T06:00:00Z",
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["agent"], "data_agent")
        self.assertEqual(payload["activeSections"], list(ACTIVE_CATEGORIES))
        self.assertEqual(len(payload["marketSnapshots"]), 3)
        self.assertEqual(len(payload["orderBookSnapshots"]), 3)
        self.assertEqual(len(payload["externalObservations"]), 5)
        metric_names = {row["metric_name"] for row in payload["externalObservations"]}
        self.assertIn("consensus_surprise_z", metric_names)
        self.assertIn("deadline_delay_risk_index", metric_names)
        self.assertIn("underlying_return_1d", metric_names)
        self.assertEqual(payload["freshness"]["marketSnapshotCount"], 3)
        self.assertTrue(all(row["category"] in ACTIVE_CATEGORIES for row in payload["marketSnapshots"]))
        self.assertTrue(all(row["spread"] >= 0 for row in payload["orderBookSnapshots"]))

    def test_live_external_adapter_probe_is_read_only_and_mockable(self) -> None:
        calls = []

        def fake_fetcher(url: str) -> dict[str, object]:
            calls.append(url)
            return {"ok": True, "status": 200, "content_type": "text/html"}

        bundle = collect_external_adapter_bundle(
            run_id="test-run",
            observed_at="2026-06-10T06:00:00Z",
            source_mode="live",
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(bundle.observations), 3)
        self.assertTrue(all(row.metric_name == "official_source_http_ok" for row in bundle.observations))
        self.assertTrue(all(row.payload["relevance"] == "source_health_not_decision_evidence" for row in bundle.observations))

    def test_live_external_adapter_parses_mocked_structured_official_payloads(self) -> None:
        def fake_fetcher(url: str) -> dict[str, object]:
            if "bls.gov" in url:
                return {
                    "ok": True,
                    "status": 200,
                    "content_type": "application/json",
                    "json": {"releases": [{"name": "CPI release", "date": "2026-06-14"}]},
                }
            if "usa.gov" in url:
                return {
                    "ok": True,
                    "status": 200,
                    "content_type": "application/json",
                    "json": {
                        "events": [
                            {
                                "name": "Election certification deadline",
                                "date": "2026-06-20",
                                "delay_risk_index": 0.27,
                            }
                        ]
                    },
                }
            return {
                "ok": True,
                "status": 200,
                "content_type": "application/json",
                "json": {
                    "events": [{"event": "NVDA earnings", "date": "2026-06-12"}],
                    "market_data": [{"symbol": "NVDA", "return_1d": 0.018}],
                },
            }

        bundle = collect_external_adapter_bundle(
            run_id="test-run",
            observed_at="2026-06-10T06:00:00Z",
            source_mode="live",
            fetcher=fake_fetcher,
        )
        metrics = {row.metric_name: row.metric_value for row in bundle.observations}
        self.assertEqual(metrics["days_until_next_release"], 4.0)
        self.assertEqual(metrics["days_until_political_deadline"], 10.0)
        self.assertEqual(metrics["deadline_delay_risk_index"], 0.27)
        self.assertEqual(metrics["event_window_days"], 2.0)
        self.assertEqual(metrics["underlying_return_1d"], 0.018)
        self.assertFalse(any(row.metric_name == "official_source_http_ok" for row in bundle.observations))
        self.assertTrue(all(row.validate() == [] for row in bundle.observations))

    def test_model_scoring_does_not_treat_health_only_live_rows_as_decision_evidence(self) -> None:
        data = DataAgent().collect(run_id="test-run", source_mode="fixture", target_count=30, observed_at="2026-06-10T06:00:00Z")

        def fake_fetcher(url: str) -> dict[str, object]:
            return {"ok": True, "status": 200, "content_type": "text/html"}

        bundle = collect_external_adapter_bundle(
            run_id="test-run",
            observed_at="2026-06-10T06:00:00Z",
            source_mode="live",
            fetcher=fake_fetcher,
        )
        data = {**data, "externalObservations": [row.to_dict() for row in bundle.observations]}
        outputs = score_market_candidates(run_id="test-run", data_payload=data, created_at="2026-06-10T06:00:00Z")
        bayesian_rows = [row.to_dict() for row in outputs if row.model_family == "bayesian_consensus"]
        self.assertTrue(bayesian_rows)
        self.assertTrue(all(row["confidence"] == 0.42 for row in bayesian_rows))
        self.assertTrue(all(row["features"]["consensusStatus"] == "source_health_only" for row in bayesian_rows))

    def test_data_agent_normalizers_filter_scope_and_parse_order_book(self) -> None:
        self.assertEqual(infer_market_category({"question": "Will CPI be above consensus?"}), "macroeconomics")
        self.assertEqual(infer_market_category({"question": "Will the Senate pass the bill?"}), "politics")
        self.assertEqual(infer_market_category({"question": "Will NVDA close above $150?"}), "stocks_trade")
        self.assertIsNone(infer_market_category({"question": "Will Arsenal win the match?"}))
        self.assertIsNone(infer_market_category({"question": "Spread: Golden State Valkyries (-7.5)"}))
        self.assertIsNone(infer_market_category({"question": "Moneyline: Lakers vs Warriors"}))
        self.assertIsNone(
            normalize_gamma_market(
                {"id": "sports-1", "question": "Will Arsenal win the match?", "category": "sports"},
                run_id="test-run",
                observed_at="2026-06-10T06:00:00Z",
            )
        )
        book = normalize_order_book(
            {"bids": [{"price": "0.40", "size": "10"}], "asks": [{"price": "0.45", "size": "12"}]},
            run_id="test-run",
            market_id="market-1",
            token_id="token-1",
            observed_at="2026-06-10T06:00:00Z",
        )
        self.assertEqual(book.best_bid, 0.40)
        self.assertEqual(book.best_ask, 0.45)
        self.assertAlmostEqual(book.spread or 0.0, 0.05)
        self.assertEqual(book.validate(), [])

    def test_dashboard_contract_exposes_required_api_sections(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            daily = run_daily_analysis(
                DailyRunConfig(source_mode="fixture", target_count=30, dry_run=True, as_of="2026-06-10")
            )
        contract = dashboard_contract_from_daily(daily)
        for section in [
            "status",
            "freshness",
            "context",
            "candidates",
            "decisions",
            "models",
            "sources",
            "portfolio",
            "performance",
            "warnings",
            "errors",
        ]:
            self.assertIn(section, contract)
        self.assertTrue(contract["ok"])
        self.assertEqual(contract["status"]["idempotencyKey"], "daily:2026-06-10")
        self.assertEqual(len(contract["candidates"]), 3)
        self.assertEqual(len(contract["context"]["broadReports"]), 3)
        self.assertGreaterEqual(len(contract["context"]["betSpecificReports"]), 1)
        self.assertIn("paperBets", contract["decisions"])
        self.assertIn("disagreement", contract["models"])
        self.assertEqual(contract["portfolio"]["bankroll_units"], 100.0)
        self.assertIn("paperTradingHistory", contract["performance"])
        self.assertIn("knowledgeLessons", contract["performance"])

    def test_dashboard_contract_filters_stale_out_of_scope_live_markets(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            daily = run_daily_analysis(
                DailyRunConfig(source_mode="fixture", target_count=30, dry_run=True, as_of="2026-06-10")
            )
        stale_market = {
            **daily["dataAgent"]["marketSnapshots"][0],
            "market_id": "stale-sports-spread",
            "question": "Spread: Golden State Valkyries (-7.5)",
            "category": "politics",
        }
        stale_decision = {
            **daily["decisionSignals"][0],
            "decision_id": "stale-sports-decision",
            "candidate_id": "stale-sports-spread",
            "market_id": "stale-sports-spread",
            "category": "politics",
        }
        stale_model = {
            **daily["modelOutputs"][0],
            "candidate_id": "stale-sports-spread",
            "market_id": "stale-sports-spread",
            "category": "politics",
        }
        daily["dataAgent"]["marketSnapshots"].append(stale_market)
        daily["decisionSignals"].append(stale_decision)
        daily["modelOutputs"].append(stale_model)
        contract = dashboard_contract_from_daily(daily)
        candidate_ids = {row["candidateId"] for row in contract["candidates"]}
        model_ids = {row["candidate_id"] for row in contract["models"]["outputs"]}
        decision_ids = {row["candidate_id"] for row in contract["decisions"]["all"]}
        self.assertNotIn("stale-sports-spread", candidate_ids)
        self.assertNotIn("stale-sports-spread", model_ids)
        self.assertNotIn("stale-sports-spread", decision_ids)
        self.assertTrue(any("out-of-scope" in warning for warning in contract["warnings"]))

    def test_run_and_performance_api_alias_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir))
            daily = run_daily_analysis(
                DailyRunConfig(source_mode="fixture", target_count=30, dry_run=True, as_of="2026-06-10"),
                store=store,
            )
            store.write_json("daily_runs/latest.json", daily)
            store.write_json(
                "run_history.json",
                {
                    "schema_version": 1,
                    "runs": [
                        {
                            "runId": "run-1",
                            "createdAt": "2026-06-10T06:00:00Z",
                            "cycleType": "scheduled_daily",
                            "status": "success",
                        }
                    ],
                },
            )

            latest = runs_latest_payload(store=store)
            history = runs_history_payload(store=store)
            performance = section_payload("performance", store=store)

        self.assertTrue(latest["ok"])
        self.assertEqual(latest["run"]["idempotencyKey"], "daily:2026-06-10")
        self.assertTrue(history["ok"])
        self.assertEqual(history["runs"][0]["runId"], "run-1")
        self.assertIn("performance", performance)
        self.assertIn("paperTradingHistory", performance["performance"])

    def test_context_agent_separates_broad_and_gated_bet_specific_reports(self) -> None:
        data = DataAgent().collect(run_id="test-run", source_mode="fixture", target_count=30, observed_at="2026-06-10T06:00:00Z")
        outputs = score_market_candidates(run_id="test-run", data_payload=data, created_at="2026-06-10T06:00:00Z")
        agent = ContextAgent()
        broad = agent.broad_context_reports(
            run_id="test-run",
            created_at="2026-06-10T06:00:00Z",
            source_mode="fixture",
            data_payload=data,
        )
        specific = agent.bet_specific_reports(
            run_id="test-run",
            created_at="2026-06-10T06:00:00Z",
            data_payload=data,
            model_outputs=outputs,
            source_mode="fixture",
        )
        self.assertEqual(len(broad), len(ACTIVE_CATEGORIES))
        self.assertEqual({row.scope for row in broad}, {"broad_category"})
        self.assertTrue(all(row.sources for row in broad))
        self.assertEqual({row.candidate_id for row in specific}, {"macro-cpi-june", "stocks-nvda-close"})
        self.assertTrue(all(row.scope == "bet_specific" for row in specific))
        self.assertTrue(all(row.sources[0]["source_reliability"] for row in specific))
        self.assertTrue(all(row.validate() == [] for row in [*broad, *specific]))

    def test_model_scoring_outputs_disagreement_and_all_families_for_each_market(self) -> None:
        data = DataAgent().collect(run_id="test-run", source_mode="fixture", target_count=30, observed_at="2026-06-10T06:00:00Z")
        outputs = score_market_candidates(run_id="test-run", data_payload=data, created_at="2026-06-10T06:00:00Z")
        self.assertEqual(len(outputs), len(data["marketSnapshots"]) * len(MODEL_FAMILIES))
        families_by_candidate = {}
        for output in outputs:
            payload = output.to_dict()
            families_by_candidate.setdefault(payload["candidate_id"], set()).add(payload["model_family"])
            self.assertIn("range", payload["disagreement"])
            self.assertEqual(output.validate(), [])
        self.assertTrue(all(families == MODEL_FAMILIES for families in families_by_candidate.values()))
        bayesian_rows = [row.to_dict() for row in outputs if row.model_family == "bayesian_consensus"]
        self.assertTrue(any(row["features"].get("externalObservationCount", 0) > 0 for row in bayesian_rows))
        self.assertTrue(any("underlying_return_1d" in row["features"].get("externalMetrics", {}) for row in bayesian_rows))

    def test_decision_agent_rejects_or_watchlists_fixture_markets_without_forcing_bets(self) -> None:
        data = DataAgent().collect(run_id="test-run", source_mode="fixture", target_count=30, observed_at="2026-06-10T06:00:00Z")
        outputs = score_market_candidates(run_id="test-run", data_payload=data, created_at="2026-06-10T06:00:00Z")
        decisions, portfolio = DecisionAgent().decide(
            run_id="test-run",
            data_payload=data,
            model_outputs=outputs,
            context_reports=[],
            created_at="2026-06-10T06:00:00Z",
        )
        self.assertEqual(len(decisions), 3)
        self.assertFalse(any(decision.decision == "paper_bet" for decision in decisions))
        self.assertTrue(all(decision.stake_units == 0.0 for decision in decisions))
        self.assertGreater(len(portfolio.warnings), 0)

    def test_decision_agent_sizes_paper_bet_only_when_all_gates_clear(self) -> None:
        data = DataAgent().collect(run_id="test-run", source_mode="fixture", target_count=1, observed_at="2026-06-10T06:00:00Z")
        market = {**data["marketSnapshots"][0], "spread": 0.03, "liquidity": 5000.0}
        data = {**data, "marketSnapshots": [market]}
        model_outputs = [
            {
                "candidate_id": market["market_id"],
                "market_id": market["market_id"],
                "model_family": "market_implied_probability",
                "probability": 0.50,
                "confidence": 0.75,
                "reject_flags": [],
                "disagreement": {"range": 0.04, "status": "low", "modelCount": 5},
            },
            {
                "candidate_id": market["market_id"],
                "market_id": market["market_id"],
                "model_family": "portfolio_ev_risk",
                "probability": 0.60,
                "confidence": 0.78,
                "reject_flags": [],
                "disagreement": {"range": 0.04, "status": "low", "modelCount": 5},
            },
            {
                "candidate_id": market["market_id"],
                "market_id": market["market_id"],
                "model_family": "base_rate_event_history",
                "probability": 0.57,
                "confidence": 0.72,
                "reject_flags": [],
                "disagreement": {"range": 0.04, "status": "low", "modelCount": 5},
            },
        ]
        decisions, portfolio = DecisionAgent(PortfolioRules(min_edge=0.04, min_confidence=0.55)).decide(
            run_id="test-run",
            data_payload=data,
            model_outputs=model_outputs,
            context_reports=[
                {
                    "scope": "bet_specific",
                    "candidate_id": market["market_id"],
                    "confidence": 0.62,
                    "reliability": "possible/probable",
                    "invalidation_triggers": ["new official evidence invalidates the thesis"],
                }
            ],
            created_at="2026-06-10T06:00:00Z",
        )
        self.assertEqual(decisions[0].decision, "paper_bet")
        self.assertGreater(decisions[0].stake_units, 0.0)
        self.assertTrue(any("Bet-specific context available" in reason for reason in decisions[0].reasons))
        self.assertGreater(portfolio.total_exposure_units, 0.0)

    def test_collector_dry_run_does_not_write_and_uses_15_minute_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            with mock.patch.dict(os.environ, {}, clear=True):
                payload = run_collector(
                    CollectorRunConfig(
                        source_mode="fixture",
                        target_count=30,
                        dry_run=True,
                        as_of="2026-06-10T06:07:30Z",
                    ),
                    store=store,
                )
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertFalse(payload["storage"]["written"])
        self.assertEqual(payload["idempotencyKey"], "collector:2026-06-10T06:00Z")
        self.assertEqual(payload["cronRun"]["scheduled_for"], "2026-06-10T06:00:00Z")
        self.assertEqual(payload["cronRun"]["counts"]["marketSnapshots"], 3)
        self.assertEqual(payload["cronRun"]["counts"]["orderBookSnapshots"], 3)

    def test_collector_persists_latest_and_skips_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            config = CollectorRunConfig(
                source_mode="fixture",
                target_count=30,
                dry_run=False,
                as_of="2026-06-10T06:07:30Z",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                first = run_collector(config, store=store)
                second = run_collector(config, store=store)
            latest = store.read_json("collector_latest.json")
        self.assertTrue(first["ok"])
        self.assertTrue(first["storage"]["written"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["cronRun"]["status"], "duplicate_skipped")
        self.assertFalse(second["storage"]["written"])
        self.assertEqual(latest["idempotencyKey"], "collector:2026-06-10T06:00Z")

    def test_live_daily_persisted_run_is_allowed_with_mocked_read_only_data_agent(self) -> None:
        fixture_data = DataAgent().collect(
            run_id="placeholder",
            source_mode="fixture",
            target_count=30,
            observed_at="2026-06-10T06:00:00Z",
        )

        class FakeDataAgent:
            def collect(self, *, run_id: str, source_mode: str, target_count: int, observed_at: str):
                payload = {
                    **fixture_data,
                    "runId": run_id,
                    "sourceMode": source_mode,
                    "observedAt": observed_at,
                    "marketSnapshots": [
                        {**row, "run_id": run_id, "observed_at": observed_at, "fetched_at": observed_at}
                        for row in fixture_data["marketSnapshots"]
                    ],
                    "orderBookSnapshots": [
                        {**row, "run_id": run_id, "observed_at": observed_at}
                        for row in fixture_data["orderBookSnapshots"]
                    ],
                    "warnings": ["mocked live read-only data agent"],
                }
                return payload

        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            config = DailyRunConfig(source_mode="live", target_count=30, dry_run=False, as_of="2026-06-10")
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("sports_edge.orchestrator.DataAgent", return_value=FakeDataAgent()):
                    payload = run_daily_analysis(config, store=store)
            stored = store.read_json("daily_runs/latest.json")

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["dryRun"])
        self.assertEqual(payload["sourceMode"], "live")
        self.assertTrue(payload["storage"]["written"])
        self.assertEqual(stored["sourceMode"], "live")

    def test_dashboard_contract_merges_latest_collector_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            with mock.patch.dict(os.environ, {}, clear=True):
                collector = run_collector(
                    CollectorRunConfig(
                        source_mode="fixture",
                        target_count=30,
                        dry_run=False,
                        as_of="2026-06-10T06:07:30Z",
                    ),
                    store=store,
                )
                daily = run_daily_analysis(
                    DailyRunConfig(source_mode="fixture", target_count=30, dry_run=False, as_of="2026-06-10"),
                    store=store,
                )
            contract = load_dashboard_contract(store=store)
        self.assertTrue(collector["storage"]["written"])
        self.assertTrue(daily["storage"]["written"])
        self.assertEqual(contract["status"]["latestCollector"]["idempotency_key"], "collector:2026-06-10T06:00Z")
        self.assertEqual(contract["freshness"]["marketSnapshotCount"], 3)

    def test_cli_collector_dry_run_outputs_contract_json(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sports_edge.cli",
                "run-collector",
                "--source",
                "fixture",
                "--as-of",
                "2026-06-10T06:07:30Z",
                "--dry-run",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["idempotencyKey"], "collector:2026-06-10T06:00Z")

    def test_local_dashboard_health_payload_is_paper_only(self) -> None:
        payload = health_payload()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["research_only"])
        self.assertFalse(payload["safety"]["orderExecution"])


class OutcomeEvaluationTests(unittest.TestCase):
    def test_outcome_contracts_validate(self) -> None:
        paper_bet = PaperBet(
            paper_bet_id="paper-1",
            decision_id="decision-1",
            run_id="run-1",
            candidate_id="stocks-nvda-close",
            market_id="stocks-nvda-close",
            category="stocks_trade",
            side="Yes",
            entry_price=0.5,
            fair_probability=0.6,
            confidence=0.7,
            stake_units=3.0,
            opened_at="2026-06-09T06:00:00Z",
        )
        outcome = ResolvedOutcome(
            outcome_id="outcome-1",
            paper_bet_id="paper-1",
            decision_id="decision-1",
            run_id="run-1",
            candidate_id="stocks-nvda-close",
            market_id="stocks-nvda-close",
            category="stocks_trade",
            resolved_at="2026-06-10T00:00:00Z",
            result="loss",
            pnl_units=-3.0,
            calibration_bucket="0.60-0.70",
            fair_probability=0.6,
            entry_price=0.5,
            stake_units=3.0,
        )
        note = DecisionNote(
            note_id="note-1",
            decision_id="decision-1",
            run_id="run-1",
            candidate_id="stocks-nvda-close",
            market_id="stocks-nvda-close",
            category="stocks_trade",
            created_at="2026-06-09T06:00:00Z",
            summary="paper bet note",
            evidence=["edge passed"],
            risks=["model disagreement"],
            evaluation_plan="Evaluate after resolution.",
        )
        lesson = KnowledgeLesson(
            lesson_id="lesson-1",
            category="stocks_trade",
            lesson_type="loss_review",
            created_at="2026-06-10T06:00:00Z",
            summary="loss review",
            severity="medium",
        )
        self.assertEqual(paper_bet.validate(), [])
        self.assertEqual(outcome.validate(), [])
        self.assertEqual(note.validate(), [])
        self.assertEqual(lesson.validate(), [])

    def test_evaluator_resolves_due_prior_fixture_paper_bet_and_creates_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            previous = _previous_daily_paper_bet_payload()
            store.write_json("cron_runs/previous.json", previous)
            evaluation = evaluate_previous_paper_bets(
                store=store,
                current_run_id="daily-2026-06-10-current",
                as_of="2026-06-10T06:00:00Z",
                source_mode="fixture",
            )
        self.assertTrue(evaluation["ok"])
        self.assertEqual(evaluation["status"], "resolved_outcomes_available")
        self.assertEqual(evaluation["evaluatedPaperBetCount"], 1)
        self.assertEqual(evaluation["resolvedOutcomeCount"], 1)
        self.assertEqual(evaluation["resolvedOutcomes"][0]["result"], "loss")
        self.assertEqual(evaluation["resolvedOutcomes"][0]["pnl_units"], -3.0)
        self.assertEqual(evaluation["knowledgeLessons"][0]["lesson_type"], "loss_review")
        self.assertEqual(evaluation["calibration"]["status"], "available")
        self.assertGreaterEqual(evaluation["drawdown"]["currentDrawdownPct"], 0.03)

    def test_daily_run_evaluates_previous_paper_bets_before_new_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            store.write_json("cron_runs/previous.json", _previous_daily_paper_bet_payload())
            with mock.patch.dict(os.environ, {}, clear=True):
                payload = run_daily_analysis(
                    DailyRunConfig(source_mode="fixture", target_count=30, dry_run=True, as_of="2026-06-10"),
                    store=store,
                )
            contract = dashboard_contract_from_daily(payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["previousEvaluation"]["resolvedOutcomeCount"], 1)
        self.assertEqual(len(payload["resolvedOutcomes"]), 1)
        self.assertEqual(len(payload["knowledgeLessons"]), 1)
        self.assertEqual(payload["portfolioState"]["current_drawdown_pct"], 0.03)
        self.assertEqual(contract["performance"]["status"], "resolved_outcomes_available")
        self.assertEqual(contract["performance"]["summary"]["losses"], 1)
        self.assertEqual(len(contract["decisions"]["decisionNotes"]), 3)

    def test_evaluator_resolves_stored_closed_market_snapshot_without_fixture_mode(self) -> None:
        payload = _previous_daily_paper_bet_payload()
        market = payload["dataAgent"]["marketSnapshots"][0]
        market["outcomes"] = ["Yes", "No"]
        market["outcome_prices"] = [1.0, 0.0]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(local_root=Path(temp_dir), prefix="test/polymarket")
            store.write_json("cron_runs/previous.json", payload)
            evaluation = evaluate_previous_paper_bets(
                store=store,
                current_run_id="daily-2026-06-10-current",
                as_of="2026-06-10T06:00:00Z",
                source_mode="live",
            )
        self.assertEqual(evaluation["resolvedOutcomeCount"], 1)
        self.assertEqual(evaluation["resolvedOutcomes"][0]["result"], "win")
        self.assertEqual(evaluation["resolvedOutcomes"][0]["payload"]["resolutionMode"], "stored_market_snapshot")

    def test_goal_audit_reports_unproven_external_requirements(self) -> None:
        payload = build_goal_audit()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["complete"])
        self.assertIn("external-proof-bundle", payload["externalProofCommand"])
        statuses = {row["id"]: row["status"] for row in payload["requirements"]}
        self.assertEqual(payload["summary"]["proven"], 11)
        self.assertEqual(payload["summary"]["partial"], 2)
        self.assertEqual(payload["summary"]["missing"], 3)
        self.assertEqual(statuses["paper_only_safety"], "proven")
        self.assertEqual(statuses["daily_run_order"], "proven")
        self.assertEqual(statuses["dashboard_api"], "proven")
        self.assertEqual(statuses["live_official_adapters"], "partial")
        self.assertEqual(statuses["live_resolution_proof"], "partial")
        self.assertEqual(statuses["postgres_apply_proof"], "missing")
        self.assertEqual(statuses["durable_daily_write_proof"], "missing")
        self.assertEqual(statuses["deployed_cron_proof"], "missing")
        self.assertEqual(statuses["deployed_dashboard_proof"], "proven")
        for row in payload["requirements"]:
            self.assertIn("checks", row)
            self.assertTrue(row["checks"])
            if row["status"] == "proven":
                self.assertTrue(all(check["passed"] for check in row["checks"]))

    def test_goal_audit_accepts_valid_production_cron_proof_file(self) -> None:
        valid_cron_proof = build_production_cron_proof(_valid_cron_evidence())
        original_read_json = goal_audit_module._read_json

        def fake_read_json(path: str) -> dict[str, object]:
            if path == "docs/ai/proofs/20260611_production_cron_run.json":
                return valid_cron_proof
            return original_read_json(path)

        with mock.patch("sports_edge.goal_audit._read_json", side_effect=fake_read_json):
            payload = build_goal_audit()

        statuses = {row["id"]: row["status"] for row in payload["requirements"]}
        self.assertEqual(statuses["deployed_cron_proof"], "proven")
        self.assertEqual(statuses["postgres_apply_proof"], "missing")
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["summary"]["proven"], 12)
        self.assertEqual(payload["summary"]["missing"], 2)

    def test_goal_audit_accepts_valid_durable_daily_proof_file(self) -> None:
        valid_daily_proof = build_durable_daily_proof(_valid_durable_daily_evidence())
        original_read_json = goal_audit_module._read_json

        def fake_read_json(path: str) -> dict[str, object]:
            if path == "docs/ai/proofs/20260611_durable_daily_write.json":
                return valid_daily_proof
            return original_read_json(path)

        with mock.patch("sports_edge.goal_audit._read_json", side_effect=fake_read_json):
            payload = build_goal_audit()

        statuses = {row["id"]: row["status"] for row in payload["requirements"]}
        self.assertEqual(statuses["durable_daily_write_proof"], "proven")
        self.assertEqual(statuses["postgres_apply_proof"], "missing")
        self.assertEqual(statuses["deployed_cron_proof"], "missing")
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["summary"]["proven"], 12)
        self.assertEqual(payload["summary"]["missing"], 2)

    def test_goal_audit_accepts_valid_live_source_proof_file(self) -> None:
        valid_live_source_proof = build_live_source_proof(_valid_live_source_evidence())
        original_read_json = goal_audit_module._read_json

        def fake_read_json(path: str) -> dict[str, object]:
            if path == "docs/ai/proofs/20260611_live_source_validation.json":
                return valid_live_source_proof
            return original_read_json(path)

        with mock.patch("sports_edge.goal_audit._read_json", side_effect=fake_read_json):
            payload = build_goal_audit()

        statuses = {row["id"]: row["status"] for row in payload["requirements"]}
        self.assertEqual(statuses["live_official_adapters"], "proven")
        self.assertEqual(statuses["live_resolution_proof"], "proven")
        self.assertEqual(statuses["postgres_apply_proof"], "missing")
        self.assertEqual(statuses["deployed_cron_proof"], "missing")
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["summary"]["proven"], 13)
        self.assertEqual(payload["summary"]["partial"], 0)
        self.assertEqual(payload["summary"]["missing"], 3)

    def test_goal_audit_accepts_valid_postgres_migration_proof_file(self) -> None:
        valid_postgres_proof = {
            "proof_id": "postgres_migration_20260611",
            "researchOnly": True,
            "paperTradingOnly": True,
            "migration": {
                "ok": True,
                "applied": True,
                "verifiedTables": list(goal_audit_module.MILESTONE_TABLES),
                "missingTables": [],
            },
            "storage": {
                "durable": True,
            },
            "checks": {
                "database_url_value_exposed": False,
                "logs_contain_credentials": False,
                "wallet_or_order_execution_enabled": False,
            },
        }
        original_read_json = goal_audit_module._read_json

        def fake_read_json(path: str) -> dict[str, object]:
            if path == goal_audit_module.POSTGRES_PROOF_PATH:
                return valid_postgres_proof
            return original_read_json(path)

        with mock.patch("sports_edge.goal_audit._read_json", side_effect=fake_read_json):
            payload = build_goal_audit()

        statuses = {row["id"]: row["status"] for row in payload["requirements"]}
        self.assertEqual(statuses["postgres_apply_proof"], "proven")
        self.assertEqual(statuses["deployed_cron_proof"], "missing")
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["summary"]["proven"], 12)
        self.assertEqual(payload["summary"]["missing"], 2)


def _previous_daily_paper_bet_payload() -> dict[str, object]:
    run_id = "daily-2026-06-09-previous"
    decision_id = stable_id(run_id, "stocks-nvda-close", "decision")
    return {
        "ok": True,
        "cronRun": {
            "run_id": run_id,
            "cycle_type": "daily_analytics",
            "scheduled_for": "2026-06-09T06:00:00Z",
            "idempotency_key": "daily:2026-06-09",
            "status": "success",
            "dry_run": False,
            "started_at": "2026-06-09T06:00:00Z",
        },
        "dataAgent": {
            "marketSnapshots": [
                {
                    "market_id": "stocks-nvda-close",
                    "question": "Will NVDA close above the weekly threshold?",
                    "category": "stocks_trade",
                    "end_time": "2026-06-09T23:59:59Z",
                    "closed": True,
                    "source_url": "fixture://resolution/stocks-nvda-close",
                    "outcome_prices": [0.5, 0.5],
                    "resolution_criteria": "Fixture prior market resolved by deterministic fixture result.",
                }
            ]
        },
        "modelOutputs": [
            {
                "candidate_id": "stocks-nvda-close",
                "market_id": "stocks-nvda-close",
                "model_family": "market_implied_probability",
                "probability": 0.50,
                "confidence": 0.75,
            },
            {
                "candidate_id": "stocks-nvda-close",
                "market_id": "stocks-nvda-close",
                "model_family": "portfolio_ev_risk",
                "probability": 0.60,
                "confidence": 0.78,
            },
        ],
        "decisionSignals": [
            {
                "decision_id": decision_id,
                "run_id": run_id,
                "candidate_id": "stocks-nvda-close",
                "market_id": "stocks-nvda-close",
                "category": "stocks_trade",
                "decision": "paper_bet",
                "confidence": 0.72,
                "reliability": "possible/probable",
                "edge": 0.10,
                "stake_units": 3.0,
                "reasons": ["Synthetic prior paper bet for outcome evaluation test."],
                "model_disagreement": {"range": 0.04, "status": "low"},
                "invalidation_triggers": ["fixture resolution changes"],
                "evaluation_plan": "Resolve against fixture result.",
                "created_at": "2026-06-09T06:00:00Z",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
