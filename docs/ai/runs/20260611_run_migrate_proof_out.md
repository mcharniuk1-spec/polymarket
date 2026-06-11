# 2026-06-11 Run - Migrate Proof Output

## Task
Continue the Polymarket analytical paper-trading goal by making approved Postgres migration proof generation automatic and secret-safe.

## FACT
- `python3 -m sports_edge.cli migrate` now accepts `--proof-out <path>`.
- `--proof-out` writes a sanitized Postgres migration proof only after a real non-dry-run migration succeeds.
- `migrate --dry-run --proof-out ...` does not write a proof file and reports `proof.written=false`.
- The external proof bundle now lists the approved Postgres command as `python3 -m sports_edge.cli migrate --proof-out docs/ai/proofs/20260611_postgres_migration_proof.json`.
- No wallet, signing, order execution, or live-trading path was added.

## INTERPRETATION
The remaining database proof is now operator-executable without hand-building JSON. This reduces proof drift and secret-leak risk while keeping the goal audit incomplete until real durable evidence exists.

## GAP
- No real Postgres migration was run in this pass.
- `docs/ai/proofs/20260611_postgres_migration_proof.json` remains absent until approved durable database credentials are available.
- Production scheduled cron proof remains absent.

## Validation
- `python3 -m unittest tests.test_pipeline.MilestoneOneContractTests.test_cli_migration_apply_uses_postgres_store_without_printing_database_url tests.test_pipeline.MilestoneOneContractTests.test_cli_migration_apply_can_write_sanitized_postgres_proof tests.test_pipeline.MilestoneOneContractTests.test_cli_migration_dry_run_with_proof_out_does_not_write_proof tests.test_pipeline.MilestoneOneContractTests.test_external_proof_bundle_is_safe_and_secret_free` - passed.
- `python3 -m sports_edge.cli migrate --dry-run --proof-out docs/ai/proofs/20260611_postgres_migration_proof.json` - passed; proof not written.
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10` - passed and included the new approved command.
- `python3 -m unittest discover -s tests` - passed, 61 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed.
- `python3 -m sports_edge.cli goal-audit` - passed; `complete=false` with durable Postgres and production scheduled cron proof still missing.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` - passed.

## Files Changed
- `sports_edge/cli.py`
- `sports_edge/external_proof.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260611_run_migrate_proof_out.md`
- `docs/ai/vault_bootstrap/wikillm/polymarket/log.md`

## Next Steps
- Run the approved Postgres migration with `--proof-out` only after durable database credentials and write approval are available.
- Capture scheduled production cron proof after a real scheduled run succeeds.
