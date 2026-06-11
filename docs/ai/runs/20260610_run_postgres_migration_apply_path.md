# 2026-06-10 Run - Postgres Migration Apply Path

## Task
Improve the remaining database-proof gap by making `python3 -m sports_edge.cli migrate` explicitly apply and verify the Postgres schema when an approved database URL is configured.

## FACT
- `PostgresStateStore.apply_schema_migration()` now applies migration SQL, records a `schema_migrations` row, verifies required tables through `information_schema`, and masks configured database URLs in errors.
- `python3 -m sports_edge.cli migrate --dry-run` remains credential-free and write-free.
- `python3 -m sports_edge.cli migrate` still requires an approved `DATABASE_URL` or `POSTGRES_URL`; it was not run against a real database in this pass.

## INTERPRETATION
The repo is closer to the full database requirement because migration application is now a first-class, test-covered operation rather than an indirect side effect of writing state.

## GAP
The goal audit must still mark Postgres application proof missing until the real migration command is run in an approved environment and durable writes are verified.

## Validation
- `python3 -m unittest discover -s tests` - passed, 45 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli migrate --dry-run` - passed.
- `python3 -m sports_edge.cli goal-audit` - passed, complete remains false by design.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` - passed.
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` - passed.
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` - passed.

## Files Changed In This Pass
- `sports_edge/state_store.py`
- `sports_edge/cli.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260610_run_postgres_migration_apply_path.md`

## Next Step
Use an approved database URL to run `python3 -m sports_edge.cli migrate`, then run a fixture daily cycle with Postgres storage enabled to prove durable writes and update the goal audit evidence.
