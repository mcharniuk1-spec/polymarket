# 2026-06-11 Run - Remote Cron Workflow Fallback

## Task
Improve scheduled automation reliability for the research-only Polymarket paper-trading system after public GitHub scheduled runs showed failures on the older local durable-storage path.

## Inputs
- Current goal audit: 11 proven, 2 partial, 3 missing.
- Public scheduled GitHub Actions runs: latest visible scheduled runs were failing on an older commit.
- Production Vercel health: durable storage and cron secret were configured in production.

## Outputs
FACT: The GitHub Actions workflow now prefers authenticated calls to deployed Vercel cron endpoints for scheduled jobs:
- `*/15 * * * *` calls `/api/cron-collector?source=live`.
- `0 6 * * *` and `0 7 * * *` call `/api/cron-daily?source=live`.

FACT: The workflow keeps local durable execution as a fallback when GitHub has database/blob durable storage secrets.

FACT: Scheduled runs fail closed when neither deployed cron auth nor local durable storage is configured.

FACT: Push/manual CI still uses the fixture dry-run proof path when durable storage is absent.

INTERPRETATION: This reduces GitHub secret blast radius because the 15-minute scheduler can use Vercel's deployed durable environment through `CRON_SECRET` instead of requiring database credentials in GitHub Actions.

GAP: Production cron proof is still missing until a real scheduled run on the updated workflow succeeds and sanitized evidence is written to `docs/ai/proofs/20260611_production_cron_run.json`.

GAP: The first observed scheduled run after this update, GitHub Actions run `27328905704`, failed in the `Run managed research cycle` step. Public metadata does not expose enough detail to prove the exact cause, and local `gh auth status` shows no authenticated GitHub host for admin log access.

## Commands / Checks
- `python3 -m unittest tests.test_pipeline.MilestoneOneContractTests.test_github_workflow_runs_contract_collector_and_sofia_daily tests.test_pipeline.MilestoneOneContractTests.test_production_readiness_contract_validates_local_deploy_surface`
- `python3 -m sports_edge.cli production-readiness`
- `python3 -m py_compile sports_edge/production_readiness.py`
- `python3 -m unittest discover -s tests`
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py`
- `node --check web/app.js`
- `python3 -m json.tool config/news-sources.json`
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10`
- `python3 -m sports_edge.cli goal-audit`
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run`
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run`
- `curl --max-time 20 -sS https://api.github.com/repos/mcharniuk1-spec/polymarket/actions/runs?event=schedule&branch=main&per_page=5`
- `curl --max-time 20 -sS https://api.github.com/repos/mcharniuk1-spec/polymarket/actions/runs/27328905704/jobs`
- `gh auth status`

## Status
Completed locally and pushed as commit `5823fc5`. Push CI succeeded; scheduled production proof remains blocked by a failed scheduled run that likely needs GitHub Actions secret/config access.

## Next Steps
1. Add or verify GitHub Actions `CRON_SECRET` and `VERCEL_CRON_URL`, or provide authenticated GitHub access to inspect scheduled-run logs.
2. Re-run or wait for the next scheduled run after secrets are confirmed.
3. If scheduled collector and Sofia daily evidence both pass with `sourceMode=live`, generate production cron proof.
