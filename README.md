# Polymarket Multi-Agent Paper Analytics MVP

Research-only MVP for Polymarket-style market analytics, odds modeling, market/news context review, category expert scoring, bankroll decisions, paper-trading performance, and dashboard review.

This project is intentionally limited to public read-only data, fixture simulation, historical backtesting, and local paper trading. It does not place bets, connect wallets, store credentials, or implement automatic exchange execution.

## Quick Start

```bash
python3 -m sports_edge.cli run-multi-agent
python3 -m sports_edge.cli run-demo
python3 -m sports_edge.cli list-sources --category crypto
python3 -m sports_edge.cli research-bet --candidate-id fixture-crypto-001
python3 -m sports_edge.cli research-topic --category geopolitics --topic "Ukraine ceasefire deadline"
python3 -m sports_edge.cli run-intelligence --source fixture --target-count 300 --cycle-type manual --no-codex
python3 -m sports_edge.cli drain-codex-queue --summary
python3 -m sports_edge.app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` for the dashboard.

## What It Produces

- `reports/multi_agent_run.json` - full multi-agent cycle with 600 candidate bets by default.
- `reports/multi_agent_report.md` - human-readable multi-agent report.
- `data/paper_trades.jsonl` - local paper-trading decision log.
- `reports/performance_report.md` - human-readable performance report.
- `data/generated/intelligence/latest.json` - latest structured intelligence cycle output.
- `data/generated/intelligence/codex_queue/` - local durable queue for Codex backfill reviews when Codex was offline.
- Dashboard API:
  - `/api/multi-agent`
  - `/api/intelligence`
  - `/api/intelligence-refresh`
  - `/api/summary`
  - `/api/forecasts`
  - `/api/performance`
  - `/api/odds-history`
  - `/api/report`

## Modules

- `sports_edge.agents` - multi-agent Polymarket paper pipeline:
  - Market Data Agent
  - Odds Modeling Agent
  - Market Context and News Agent
  - Category Expert Agent
  - Decision and Bankroll Agent
  - Evaluation and Learning Agent
- `sports_edge.polymarket_client` - read-only public Polymarket API client for Gamma/CLOB/Data API surfaces.
- `sports_edge.source_registry` - structured project source registry loader and validator.
- `sports_edge.bet_research` - fixture-backed per-bet and per-topic research brief planner.
- `sports_edge.odds_ingestion` - fixture CSV ingestion and odds normalization.
- `sports_edge.market_news` - market/news context scoring.
- `sports_edge.sports_statistics` - team strength and form features.
- `sports_edge.odds_movement` - opening/latest movement and volatility.
- `sports_edge.risk_control` - paper-only exposure and decision guardrails.
- `sports_edge.synthesis` - final forecast, confidence, and EV synthesis.
- `sports_edge.backtesting` - historical simulation and paper log writing.
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

Vercel does not use local Codex auth. On Vercel, `/api/intelligence` displays stored/generated deterministic analysis and `/api/cron-refresh` runs dashboard-safe deterministic refresh only. The current Hobby Vercel plan cannot run true every-15-minute cron; use local `npm run intelligence:15m`, Vercel Pro Cron, or an external scheduler for unattended 15-minute execution.

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

Required production secrets:

- GitHub: `VERCEL_CRON_URL`, `CRON_SECRET`
- Vercel: `CRON_SECRET`, `BLOB_READ_WRITE_TOKEN`

New dashboard/API state:

- `/api/run-history` - chronological scheduled/manual runs and gaps.
- `/api/model-state` - global/category/question online logistic model health.
- `/api/correlation-matrix` - category related-market correlation summaries.

Codex automation prompts and instruction files live under `docs/ai/automations/`.

## Verification

```bash
python3 -m unittest discover -s tests
node --check web/app.js
python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py
```

## Multi-Agent Run Shape

Default run:

- Analyzes 600 candidates, giving 100 fixture candidates per category: sports, geopolitics, crypto, macro, weather, culture.
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

- Gamma: event, market, tag, sports, team, and search discovery.
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
