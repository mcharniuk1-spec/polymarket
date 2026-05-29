from __future__ import annotations

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
from sports_edge.bet_research import BetResearchPlanner
from sports_edge.codex_queue import drain_codex_queue, enqueue_codex_review, queue_summary
from sports_edge.dashboard_data import build_dashboard_payload
from sports_edge.full_scan import run_full_scan
from sports_edge.intelligence import run_intelligence_cycle, validate_news_sources
from sports_edge.managed_pipeline import run_agent_replay, run_managed_cycle, run_ml_update
from sports_edge.odds_math import american_to_decimal, american_to_implied_probability
from sports_edge.reporting import PerformanceReporter
from sports_edge.risk_control import RESEARCH_ONLY_MODE, RiskControl
from sports_edge.source_registry import SourceRegistry
from sports_edge.state_store import JsonStateStore
from sports_edge.vercel_api import cron_authorized


ROOT = Path(__file__).resolve().parents[1]


def _fake_gamma_market(index: int) -> dict[str, object]:
    price = 0.42 + ((index % 10) / 100.0)
    return {
        "id": str(1000 + index),
        "question": f"Will Bitcoin close above test threshold #{index}?",
        "conditionId": f"condition-{index}",
        "slug": f"fake-market-{index}",
        "resolutionSource": "https://example.com/resolution",
        "endDate": "2026-05-30T00:00:00Z",
        "liquidity": "1000",
        "liquidityNum": 1000 + index,
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
        "description": "Fixture public market metadata for full-scan pagination test.",
        "events": [
            {
                "id": f"event-{index // 2}",
                "slug": f"event-{index // 2}",
                "title": f"Bitcoin threshold event {index // 2}",
                "description": "Event metadata",
                "resolutionSource": "https://example.com/resolution",
                "createdAt": "2026-05-29T08:00:00Z",
                "updatedAt": "2026-05-29T08:05:00Z",
                "series": [{"title": "BTC thresholds", "slug": "btc-thresholds"}],
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
        result = MultiAgentPipeline().run(source_mode="fixture", target_count=600)
        self.assertTrue(result.metrics["research_only"])
        self.assertEqual(result.metrics["candidate_count"], 600)
        self.assertEqual(len(result.category_stats), 6)
        self.assertTrue(all(row["candidate_count"] == 100 for row in result.category_stats))
        self.assertEqual(len(result.top_bets), 10)
        self.assertAlmostEqual(result.metrics["total_staked_units"], 100.0)
        self.assertAlmostEqual(result.metrics["deployment_budget_units"], 100.0)
        self.assertAlmostEqual(result.metrics["unallocated_budget_units"], 0.0)
        self.assertTrue(all(item["mode"] == "paper" if "mode" in item else True for item in result.top_bets))
        self.assertTrue(all("assessments" in item for item in result.recommendations))

    def test_dashboard_payload_has_explicit_bet_records_and_news_graph(self) -> None:
        payload = build_dashboard_payload(source_mode="fixture", target_count=300, use_cache=False)
        multi_agent = payload["multi_agent"]
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
        candidates = MarketDataAgent().load_candidates(source_mode="fixture", target_count=600)
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
        self.assertIn(first["reliability"]["label"], {"reliable", "probable/usable with caution", "unreliable/weak"})
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
        self.assertGreater(payload["summary"]["eventGroupCount"], 0)
        self.assertEqual(payload["summary"]["timeSeries"]["observedHistoryCount"], 200)
        self.assertTrue(payload["agentSourceMatrix"]["rows"])
        self.assertTrue(payload["correlations"]["categories"])
        self.assertEqual(client.calls[0]["offset"], 0)
        self.assertEqual(client.calls[1]["offset"], 60)

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
            [sys.executable, "-m", "sports_edge.cli", "list-sources", "--category", "crypto"],
            [sys.executable, "-m", "sports_edge.cli", "research-bet", "--candidate-id", "fixture-crypto-001"],
            [
                sys.executable,
                "-m",
                "sports_edge.cli",
                "research-topic",
                "--category",
                "geopolitics",
                "--topic",
                "Ukraine ceasefire deadline",
            ],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload)


if __name__ == "__main__":
    unittest.main()
