# 2026-06-10 Run - Production Readiness And Scoped API

## Task
Close the local implementation pass as far as possible without deployment, real database writes, live API calls, credentials, wallet actions, signing, or order execution.

## FACT
- Scheduled automation now declares a 15-minute read-only live collector and daily read-only live analytical run at Sofia 09:00 UTC-equivalent windows.
- `sports_edge.production_readiness` and `python3 -m sports_edge.cli production-readiness` now verify workflow shape, Sofia daily windows, durable-storage gating, dashboard route presence, and health/cron safety signals.
- Persisted live daily runs are allowed in code when configured, while dry-run mode remains fixture-first and write-free.
- `/api/all` now uses a scoped compatibility payload: root-level legacy sports forecasts, trades, and odds history are disabled, while the Polymarket multi-agent payload remains available for the three active sections.
- The system remains research-only and paper-trading-only. No wallet, signing, order execution, or real-money trading path was added.

## INTERPRETATION
The local repo now covers the requested analytical architecture and operational contract at code, schema, tests, dry-run, and dashboard-API levels. The remaining gaps are external proof gaps, not local implementation gaps.

## GAP
- No real Postgres migration was applied because that would require approved database credentials and durable writes.
- No GitHub Actions or Vercel production run was executed or inspected.
- No public Vercel dashboard URL was deployed or smoke-tested.
- No live external-source parser validation was run because network/source validation was not approved in this pass.

## Validation
- `python3 -m unittest discover -s tests` - passed, 50 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed, all checks `pass`, deployed remains `false`.
- `python3 -m sports_edge.cli migrate --dry-run` - passed, 13 tables and 6 indexes reported.
- `python3 -m sports_edge.cli goal-audit` - passed, complete remains `false`; 10 proven, 2 partial, 3 missing.
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` - passed; 3 market snapshots; no storage writes.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` - passed; 5 context reports, 21 model outputs, 3 decisions, schema validation OK; no storage writes.
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` - passed; 30 candidates, 6 paper bets, no storage writes.
- `python3 -c '... load_scoped_compat_dashboard ...'` - passed; active sections are macroeconomics, politics, and stocks/trade; root forecasts/trades/odds history are all zero.
- Local `python3 -m sports_edge.app --host 127.0.0.1 --port 8765` served `/api/health` with research-only safety flags. A follow-up `/api/all` curl was unreliable in the sandbox, so the shared `/api/all` helper was verified directly.

## Files Changed In This Pass
- `.github/workflows/polymarket-15m.yml`
- `api/all.py`
- `sports_edge/app.py`
- `sports_edge/cli.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/orchestrator.py`
- `sports_edge/production_readiness.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260610_run_production_readiness_scoped_api.md`

## Next Step
With explicit approval, apply the Postgres migration in the real durable environment, run an approved read-only live-source validation, deploy/smoke-test Vercel, and inspect the first scheduled GitHub Actions run logs.
