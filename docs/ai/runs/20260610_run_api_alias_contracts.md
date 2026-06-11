# 2026-06-10 Run - API Alias Contracts

## Task
Continue the Polymarket analytical-system goal by aligning the API route surface with the dashboard/API requirements for run status, run history, and performance, without deployment or live writes.

## FACT
- Added contract helpers `runs_latest_payload()` and `runs_history_payload()` in `sports_edge.dashboard_api`.
- Added Vercel route shims:
  - `api/performance.py`
  - `api/runs/latest.py`
  - `api/runs/history.py`
- Local app routing now exposes:
  - `/api/performance` as the active contract performance endpoint.
  - `/api/performance-contract` as a compatibility alias.
  - `/api/runs/latest` and `/api/runs/history` as run-status aliases.
- `production-readiness` now requires the new route shims and reports 16 dashboard contract routes.
- README now documents `/api/performance`, `/api/runs/latest`, and `/api/runs/history`.

## INTERPRETATION
The API surface is closer to the requested dashboard contract. Performance is no longer treated as a disabled legacy sports route; it is now a first-class Polymarket contract endpoint, while legacy sports routes remain disabled for summary, forecasts, and odds history.

## GAP
- This pass did not deploy Vercel, apply a real Postgres migration, validate live public sources, or inspect production cron logs. `goal-audit` correctly remains incomplete.

## Validation
- `python3 -m unittest discover -s tests` - passed, 53 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `python3 -m compileall -q api/runs` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed, 16 contract routes.
- `python3 -m sports_edge.cli migrate --dry-run` - passed, 13 tables and 6 indexes reported.
- `python3 -m sports_edge.cli goal-audit` - passed, complete remains `false`; 10 proven, 2 partial, 3 missing.
- Fixture collector, daily, and managed-cycle dry-run summaries all passed with `storageWritten: false`.
- Direct alias shape check passed: latest run returned `daily:2026-06-10`, history returned one run, and performance exposed paper history, resolved outcomes, calibration, drawdown, and lessons fields.

## Files Changed In This Pass
- `README.md`
- `api/performance.py`
- `api/runs/latest.py`
- `api/runs/history.py`
- `sports_edge/app.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/production_readiness.py`
- `tests/test_pipeline.py`
- `docs/ai/runs/20260610_run_api_alias_contracts.md`

## Next Step
With explicit approval, run the external proof sequence: apply and verify the Postgres migration, validate approved read-only live sources, deploy and smoke-test Vercel, and inspect GitHub Actions scheduled-run logs.
