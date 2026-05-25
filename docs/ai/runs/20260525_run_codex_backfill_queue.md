---
title: Codex Backfill Queue For Intelligence Cycles
date: 2026-05-25
tags:
  - project/polymarket
  - intelligence
  - queue
  - vercel
  - research-only
---

# Codex Backfill Queue For Intelligence Cycles

## Task

Add a backup queue so 15-minute collection/modeling cycles still preserve local Codex review work when Codex is not active, then process queued cycles in order after Codex becomes available locally.

## Facts

- The project remains research-only and paper-only.
- Vercel must not use local Codex authentication.
- Local persisted intelligence cycles now enqueue Codex review work under `data/generated/intelligence/codex_queue/` when local Codex is unavailable.
- Vercel serverless endpoints emit a queue item in the response but do not claim durable hosted persistence without an external store.

## Implementation

- Added `sports_edge/codex_review.py` for the local-only Codex CLI boundary.
- Added `sports_edge/codex_queue.py` for queue item creation, local persistence, summaries, and ordered draining.
- Added `scripts/run_codex_queue.py`.
- Extended `scripts/run_intelligence_cycle.py` to queue missed Codex reviews and attempt a safe drain after each run.
- Added CLI command `python3 -m sports_edge.cli drain-codex-queue`.
- Added API route `/api/codex-queue`.
- Added dashboard queue status display on the Intelligence page.
- Updated README and `docs/intelligence-pipeline.md`.

## Verification

- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py`
- `python3 -m unittest discover -s tests`
- `node --check web/app.js`
- `npm run intelligence:once`
- `npm run intelligence:queue`
- Local server smoke test on `127.0.0.1:8766`.
- Production Vercel deployment and endpoint smoke tests.

## Results

- Production dashboard alias: `https://polymarket-research-dashboard.vercel.app/`
- Production `/api/intelligence`: success, 300 markets, Vercel queue shown as `deployment_snapshot`.
- Production `/api/cron-refresh`: success, 300 candidates, 70 paper bets, queue emitted as `emitted_not_persisted`.
- Local queue summary after verification: pending cycles exist because Codex was not enabled in the shell.

## Interpretation

The local queue now preserves the chronological decision-review sequence for local persisted cycles. Hosted Vercel can safely produce deterministic outputs and queue payloads, but true Vercel-to-local replay requires a durable external store or a scheduler that captures response payloads.

## Gap

External durable queue persistence for Vercel-generated cycles is not implemented because no Vercel KV, Blob, Postgres, or similar configured store was provided. This is the next required piece for fully unattended hosted-to-local backfill.
