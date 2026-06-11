---
title: Milestone 1 Contracts And Daily Orchestrator
date: 2026-06-10
tags:
  - project/polymarket
  - run
  - milestone-1
  - paper-trading-only
---

# Milestone 1 Contracts And Daily Orchestrator

## Task

Implement the first approved rebuild milestone for the Polymarket research-only paper-trading system:

- normalized schema contracts;
- Postgres migration definitions;
- fixture-first dry-run daily orchestrator for macroeconomics, politics, and stocks/trade markets;
- duplicate-run/idempotency protection;
- no-live-trading safety gates;
- validation tests and dry-run commands.

## Outputs

- Added schema contracts for sources, context reports, model outputs, decisions, portfolio state, and cron runs.
- Added non-destructive Postgres migration SQL for milestone storage tables.
- Added a paper-trading safety gate that fails closed on live-trading flags or wallet/signing secret variables.
- Added `run-daily` CLI command with Europe/Sofia 09:00 idempotency keying.
- Added `run-managed-cycle --dry-run` fixture-only compatibility path.
- Added tests for contracts, duplicate protection, safety gates, migration coverage, and CLI dry-runs.

## Status

Completed locally. No deploy was run. No live API calls were required.

## Checks

- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m json.tool config/news-sources.json` passed.
- `python3 -m unittest discover -s tests` passed: 23 tests.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` passed.
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` passed.

## Files Changed

- `sports_edge/safety.py`
- `sports_edge/schemas.py`
- `sports_edge/migrations.py`
- `sports_edge/orchestrator.py`
- `sports_edge/state_store.py`
- `sports_edge/cli.py`
- `tests/test_pipeline.py`
- `docs/ai/runs/20260610_run_milestone1_contracts_orchestrator.md`

## Blockers And Gaps

- External WikiLLM/vault writes were not attempted because they are outside the writable project root in this session.
- The local dashboard server was not started because `sports_edge.app` writes reports/data during module initialization and Milestone 1 did not modify dashboard code.
- Live external numeric adapters remain Milestone 2 work.

## Next Steps

- Implement Milestone 2 data normalization: Polymarket market/order-book snapshots and official external source adapters.
- Add API endpoints for latest run, freshness, context, candidates, model outputs, decisions, portfolio, and performance.
- Replace fixture contract rows with real candidate rows once Data Agent selection is normalized.
