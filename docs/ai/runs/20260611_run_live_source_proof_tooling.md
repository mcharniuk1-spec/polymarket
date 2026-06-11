# 2026-06-11 Run - Live Source Proof Tooling

## Task
Continue the Polymarket analytical paper-trading goal by adding a sanitized proof path for approved live-source validation.

## FACT
- Added `python3 -m sports_edge.cli live-source-proof`.
- Added live-source proof builders and validators to `sports_edge/proof_capture.py`.
- Added `docs/ai/proofs/20260611_live_source_validation.json` as the audit proof path.
- `goal-audit` can now move `live_official_adapters` and `live_resolution_proof` from partial to proven when a valid approved live-source proof file exists.
- The proof requires the three active sections: `macroeconomics`, `politics`, and `stocks_trade`.
- The proof stores validation counts and booleans, not raw source payloads, credentials, cookies, or logs.
- No live API call, wallet, signing, order execution, or durable database write was added.

## INTERPRETATION
The system now has a mechanical acceptance path for approved live-source evidence instead of leaving live adapter and resolution validation permanently partial. The audit remains incomplete until real approved evidence is captured.

## GAP
- `docs/ai/proofs/20260611_live_source_validation.json` remains absent.
- `docs/ai/proofs/20260611_postgres_migration_proof.json` remains absent.
- `docs/ai/proofs/20260611_production_cron_run.json` remains absent.

## Validation
- `python3 -m unittest tests.test_pipeline.MilestoneOneContractTests.test_live_source_proof_builder_requires_all_active_categories tests.test_pipeline.MilestoneOneContractTests.test_cli_live_source_proof_dry_run_does_not_write tests.test_pipeline.MilestoneOneContractTests.test_cli_live_source_proof_rejects_missing_parser_evidence tests.test_pipeline.MilestoneOneContractTests.test_external_proof_bundle_is_safe_and_secret_free tests.test_pipeline.OutcomeEvaluationTests.test_goal_audit_accepts_valid_live_source_proof_file` - passed.
- `python3 -m unittest discover -s tests` - passed, 68 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed.
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10` - passed and now lists `live-source-proof`.
- `python3 -m sports_edge.cli goal-audit` - passed with `complete=false`, 11 proven, 2 partial, and 2 missing.

## Files Changed
- `sports_edge/proof_capture.py`
- `sports_edge/cli.py`
- `sports_edge/external_proof.py`
- `sports_edge/goal_audit.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260611_run_live_source_proof_tooling.md`
- `docs/ai/vault_bootstrap/wikillm/polymarket/log.md`

## Next Steps
- Run approved read-only live validation and create sanitized evidence for `live-source-proof`.
- Keep durable Postgres migration and production cron proof gated behind explicit approval and credentials.
