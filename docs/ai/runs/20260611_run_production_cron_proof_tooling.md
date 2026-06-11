# 2026-06-11 Run - Production Cron Proof Tooling

## Task
Continue the Polymarket analytical paper-trading goal by making the missing production scheduled-job proof mechanically reproducible from sanitized operator evidence.

## FACT
- Added `sports_edge/proof_capture.py`.
- Added `python3 -m sports_edge.cli production-cron-proof`.
- The new proof command reads an operator-approved sanitized evidence JSON and writes `docs/ai/proofs/20260611_production_cron_run.json` only when validation passes.
- `--dry-run` validates and prints the proof payload without writing a file.
- The proof requires both `scheduledJobs.collector_15m` and `scheduledJobs.sofia_daily`.
- URL query strings and fragments are stripped before proof output.
- No wallet, signing, order execution, raw log fetch, database write, or live API call was added.

## INTERPRETATION
The remaining production cron proof is now less manual and harder to fake accidentally. A push workflow or deployment alone is not accepted as full proof; the audit requires sanitized evidence for both the 15-minute collector and the Sofia daily run.

## GAP
- No approved scheduled production cron proof was captured in this pass.
- `docs/ai/proofs/20260611_production_cron_run.json` remains absent.
- `docs/ai/proofs/20260611_postgres_migration_proof.json` remains absent.
- Live-source parser validation and live resolution proof remain partial until approved network validation is run.

## Validation
- `graphify query "How are goal audit external proof and cron automation wired?"` - passed and confirmed this proof/audit area was the relevant structure.
- `python3 -m unittest tests.test_pipeline.MilestoneOneContractTests.test_production_cron_proof_builder_requires_both_scheduled_jobs tests.test_pipeline.MilestoneOneContractTests.test_cli_production_cron_proof_dry_run_does_not_write tests.test_pipeline.MilestoneOneContractTests.test_cli_production_cron_proof_rejects_incomplete_evidence tests.test_pipeline.MilestoneOneContractTests.test_external_proof_bundle_is_safe_and_secret_free tests.test_pipeline.OutcomeEvaluationTests.test_goal_audit_accepts_valid_production_cron_proof_file` - passed.
- `python3 -m unittest discover -s tests` - passed, 64 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed.
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10` - passed and now lists `production-cron-proof`.
- `python3 -m sports_edge.cli goal-audit` - passed with `complete=false`, 11 proven, 2 partial, and 2 missing.

## Files Changed
- `sports_edge/proof_capture.py`
- `sports_edge/cli.py`
- `sports_edge/external_proof.py`
- `sports_edge/goal_audit.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260611_run_production_cron_proof_tooling.md`
- `docs/ai/vault_bootstrap/wikillm/polymarket/log.md`

## Next Steps
- After durable storage credentials and scheduled job evidence are available, run `python3 -m sports_edge.cli production-cron-proof --evidence-in <sanitized-cron-evidence.json> --proof-out docs/ai/proofs/20260611_production_cron_run.json`.
- Keep Postgres migration proof gated behind approved durable database credentials.
