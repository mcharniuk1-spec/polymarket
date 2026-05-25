---
title: Explicit Dashboard Decision Views
date: 2026-05-25
project: polymarket
status: completed
research_only: true
---

# Explicit Dashboard Decision Views

## Task

Expand the dashboard so current bets are clickable, state-colored, source-linked, and explainable through a top-to-bottom decision process with news influence, event sub-bets, history, model data, forecasts, and portfolio impact.

## Outputs

- Added `sports_edge/dashboard_enrichment.py`.
- Dashboard API now includes:
  - `portfolio_rules`
  - `collection_plan`
  - `source_reviews_by_category`
  - `news_influence_graph`
  - `event_groups`
  - compact `bet_detail_records`
- Changed paper allocation to target the full 100-coin paper bankroll across simultaneous qualified bets.
- Changed dashboard default to 300 fixture candidates for reliable Vercel/browser payload size while keeping the pipeline capable of 600+ runs when requested.
- Added compact runtime JSON responses for Vercel/local API reliability.
- Added dashboard pages/sections:
  - always-visible portfolio strip
  - Current Bets
  - News
  - Events and sub-bets
  - richer Bet Detail with decision process, source links, monitored values, model cards, history/forecast graph, failure conditions, and event siblings
- Kept live public API mode opt-in and read-only; fixture mode remains the default.

## Verification

- `python3 -m unittest discover -s tests`
- `python3 -m py_compile sports_edge/*.py api/*.py`
- `node --check web/app.js`
- Local `/api/all` smoke: 300 candidates, 300 bet detail records, 150 event groups, 100.0 paper coins staked.
- Local browser QA:
  - `http://127.0.0.1:8766/`
  - `http://127.0.0.1:8766/?page=news`
  - `http://127.0.0.1:8766/?page=details`
- Production deploy:
  - Stable URL: https://polymarket-research-dashboard.vercel.app/
  - Deployment URL: https://polymarket-research-dashboard-d2shz2eit.vercel.app/
- Production API smoke:
  - `/api/all`: 300 candidates, 300 bet detail records, 24 news nodes, 150 event groups, 100.0 paper coins staked.
  - `/api/cron-refresh`: `ok=true`, 300 candidates, research-only.

## Constraint

The dashboard scripts public/API-key-free sources in fixture mode by default. Paid, keyed, unofficial, or license-sensitive sources remain visible for planning but disabled by default.

## Safety

No wallet, credential storage, order posting, real-money betting, or automated execution was added.
