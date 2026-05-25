---
title: Intelligence Pipeline 15m MVP
date: 2026-05-25
project: polymarket
status: completed
research_only: true
---

# Intelligence Pipeline 15m MVP

## Task

Add a temporary but reliable MVP intelligence layer that runs after Polymarket ingestion/modeling, supports local 15-minute execution, optionally uses local Codex only in a trusted environment, stores compact structured outputs, and renders results in the dashboard.

## Outputs

- Added `sports_edge/intelligence.py`.
- Added `scripts/run_intelligence_cycle.py`.
- Added `config/news-sources.json`.
- Added API routes:
  - `/api/intelligence`
  - `/api/intelligence-refresh`
- Extended `/api/cron-refresh` to run deterministic intelligence refresh.
- Extended local `sports_edge.app` so post-ingestion refresh also stores intelligence output.
- Added package scripts:
  - `npm run intelligence:once`
  - `npm run intelligence:watch`
  - `npm run intelligence:15m`
- Added dashboard `Intelligence` page with:
  - last run/status/Codex state;
  - market signal cards;
  - probability history and forecast interval SVG;
  - source reliability panel;
  - run history;
  - fallback/local-auth boundary explanation.
- Added generated baseline:
  - `data/generated/intelligence/latest.json`
  - `data/generated/intelligence/analysis_runs.json`
  - `data/generated/intelligence/source_snapshots.json`
  - `data/generated/intelligence/market_analysis_results.json`
- Added `docs/intelligence-pipeline.md`.

## 15-Minute Behavior

- Local reliable 15-minute loop: `npm run intelligence:15m`.
- Safe endpoint: `/api/cron-refresh` runs dashboard refresh plus deterministic intelligence refresh.
- Vercel Hobby still cannot run true 15-minute Vercel Cron; use Vercel Pro Cron, an external scheduler, or the local loop for unattended 15-minute execution.

## Local Codex Boundary

Codex is disabled unless both are set:

- `ENABLE_LOCAL_CODEX_ANALYSIS=true`
- `CODEX_ANALYSIS_MODE=local-cli`

If Codex CLI is missing, fails, is unauthenticated, or emits invalid JSON, the cycle stores partial/fallback status and deterministic analysis remains available.

## Verification

- `python3 -m unittest discover -s tests`
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py`
- `node --check web/app.js`
- `python3 -m json.tool config/news-sources.json`
- Local `/api/intelligence`: success, 300 markets, average reliability 0.6913, Codex skipped.
- Local `/api/cron-refresh`: success, 300 candidates, intelligence status success.
- Production `/api/intelligence`: success, 300 markets, average reliability 0.6913, Codex skipped.
- Production `/api/cron-refresh`: success, 300 candidates, 300 intelligence markets.
- Browser QA:
  - local `/?page=intelligence`
  - production `/?page=intelligence&verify=intel`

## Safety

No wallet, credentials, local Codex auth files, tokens, order posting, real-money betting, or automated execution were added or exposed.
