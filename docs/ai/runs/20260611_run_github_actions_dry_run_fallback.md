# 2026-06-11 Run - GitHub Actions Dry-Run Fallback

## Task
Continue the Polymarket paper-analytics goal by inspecting external automation status and fixing any reliability gap that can be handled without real-money trading, wallet actions, credential exposure, or destructive operations.

## FACT
- Public GitHub Actions API showed the latest pushed workflow runs for `Polymarket 15m Research Cycle` completed with `conclusion=failure`.
- The latest observed push run `27326159451` failed in the `Run managed research cycle` step before validation.
- The unauthenticated GitHub logs endpoint returned HTTP 403, so raw step logs were not fetched.
- Vercel CLI showed the production deployment `dpl_AYkk3aKjqzUUbfLda1J3A7qNoZnL` is ready and includes the cron functions.
- Vercel logs showed only manual smoke traffic during this check, not an authenticated scheduled cron invocation.
- The workflow was updated so scheduled jobs still fail closed without durable storage, while push/manual runs without durable storage execute a fixture dry-run proof.
- Production-readiness now has an explicit `non_scheduled_dry_run_fallback` check.

## INTERPRETATION
The previous workflow design was too strict for push-triggered CI: it required durable production storage before it could run any safe contract proof. That made normal pushes fail even when the code was otherwise healthy. The new behavior preserves the production safety boundary while allowing source-control automation to prove the paper-only contract.

## GAP
- This does not prove a successful scheduled production job yet. That still requires a post-fix GitHub Actions schedule or Vercel cron log with durable storage configured.
- Postgres migration proof remains missing because no approved database URL is configured locally.
- Live official-source parsing remains partial until approved public endpoints or licensed providers are validated.

## Validation
- `python3 -m unittest tests.test_pipeline.MilestoneOneContractTests.test_github_workflow_runs_contract_collector_and_sofia_daily tests.test_pipeline.MilestoneOneContractTests.test_production_readiness_contract_validates_local_deploy_surface` - passed.
- `python3 -m unittest discover -s tests` - passed, 57 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed, including `non_scheduled_dry_run_fallback`.
- `python3 -m sports_edge.cli goal-audit` - passed with `complete=false`, 11 proven, 2 partial, 2 missing.
- Post-push public GitHub Actions run `27326320766` for commit `3b92b18` completed successfully.
- Public job metadata for job `80728152175` showed `Validate source registry`, `Run managed research cycle`, `Validate managed cycle result`, and `Vercel dashboard smoke check` all succeeded.

## Files Changed
- `.github/workflows/polymarket-15m.yml`
- `sports_edge/production_readiness.py`
- `tests/test_pipeline.py`
- `docs/ai/proofs/20260611_github_actions_public_status.json`
- `docs/ai/runs/20260611_run_github_actions_dry_run_fallback.md`
- `docs/ai/vault_bootstrap/wikillm/polymarket/log.md`

## Next Steps
- Configure approved durable storage secrets before expecting scheduled production runs to succeed.
- After a scheduled run fires, capture the cron run evidence and rerun `python3 -m sports_edge.cli goal-audit`.
