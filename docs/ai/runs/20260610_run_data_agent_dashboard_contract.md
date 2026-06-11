---
title: Data Agent And Dashboard Contract API
date: 2026-06-10
tags:
  - project/polymarket
  - run
  - data-agent
  - dashboard-api
  - paper-trading-only
---

# Data Agent And Dashboard Contract API

## Task

Continue the Polymarket analytical paper-trading rebuild after Milestone 1 by adding the first read-only Data Agent and dashboard/API contract surface.

## Outputs

- Added normalized schema contracts for market snapshots, order book snapshots, and external observations.
- Added a read-only `DataAgent` that normalizes fixture Gamma markets, order books, and external adapter-readiness observations.
- Wired Data Agent output into the fixture-first daily orchestrator.
- Added dashboard contract assembly for run status, freshness, context, candidates, decisions, models, sources, portfolio, performance, warnings, and errors.
- Added thin Vercel API routes for each dashboard section plus a full dashboard-contract route.
- Added equivalent local development server routes.
- Added tests for Data Agent normalization, out-of-scope filtering, order-book parsing, and dashboard API shape.

## Status

Completed locally. No deploy was run. No live API calls were required.

## Checks

- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m json.tool config/news-sources.json` passed.
- `python3 -m unittest discover -s tests` passed: 26 tests.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` passed.
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` passed.
- Dashboard contract smoke check passed with all expected sections.

## Files Changed

- `sports_edge/schemas.py`
- `sports_edge/data_agent.py`
- `sports_edge/orchestrator.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/app.py`
- `api/status.py`
- `api/freshness.py`
- `api/context.py`
- `api/candidates.py`
- `api/decisions.py`
- `api/models.py`
- `api/sources.py`
- `api/portfolio.py`
- `api/performance-contract.py`
- `api/warnings.py`
- `api/dashboard-contract.py`
- `tests/test_pipeline.py`
- `docs/ai/runs/20260610_run_data_agent_dashboard_contract.md`

## Gaps

- External observations are still adapter-readiness contracts, not live official macro/politics/stocks data.
- Data Agent live mode exists through the read-only public client but was not invoked in this run.
- The dashboard frontend has not yet been redesigned to consume the new contract routes.

## Next Steps

- Implement durable collector writes for normalized market and order-book snapshots.
- Add official external source adapters for macro calendars, political/election calendars, and stocks/trade event calendars.
- Replace fixture decision/model rows with real candidate rows from normalized Data Agent output.
