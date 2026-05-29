# 2026-05-29 Scheduler Reliability And Scope Review

## Safety Boundary

FACT: This remains research-only and paper-only. No wallet actions, credential storage, order posting, or real-money betting are implemented.

## Incident

FACT: GitHub Actions run `26635455724` for `Polymarket 15m Research Cycle` failed in job `call-vercel-cron`.

FACT: The job log shows GitHub called `https://polymarket-research-dashboard.vercel.app/api/cron-refresh?source=live&cycle_type=scheduled_15m&target_count=300&global_review=false`.

FACT: Vercel returned `504 FUNCTION_INVOCATION_TIMEOUT` after roughly 30 seconds.

FACT: The GitHub job environment showed `CRON_SECRET` empty, so the production cron endpoint is publicly callable unless Vercel has a separate protection layer.

INTERPRETATION: The 15-minute worker should not rely on a 30-second Vercel serverless function for the full managed cycle. Vercel is suitable for dashboard/API serving and small health checks; GitHub Actions or a dedicated worker is more suitable for scheduled data/model runs.

## Fix Applied Locally

FACT: `.github/workflows/polymarket-15m.yml` now runs the managed cycle directly on the GitHub runner instead of calling the heavy Vercel cron endpoint.

FACT: The workflow installs Python dependencies, runs `python3 -m sports_edge.cli run-managed-cycle --source live --cycle-type scheduled_15m`, validates live data, validates research-only status, and requires durable storage.

FACT: The workflow now fails fast with a clear message if GitHub Actions lacks `DATABASE_URL`, `POSTGRES_URL`, `POSTGRES_PRISMA_URL`, `POSTGRES_URL_NON_POOLING`, or `BLOB_READ_WRITE_TOKEN`.

FACT: The workflow keeps a lightweight Vercel dashboard smoke check.

## Current Data Review

FACT: The latest wide local full scan gathered 6,000 active Polymarket Gamma markets and built 7,876 eligible outcome candidates.

FACT: It identified 2,899 event groups, 1,159 correlation pairs, and sampled 300 CLOB price histories with zero history-request errors.

FACT: 7,576 candidates still used Gamma-derived fallback history instead of observed CLOB history.

FACT: The current source matrix marks Polymarket Gamma and CLOB as currently fetched. External news/context sources are planned and visible, but live external news fetching is not yet wired into the scoring path.

## Scope Decision

FACT: Culture and sports produced the strongest current paper-decision surface.

FACT: Culture had 1,468 candidates, 159 event groups, 4 paper-bet decisions, and 2 watchlist decisions across the full universe.

FACT: Sports had 404 candidates, 19 event groups, 1 paper-bet decision, and 1 watchlist decision.

FACT: Crypto had 5,398 candidates and 2,662 event groups, but produced no paper-bet decisions after correlation, volatility, and guardrails.

FACT: Weather had many structured threshold groups but all were rejected in the current run because source and spread/wording risk were too weak.

FACT: Geopolitics and macro were sparse and included category misclassification, so they are not reliable primary decision scopes yet.

RECOMMENDATION: Keep broad discovery, but focus decision-making and news-source effort on event-dense sports and culture clusters: MLB/NBA games, tennis matches, Counter-Strike, Dota, and LoL. Use crypto primarily as a time-series/calibration laboratory until the model has stronger observed history and volatility controls. Keep weather/geopolitics/macro as watchlist unless official source evidence and settlement wording are strong.

## What Worked

- Event grouping worked best for markets with many sibling bets: NBA totals/spreads, MLB game totals/spreads, tennis match markets, esports map/match markets, crypto strike ladders, and weather threshold ladders.
- Mutually exclusive guardrails caught sibling conflicts and downgraded weaker sides to watchlist.
- CLOB price-history sampling worked reliably for the bounded 300-token sample.
- The full-scan artifact set is now useful for audits: top recommendations, event groups, correlations, time-series samples, market coverage, source matrix, and monitoring instructions.

## What Is Lacking

- Production scheduling was incorrectly pushing full work through Vercel's 30-second function budget.
- GitHub `CRON_SECRET` was empty in the observed failed run.
- The live news layer is still mostly planned/source-matrix based; external category news is not yet fetched and attached to decisions.
- Polymarket Data API trades are implemented in the client but not wired into the full scan or managed-cycle scoring.
- Time-series persistence is not normalized into durable price/trade/order-book tables yet.
- Category classification needs stronger tag/series handling; some weather markets appear under geopolitics.

## Next Build Targets

1. Configure durable storage secrets in GitHub Actions and Vercel.
2. Push/deploy the workflow fix.
3. Add a fast Vercel health endpoint and keep heavy scheduled work off Vercel functions.
4. Wire Polymarket Data API trades into candidate features.
5. Add source-specific external news fetchers for the chosen primary scope.
6. Add normalized durable tables for outcome tokens, price history, trades/activity, source evidence, decisions, and resolved labels.
