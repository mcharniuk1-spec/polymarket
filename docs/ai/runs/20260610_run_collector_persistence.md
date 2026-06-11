---
title: Collector Persistence And Idempotency
date: 2026-06-10
tags:
  - project/polymarket
  - run
  - collector
  - storage
  - idempotency
  - paper-trading-only
---

# Collector Persistence And Idempotency

## Task

Continue the research-only Polymarket analytical system by adding a 15-minute read-only collector path that can persist normalized Data Agent snapshots safely and idempotently.

## Outputs

- Added `CollectorRunConfig` and `run_collector` with 15-minute UTC bucket keys.
- Added `run-collector` CLI command with `--source`, `--target-count`, `--dry-run`, `--as-of`, and `--force`.
- Collector writes `collector_runs/<id>.json` and `collector_latest.json` only when not in dry-run and not a duplicate.
- Dashboard contract loader now merges the latest collector Data Agent freshness into the dashboard contract.
- Postgres state projection now supports collector payloads:
  - `cron_runs`;
  - `collection_runs`;
  - `external_source_records`;
  - `market_snapshots`;
  - `order_book_snapshots`;
  - `external_observations`.
- Migration SQL now includes additional market snapshot columns and a unique `(run_id, market_id)` index for collector upserts.
- Added tests for collector dry-run, persistence, duplicate protection, CLI output, and dashboard collector freshness merge.

## Status

Completed locally. No deploy was run. No live API calls were required.

## Checks

- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m unittest discover -s tests` passed: 30 tests.
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` passed.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` passed.
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` passed.
- `python3 -m json.tool config/news-sources.json` passed.
- Dashboard contract smoke check passed with all expected sections.

## Files Changed

- `sports_edge/data_agent.py`
- `sports_edge/orchestrator.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/state_store.py`
- `sports_edge/migrations.py`
- `sports_edge/cli.py`
- `tests/test_pipeline.py`
- `docs/ai/runs/20260610_run_collector_persistence.md`

## Gaps

- Collector live mode is still unverified in this environment because network access is restricted and no live API call was requested.
- External observations still represent adapter readiness only.
- Decision/model rows still use fixture contract candidates rather than normalized Data Agent market candidates.

## Next Steps

- Implement model scoring over normalized Data Agent candidates.
- Replace contract-only model outputs with market-implied, liquidity, base-rate, catalyst, and portfolio-risk outputs.
- Update Decision Agent to consume normalized market candidates and produce reject/watchlist/paper-bet decisions from real evidence quality gates.
