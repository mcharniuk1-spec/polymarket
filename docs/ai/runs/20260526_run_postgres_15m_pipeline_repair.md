# 2026-05-26 Postgres 15m Pipeline Repair

## Task

Diagnose why the Polymarket dashboard could show yesterday/stale bet rates and harden the research-only 15-minute pipeline.

## Findings

FACT: The existing scheduler was GitHub Actions calling `/api/cron-refresh` every 15 minutes.

FACT: Durable production state depended on JSON state in Vercel Blob, with local-file fallback. There was no PostgreSQL database or relational bet-history table.

FACT: `/api/all` and `/api/multi-agent` recomputed default fixture/dashboard payloads instead of first loading the latest persisted managed-cycle dashboard state.

FACT: Live candidate ids were based on Gamma market id plus outcome index, and live discovery requested volume-ordered markets.

FACT: The serverless live path could make CLOB book requests per outcome when Gamma spread fields were unavailable, increasing timeout risk.

INTERPRETATION: The stale-rate symptom can come from three separate issues: missing durable production storage, dashboard APIs reading generated/default state instead of latest managed-cycle state, and live discovery prioritizing high-volume markets rather than newest listings.

GAP: A one-time live API smoke test from this local workspace timed out even with network approval, so live Polymarket availability from the local machine was not confirmed. Fixture managed-cycle verification passed.

## Changes

- Added optional PostgreSQL-backed state storage selected by `DATABASE_URL`, `POSTGRES_URL`, `POSTGRES_PRISMA_URL`, or `POSTGRES_URL_NON_POOLING`.
- Added automatic PostgreSQL schema/projections:
  - `pipeline_state`
  - `collection_runs`
  - `market_snapshots`
  - `market_news_items`
  - `model_metric_snapshots`
- Kept local JSON and Vercel Blob fallback behavior.
- Changed live Gamma discovery to request `order=createdAt&ascending=false`.
- Added stable live candidate ids based on slug/token/outcome hash.
- Added `published_at`, `updated_at`, and `token_id` to candidate records.
- Sorted all recommendations by publication timestamp for display while preserving top paper bets by rank score.
- Changed dashboard APIs to prefer latest persisted managed-cycle dashboard state.
- Reduced scheduled timeout risk by using Gamma spread/best-bid/best-ask before falling back to CLOB book calls.
- Documented PostgreSQL deployment requirements.

## Verification

- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py`
- `node --check web/app.js`
- `python3 -m unittest discover -s tests`
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --target-count 30 --cycle-type manual`
- `python3 -m sports_edge.cli run-managed-cycle --source live --target-count 20 --cycle-type manual`

## Status

Fixture cycle succeeded. Local live cycle returned fixture fallback because the public Polymarket API request timed out from this environment.

Production still needs a real PostgreSQL URL configured in Vercel before `storage_durable=true` can be expected from `/api/cron-refresh`.
