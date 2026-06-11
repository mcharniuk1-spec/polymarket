# 2026-06-10 Run - Runtime Scope Tightening

## Task
Continue the Polymarket analytical-system goal by removing runtime dashboard/API exposure of legacy sports backtest data, while preserving paper-only safety and internal regression coverage.

## FACT
- `sports_edge.dashboard_data.build_dashboard_payload()` no longer runs `Backtester`, `OddsIngestion`, or `OddsMovementAnalyzer`.
- Root dashboard payloads now expose only the Polymarket multi-agent payload plus scoped empty compatibility fields for `forecasts`, `trades`, and `odds_history`.
- Local legacy routes `/api/summary`, `/api/forecasts`, `/api/performance`, and `/api/odds-history` return explicit `legacySportsDisabled: true` compatibility payloads.
- `/api/report` now serves the Polymarket multi-agent report text instead of the legacy historical performance report.
- The visible dashboard no longer has the `Fixture Backtest` / sports page or sports render functions.
- `production-readiness` now includes `runtime_scope_boundary`, checking visible dashboard markers, scoped dashboard payload behavior, and disabled legacy route semantics.

## INTERPRETATION
The runtime dashboard and API are now more faithful to the active goal: macroeconomics, politics, and stocks/trade only. Legacy sports modules remain in the repo for historical regression tests, but are no longer first-class runtime dashboard surfaces.

## GAP
- This pass did not apply the real Postgres migration, deploy to Vercel, inspect production cron logs, or validate live external sources. `goal-audit` correctly remains incomplete.
- Local `/api/health` responded during smoke testing, but subsequent loopback curls to `/api/all` were unreliable in the sandbox even while the server session remained attached. The shared route payload functions are covered by direct checks and tests.

## Validation
- `python3 -m unittest discover -s tests` - passed, 52 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed, including `runtime_scope_boundary`.
- `python3 -m sports_edge.cli migrate --dry-run` - passed, 13 tables and 6 indexes reported.
- `python3 -m sports_edge.cli goal-audit` - passed, complete remains `false`; 10 proven, 2 partial, 3 missing.
- Fixture collector, daily, and managed-cycle dry-run summaries all passed with `storageWritten: false`.
- Direct scoped payload check passed: active sections are macroeconomics, politics, and stocks/trade; root forecasts/trades/odds history are zero; legacy forecast route payload is disabled.

## Files Changed In This Pass
- `README.md`
- `sports_edge/app.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/dashboard_data.py`
- `sports_edge/production_readiness.py`
- `tests/test_pipeline.py`
- `web/app.js`
- `web/index.html`
- `docs/ai/runs/20260610_run_runtime_scope_tightening.md`

## Next Step
With explicit approval, run the remaining external proof sequence: apply Postgres migrations and verify durable writes, validate approved read-only live sources, deploy/smoke-test Vercel, and inspect scheduled GitHub Actions logs.
