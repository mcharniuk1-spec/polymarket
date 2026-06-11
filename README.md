# Polymarket Multi-Agent Paper Analytics MVP

Research-only MVP for Polymarket-style market analytics, odds modeling, market/news context review, three-agent decisioning, bankroll decisions, paper-trading performance, and dashboard review.

This project is intentionally limited to public read-only data, fixture simulation, historical backtesting, and local paper trading. It does not place bets, connect wallets, store credentials, or implement automatic exchange execution.

Active analytical scope is limited to three sections: macroeconomics, politics, and stocks/trade-related markets.

## Quick Start

```bash
python3 -m sports_edge.cli run-multi-agent
python3 -m sports_edge.cli list-sources --category stocks_trade
python3 -m sports_edge.cli research-bet --candidate-id fixture-stocks_trade-001
python3 -m sports_edge.cli research-topic --category politics --topic "election certification deadline"
python3 -m sports_edge.cli run-collector --source fixture --dry-run
python3 -m sports_edge.cli run-daily --source fixture --dry-run
python3 -m sports_edge.cli run-intelligence --source fixture --target-count 300 --cycle-type manual --no-codex
python3 -m sports_edge.cli drain-codex-queue --summary
python3 -m sports_edge.app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` for the dashboard.

## What It Produces

- `reports/multi_agent_run.json` - full multi-agent cycle with 300 candidate bets by default, 100 per active section.
- `reports/multi_agent_report.md` - human-readable multi-agent report.
- `data/paper_trades.jsonl` - legacy local paper-trading log used by historical regression tests only; runtime dashboard payloads do not expose out-of-scope sports records.
- `reports/performance_report.md` - legacy historical performance report; `/api/report` now serves the Polymarket multi-agent report text.
- `data/generated/intelligence/latest.json` - latest structured intelligence cycle output.
- `data/generated/intelligence/codex_queue/` - local durable queue for Codex backfill reviews when Codex was offline.
- Dashboard API:
  - `/api/all`
  - `/api/dashboard-contract`
  - `/api/status`
  - `/api/freshness`
  - `/api/context`
  - `/api/candidates`
  - `/api/decisions`
  - `/api/models`
  - `/api/sources`
  - `/api/portfolio`
  - `/api/performance`
  - `/api/performance-contract`
  - `/api/warnings`
  - `/api/runs/latest`
  - `/api/runs/history`
  - `/api/multi-agent`
  - `/api/intelligence`
  - `/api/intelligence-refresh`
  - `/api/cron-refresh`
  - `/api/run-history`
  - `/api/model-state`
  - `/api/correlation-matrix`
  - `/api/report`

Legacy `/api/summary`, `/api/forecasts`, and `/api/odds-history` routes are scope-disabled compatibility routes. They return empty payloads with `legacySportsDisabled: true` and do not run the old sports backtest. `/api/performance` is the current contract performance endpoint; `/api/performance-contract` remains as a compatibility alias.

## Modules

- `sports_edge.context_agent` - broad category context first, then gated candidate-specific context reports with source reliability, uncertainty, confidence, market relevance, and invalidation triggers.
- `sports_edge.data_agent` - read-only Polymarket market/order-book normalization plus fixture-first external observation contracts.
- `sports_edge.external_adapters` - fixture-first official-source adapters for macro release timing/consensus, political deadlines, stock/trade event windows, and market-data features.
- `sports_edge.decision_agent` - paper-only reject/watchlist/paper-bet decisions, risk gates, fractional-Kelly sizing caps, and context-aware decision notes.
- `sports_edge.model_scoring` - market-implied, liquidity/microstructure, base-rate, Bayesian/consensus, catalyst, statistical/ML readiness, and portfolio EV/risk model outputs with disagreement reporting.
- `sports_edge.orchestrator` - idempotent 15-minute collector and 09:00 Europe/Sofia daily analytical run contracts.
- `sports_edge.dashboard_api` - compact API contract used by Vercel functions and the local app.
- `sports_edge.schemas` - JSON contracts for sources, markets, order books, context reports, model outputs, decisions, portfolio state, and cron runs.
- `sports_edge.safety` - fail-closed guard that blocks live-trading flags and wallet/signing environment variables.
- `sports_edge.agents` - multi-agent Polymarket paper pipeline:
  - Context Agent rollup
  - Data Agent rollup
  - Decision Agent rollup
  - Internal model helpers for odds, context, section rules, decisions, and evaluation
- `sports_edge.polymarket_client` - read-only public Polymarket API client for Gamma/CLOB/Data API surfaces.
- `sports_edge.source_registry` - structured project source registry loader and validator.
- `sports_edge.bet_research` - fixture-backed per-bet and per-topic research brief planner.
- `sports_edge.odds_ingestion` - legacy fixture CSV ingestion and odds normalization retained for regression tests, not active runtime dashboard scope.
- `sports_edge.market_news` - market/news context scoring.
- `sports_edge.sports_statistics` - legacy sports feature helper retained for historical tests only.
- `sports_edge.odds_movement` - legacy opening/latest movement helper retained for historical tests only.
- `sports_edge.risk_control` - paper-only exposure and decision guardrails.
- `sports_edge.synthesis` - final forecast, confidence, and EV synthesis.
- `sports_edge.backtesting` - legacy historical simulation retained for internal regression tests only; active paper-trading decisions use the Polymarket multi-agent and daily orchestrator paths.
- `sports_edge.reporting` - report generation.
- `sports_edge.intelligence` - post-ingestion intelligence cycle, source reliability scoring, deterministic fallback analysis, and optional local-only Codex CLI wrapper.
- `sports_edge.codex_queue` - chronological local queue for replaying Codex review after offline 15-minute cycles.
- `sports_edge.managed_pipeline` - durable 15-minute live collection, chronological agent replay, online logistic model state, and correlation matrices.
- `sports_edge.state_store` - JSON persistence with local development storage and optional Vercel Blob mirroring.

## Intelligence Layer

Run once:

```bash
npm run intelligence:once
```

Run every 15 minutes locally until stopped:

```bash
npm run intelligence:15m
```

Show or drain the Codex backfill queue:

```bash
npm run intelligence:queue
npm run intelligence:drain-codex-queue
```

Run a local queue worker after enabling Codex:

```bash
npm run intelligence:codex-worker
```

The intelligence layer runs after ingestion/modeling, stores compact JSON under `data/generated/intelligence/`, queues missed local Codex reviews, and powers the dashboard `Intelligence` page.

Local Codex analysis is disabled by default. It is only attempted when all of these are set in a trusted local environment:

```bash
ENABLE_LOCAL_CODEX_ANALYSIS=true
CODEX_ANALYSIS_MODE=local-cli
```

Vercel does not use local Codex auth. On Vercel, `/api/intelligence` displays stored/generated deterministic analysis, `/api/cron-refresh` remains a compatibility refresh route, and the deployable cron routes are:

- `/api/cron-collector` - deployable read-only collector orchestration endpoint. The 15-minute schedule is kept on GitHub Actions because the current Vercel Hobby account rejects sub-daily cron expressions.
- `/api/cron-daily` - daily analytical run, scheduled on Vercel at both UTC windows that cover 09:00 Europe/Sofia across DST.

These routes fail closed unless durable storage is configured through Postgres or Vercel Blob. Set `CRON_SECRET` in Vercel to have Vercel send the bearer authorization header automatically for cron invocations.

The repository keeps more API compatibility shims than Vercel Hobby can deploy as separate Serverless Functions. `.vercelignore` limits the production deploy surface to the essential dashboard, health, run-status, report, refresh, and cron functions; source files remain in the repo for local testing and future Pro-plan consolidation.

If Vercel computes a cycle while local Codex is inactive, the API response includes a `codexQueue` item. Without Vercel KV/Blob/Postgres or another durable external store, Vercel cannot persist that queue across serverless invocations; the local queue is durable when the cycle is run or imported locally.

More detail: `docs/intelligence-pipeline.md`.

## Managed 15-Minute Production Flow

GitHub Actions is the default 15-minute scheduler:

```bash
python3 -m sports_edge.cli run-managed-cycle --source live --target-count 300
python3 -m sports_edge.cli run-agent-replay
python3 -m sports_edge.cli run-ml-update --global-review
```

The deployed scheduler calls:

```text
GET /api/cron-refresh?source=live&cycle_type=scheduled_15m&target_count=300
Authorization: Bearer $CRON_SECRET
```

Vercel `vercel.json` cron automation calls:

```text
GET /api/cron-daily
```

GitHub Actions remains the 15-minute collector scheduler:

```text
python3 -m sports_edge.cli run-collector --source live --target-count "$TARGET_COUNT"
```

Required production secrets:

- GitHub: `VERCEL_CRON_URL`, `CRON_SECRET`
- Vercel: `CRON_SECRET`, `DATABASE_URL` or `POSTGRES_URL`

PostgreSQL is the preferred durable store. When a database URL is configured, each run writes both JSON state and queryable relational projections:

- `collection_runs` - every scheduled/manual cycle.
- `market_snapshots` - every gathered market/outcome with publication, collection, decision, and expected resolution timestamps.
- `market_news_items` - timestamped source links/reviews attached to each market snapshot.
- `model_metric_snapshots` - model health snapshots such as Brier/calibration inputs.

`BLOB_READ_WRITE_TOKEN` remains supported as a fallback state mirror, but it is no longer the recommended production database.

New dashboard/API state:

- `/api/runs/latest` - latest analytical run status, warnings, and errors.
- `/api/runs/history` and `/api/run-history` - chronological scheduled/manual runs and gaps.
- `/api/model-state` - global/category/question online logistic model health.
- `/api/correlation-matrix` - category related-market correlation summaries.

Codex automation prompts and instruction files live under `docs/ai/automations/`.

## Three-Agent Daily Contract

The contract-oriented daily run is fixture-first and paper-only by default:

```bash
python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run
```

Daily flow:

1. Safety gate rejects live-trading flags and wallet/signing environment variables.
2. Previous paper bets are evaluated from stored prior daily runs when due, producing resolved outcomes, calibration, drawdown, and knowledge lessons.
3. Context Agent creates broad reports for macroeconomics, politics, and stocks/trade.
4. Data Agent normalizes in-scope market snapshots, order books, source records, and external official-source observations.
5. Model scoring emits all configured model families, uses external observations where available, and reports per-candidate disagreement.
6. Context Agent creates bet-specific reports only for candidates that pass Data Agent/model relevance gates.
7. Decision Agent outputs reject/watchlist/paper-bet records with risk sizing, reasons, invalidation triggers, and evaluation plans.
8. Decision notes, current paper bets, resolved outcomes, and knowledge lessons are exposed through the dashboard contract.
9. The run writes only when not in dry-run mode and the idempotency key has not already completed.

The 15-minute collector contract refreshes lightweight market/data snapshots:

```bash
python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run
```

Both commands support fixture mode without network access. Live mode remains read-only and does not place orders.
Live external adapters can parse source-specific structured public payloads into numeric observations when an approved parser exists.
They do not bypass access controls, and source-health checks or unparsed live pages are explicitly marked as non-decision evidence.

The dashboard `System` tab reads `/api/dashboard-contract` and shows run status, freshness, broad and bet-specific context, candidate decisions, model disagreement, performance, warnings, and errors from the new contract layer.

Use the goal audit to see which parts of the full Polymarket system goal are locally proven and which still require database, deployment, or approved live-source validation:

```bash
python3 -m sports_edge.cli goal-audit
```

Use the production-readiness check before deployment or scheduled-job review. It validates local GitHub Actions/Vercel/API wiring, including live read-only scheduled collector and daily commands, but it does not prove that production jobs have actually run:

```bash
python3 -m sports_edge.cli production-readiness
```

Use the external proof bundle to print the remaining approval-gated evidence checklist without deploying, writing to Postgres, calling live APIs, or exposing secret values:

```bash
python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10
```

The bundle lists the required proof items for Postgres migration application, durable daily writes, approved live-source validation, Vercel dashboard smoke checks, and production cron logs. It is a planning artifact only; commands marked `approvedCommand` must not be run until a human approves the relevant durable write, network, or deployment action.

Postgres migration dry-run is safe without credentials. Actual migration application requires an approved `DATABASE_URL` or `POSTGRES_URL`; the CLI applies the SQL, writes a `schema_migrations` marker, verifies required tables, and masks connection details in output:

```bash
python3 -m sports_edge.cli migrate --dry-run
python3 -m sports_edge.cli migrate --proof-out docs/ai/proofs/20260611_postgres_migration_proof.json
```

After an approved real migration, `--proof-out` saves only sanitized proof metadata to `docs/ai/proofs/20260611_postgres_migration_proof.json`. The goal audit accepts it only when it proves `researchOnly=true`, `paperTradingOnly=true`, `migration.ok=true`, `migration.applied=true`, durable storage, all 13 milestone tables verified, `missingTables=[]`, no credential values in logs, and no wallet/order execution enabled.

Production cron proof is also file-gated. After approved GitHub Actions or Vercel cron review, create an operator-sanitized evidence JSON that includes both `scheduledJobs.collector_15m` and `scheduledJobs.sofia_daily`, each with `observed=true`, `status=success` or `duplicate_skipped`, and `sourceMode=live`. Then generate the audit proof without fetching logs or storing credentials:

```bash
python3 -m sports_edge.cli production-cron-proof --evidence-in sanitized-cron-evidence.json --dry-run
python3 -m sports_edge.cli production-cron-proof --evidence-in sanitized-cron-evidence.json --proof-out docs/ai/proofs/20260611_production_cron_run.json
```

The proof command strips URL query strings/fragments, requires `paper_trading_only=true`, `durable_storage_gate_passed=true`, `logs_contain_credentials=false`, `wallet_or_order_execution_enabled=false`, and refuses incomplete collector/daily evidence.

Approved live-source validation is also proof-file gated. After an approved read-only live dry-run and source/ToS review, create sanitized evidence with `sourceMode=live`, one observed row for each active category (`macroeconomics`, `politics`, and `stocks_trade`), parser-verified numeric observation counts, rule/resolution capture checks, and no wallet/order execution:

```bash
python3 -m sports_edge.cli live-source-proof --evidence-in sanitized-live-source-evidence.json --dry-run
python3 -m sports_edge.cli live-source-proof --evidence-in sanitized-live-source-evidence.json --proof-out docs/ai/proofs/20260611_live_source_validation.json
```

The live-source proof stores only validation counts and booleans. It rejects missing category evidence, missing parser-verified observations, missing resolution proof validation, logs with credential exposure, or any wallet/order execution flag.

## Verification

```bash
python3 -m unittest discover -s tests
node --check web/app.js
python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py
python3 -m json.tool config/news-sources.json
python3 -m sports_edge.cli migrate --dry-run
python3 -m sports_edge.cli goal-audit
python3 -m sports_edge.cli production-readiness
python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10
python3 -m sports_edge.cli production-cron-proof --evidence-in sanitized-cron-evidence.json --dry-run
python3 -m sports_edge.cli live-source-proof --evidence-in sanitized-live-source-evidence.json --dry-run
python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run
python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run
python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run
```

## Multi-Agent Run Shape

Default run:

- Analyzes 300 candidates, giving 100 fixture candidates per section: macroeconomics, politics, stocks/trade.
- Builds top-10 paper bets.
- Simulates a 100-coin bankroll with a 100-coin paper deployment target.
- Splits decisions into paper bets, watchlist, rejected, and no-bet candidates.
- Scores each agent after fixture settlement using Brier/log-loss style metrics and loss attribution.

Live public API mode:

```bash
python3 -m sports_edge.cli run-multi-agent --source live --target-count 200
```

Live mode is read-only. It uses public Gamma market discovery and CLOB orderbook checks where available, then falls back to fixtures if public network access is unavailable.

## API Strategy

- Gamma: event, market, tag, and search discovery.
- CLOB: orderbook, executable quotes, midpoint, spread, last trade, and price-history analytics.
- Data API: trades, activity, holders, live volume, open interest, positions where relevant.
- WebSocket channels are the right future surface for live orderbook/price updates.
- UI scraping is not used for data that official APIs expose.

## Project Skills And Source Registry

- `docs/ai/PROJECT_SKILLS.md` routes project-local skills for ingestion, history, modeling, forecasting, news analysis, bet research, decision review, psychology, portfolio optimization, and monitoring.
- `docs/ai/source_registry.json` lists global, Polymarket, and category-specific sources with access status, reliability tier, freshness, history depth, and default eligibility.
- Research commands are fixture-backed by default. They build source/query plans and evidence briefs without live network fetches.

## Safety Constraints

- Default records are local deterministic fixtures.
- External API calls only happen with `--source live`.
- No real-money bet placement or automatic execution exists in this codebase.
- Stake sizing is simulated in units for research only.
- No API keys, wallet keys, cookies, or credentials are requested or stored.
