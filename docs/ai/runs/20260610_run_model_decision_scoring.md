# 2026-06-10 Run - Model Scoring And Decision Agent

## Task
Implement the next part of Milestone 1 for the Polymarket analytical paper-trading rebuild: fixture-first model scoring, paper-only decision logic, dashboard contract routing, and local validation.

## Inputs
- Approved rebuild blueprint for a research-only Polymarket analytical and paper-trading system.
- Existing Milestone 1 schema, migration, data-agent, dashboard, collector, and orchestrator work.
- Active scope: macroeconomics, politics, and stocks/trade-related markets.

## Outputs
- Added fixture-first model scoring across these model families:
  - market-implied probability
  - liquidity/microstructure
  - base-rate/event-history
  - Bayesian/consensus
  - news/catalyst sentiment
  - statistical/ML placeholder with explicit insufficient-data gap
  - portfolio EV/risk
- Added a paper-only Decision Agent with reject/watchlist/paper-bet outcomes, confidence labels, risk gates, fractional-Kelly sizing, exposure caps, invalidation triggers, and evaluation plans.
- Wired the daily dry-run orchestrator to use the Data Agent, model scoring, and Decision Agent.
- Extended Postgres projection logic for daily analytical records and collector records.
- Added dashboard contract API route files and local app contract routes.
- Changed the local dashboard app to lazy-load legacy dashboard state so contract routes can start without running heavy legacy refresh work before HTTP bind.

## Validation
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m unittest discover -s tests` passed: 33 tests.
- `python3 -m json.tool config/news-sources.json` passed.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` passed.
  - `ok=True`
  - `dryRun=True`
  - `idempotencyKey=daily:2026-06-10`
  - sections: macroeconomics, politics, stocks_trade
  - context reports: 3
  - market snapshots: 3
  - order books: 3
  - source records: 5
  - external observations: 3
  - model outputs: 21
  - decision signals: 3
  - portfolio snapshot: present
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` passed.
  - `ok=True`
  - `idempotencyKey=collector:2026-06-10T06:00Z`
  - market snapshots: 3
  - order books: 3
  - source records: 5
  - external observations: 3
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` passed.
  - `ok=True`
  - `dryRun=True`
  - candidates: 30
  - paper bets from legacy managed-cycle path: 6
  - storage: not written because dry-run
- Dashboard contract route builder passed shape validation for status, freshness, context, candidates, decisions, models, sources, portfolio, performance, warnings, and aggregate payloads.

## Files Changed
- `sports_edge/model_scoring.py`
- `sports_edge/decision_agent.py`
- `sports_edge/orchestrator.py`
- `sports_edge/state_store.py`
- `sports_edge/app.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/data_agent.py`
- `sports_edge/schemas.py`
- `sports_edge/migrations.py`
- `sports_edge/safety.py`
- `sports_edge/cli.py`
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

## Gaps
- No real external macro, politics, or stocks/trade adapters are implemented yet.
- Statistical/ML probability is intentionally disabled until enough resolved, as-of-safe outcome history exists.
- Postgres projection SQL compiles but still needs integration validation against a real migration-applied database.
- Local dashboard HTTP server route functions validate, but loopback curl from this sandbox could not connect reliably to the temporary server process despite the socket appearing in `lsof`.
- Existing legacy managed-cycle scoring can still output paper bets independently of the new Decision Agent. The new daily analytical path remains paper-only and conservative.

## Next Steps
1. Implement official/read-only external adapters and source freshness checks.
2. Add migration execution and Postgres integration tests.
3. Build broad and bet-specific Context Agent persistence from registered sources.
4. Replace deterministic model priors with calibrated base-rate and consensus datasets.
5. Update the static dashboard UI to consume the new contract sections directly.
