# 2026-06-10 Run - External Data, Automation, Dashboard Finish Pass

## Task
Continue toward the full Polymarket analytical paper-trading goal by closing locally-completable gaps across external observations, model feature use, automation, dashboard contract rendering, and migration validation.

## Outputs
- Added `sports_edge/external_adapters.py`.
- Data Agent now emits seven source records and five normalized external observations in fixture mode:
  - macro `days_until_next_release`
  - macro `consensus_surprise_z`
  - politics `deadline_delay_risk_index`
  - stocks/trade `event_window_days`
  - stocks/trade `underlying_return_1d`
- Model scoring now consumes external observations in:
  - base-rate/event-history features
  - Bayesian/consensus features
  - news/catalyst sentiment features
- Dashboard now has a `System` tab reading `/api/dashboard-contract` and rendering:
  - run status
  - freshness
  - broad and bet-specific context
  - candidate decisions
  - model disagreement
  - performance summary
  - warnings and errors
- GitHub Actions schedule now includes:
  - 15-minute collector path through `run-collector --source live`
  - daily Sofia-time windows at `0 6 * * *` and `0 7 * * *` through `run-daily --source fixture`
  - duplicate-safe validation for both collector and daily analytical paths
- Added `python3 -m sports_edge.cli migrate --dry-run` to validate migration table/index coverage without requiring a database URL.
- README now documents external adapters, the System tab, and migration dry-run validation.

## Validation
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m unittest discover -s tests` passed: 39 tests.
- `python3 -m json.tool config/news-sources.json` passed.
- `python3 -m sports_edge.cli migrate --dry-run` passed.
  - migration id: `20260610_milestone1_research_contracts`
  - tables: 13
  - indexes: 6
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` passed.
  - source records: 7
  - external observations: 5
  - model outputs: 21
  - decision notes: 3
  - schema validation: ok
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` passed.
  - market snapshots: 3
  - order books: 3
  - source records: 7
  - external observations: 5
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` passed and wrote nothing.
- Dashboard contract route builder passed direct validation:
  - candidates: 3
  - broad context: 3
  - bet-specific context: 2
  - model outputs: 21
  - performance status: `no_prior_paper_bets`

## Local Server Note
`python3 -m sports_edge.app --host 127.0.0.1 --port 8877` created a listening socket visible to `lsof`, but sandbox loopback `curl` still failed immediately with connection refused. The app process was stopped and no dashboard server was left running. Direct route-function validation remains the reliable local evidence for the dashboard contract in this sandbox.

## Files Changed
- `sports_edge/external_adapters.py`
- `sports_edge/data_agent.py`
- `sports_edge/model_scoring.py`
- `sports_edge/orchestrator.py`
- `sports_edge/cli.py`
- `.github/workflows/polymarket-15m.yml`
- `web/index.html`
- `web/app.js`
- `web/styles.css`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260610_run_external_automation_dashboard_finish_pass.md`

## Completion Audit
FACT: The repo now has paper-only safety gates, three active sections, Context/Data/Decision Agent contracts, model-family outputs, model disagreement, risk-gated paper decisions, prior paper-bet evaluation, source/evidence records, daily and collector dry-runs, idempotency keys, migration definitions, dashboard API sections, a System UI tab, tests, and README documentation.

GAP: The full goal cannot honestly be marked complete yet because several requirements need external-state validation or further implementation:
- live official external adapters are still pending and fixture-first only;
- live outcome/resolution proof ingestion is still pending;
- Postgres migration execution has dry-run validation but not a real database integration proof in this sandbox;
- the local HTTP dashboard could not be verified with `curl` despite a listening socket;
- Vercel deployment was intentionally not performed;
- production scheduled jobs were not executed from GitHub Actions in this session.

## Next Steps
1. Run Postgres migration/apply validation against an approved database URL.
2. Implement read-only official live adapters for selected sources with source-specific ToS and rate-limit review.
3. Verify the deployed Vercel dashboard contract routes after deployment approval.
4. Add live resolved-outcome ingestion with official proof URLs and no-future-data checks.
