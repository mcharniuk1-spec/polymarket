# 2026-06-10 Run - Outcome Evaluation And Knowledge Lessons

## Task
Continue the research-only Polymarket analytical paper-trading rebuild by adding the daily-run step that evaluates previous paper bets, updates performance/calibration/drawdown, and records knowledge lessons after outcomes.

## Inputs
- Active goal: paper-only prediction-market analytics for macroeconomics, politics, and stocks/trade.
- Existing schema, Data Agent, Context Agent, model scoring, Decision Agent, state store, and dashboard contract.
- Safety boundary: no wallet, signing, order execution, live betting, deployment, or irreversible actions.

## Outputs
- Added schema contracts for:
  - `PaperBet`
  - `ResolvedOutcome`
  - `DecisionNote`
  - `KnowledgeLesson`
- Added `sports_edge/outcome_evaluator.py`.
- Daily orchestrator now evaluates previous stored paper bets before new context/data/model/decision stages.
- Fixture mode can resolve due stored paper bets against explicit deterministic fixture results.
- Live mode does not resolve outcomes until a read-only resolution adapter exists.
- Decision notes are generated for current daily decisions.
- Previous evaluation output now includes:
  - paper trading history
  - resolved outcomes
  - calibration buckets and Brier score when labels exist
  - drawdown summary
  - knowledge lessons
  - warnings
- Dashboard performance contract now exposes history, resolved outcomes, calibration, drawdown, current paper bets, and knowledge lessons.
- Postgres projection now upserts resolved outcomes, decision notes, and knowledge lessons from daily-run payloads.
- README daily-flow documentation now includes previous paper-bet evaluation and knowledge updates.

## Validation
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m unittest discover -s tests` passed: 37 tests.
- `python3 -m json.tool config/news-sources.json` passed.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` passed.
  - `ok=True`
  - `schemaOk=True`
  - `idempotencyKey=daily:2026-06-10`
  - previous evaluation status: `no_prior_paper_bets`
  - resolved outcomes: 0
  - decision notes: 3
  - knowledge lessons: 0
  - schema-checked records: 39
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` passed.
  - `idempotencyKey=collector:2026-06-10T06:00Z`
  - market snapshots: 3
  - order books: 3
  - source records: 5
  - external observations: 3
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` passed and wrote nothing.
- Added tests prove a seeded prior fixture paper bet resolves to a loss, creates a `loss_review` lesson, updates calibration, and reports drawdown through the dashboard contract.

## Files Changed
- `sports_edge/schemas.py`
- `sports_edge/outcome_evaluator.py`
- `sports_edge/orchestrator.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/state_store.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260610_run_outcome_evaluation_knowledge.md`

## Gaps
- Outcome resolution is fixture-only until read-only official/Polymarket resolution adapters are implemented.
- Postgres projection compiles but still needs execution against a real migrated database.
- Current daily fixture decisions produce no new paper bets because the conservative Decision Agent gates reject/watchlist them.
- The static dashboard UI still needs direct visual integration for the new performance fields.
- Full objective remains incomplete: official external adapters, richer context fetching, calibrated base-rate datasets, and production cron verification remain pending.

## Next Steps
1. Implement migration execution/integration validation for Postgres-backed daily runs.
2. Add read-only outcome/resolution adapters with source proof and no-future-data checks.
3. Update the static dashboard UI to render performance history, calibration, drawdown, and lessons from `/api/performance-contract`.
