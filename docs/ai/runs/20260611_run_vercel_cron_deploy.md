# 2026-06-11 Run - Vercel Cron Deploy And Scope Hardening

## Task
Run the external proof bundle, update/deploy the website, add deployable cron automation, and verify the production dashboard without enabling wallet actions, order execution, or real-money betting.

## FACT
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10` ran successfully and reported the expected approval-gated proof sequence.
- Vercel production deployment succeeded at `https://polymarket-research-dashboard.vercel.app`.
- Vercel Hobby rejected `*/15 * * * *`, so the 15-minute collector remains on GitHub Actions. Vercel daily cron is configured for `/api/cron-daily` at `0 6 * * *` and `0 7 * * *`.
- Vercel Hobby also rejected more than 12 serverless functions. `.vercelignore` now limits the deployable function surface to 12 while preserving source files locally.
- A random production `CRON_SECRET` was added through Vercel CLI without printing or storing its value.
- Final smoke checks returned: root 200, `/api/health` 200 with `cron_secret_configured=true`, `/api/dashboard-contract` 200, `/api/runs/latest` 200, and unauthenticated `/api/cron-daily` 401.
- Scoped milestone commit `989f668` was pushed to `origin/main`, so the updated GitHub Actions workflow and dashboard/API code are available remotely.
- A live durable daily run existed in Vercel Blob with `sourceMode=live`, `status=success`, `paperTradingOnly=true`, and zero paper bets.
- The live run exposed stale out-of-scope sports spread markets. `DataAgent` and `dashboard_api` were hardened so sports-like text such as `Spread: Golden State Valkyries (-7.5)` is rejected/filtered even if stale stored category labels say politics.

## INTERPRETATION
The website and deployable Vercel daily automation are live. The dashboard is now safer than the stored state because it filters out stale out-of-scope markets before rendering candidates, decisions, and model outputs.

## GAP
- Local `goal-audit` remains incomplete by design because Postgres migration proof is not available locally and GitHub scheduled-run logs were not inspected in this run.
- Vercel durable storage is configured through Blob, but the planned Postgres migration was not applied because no local database URL is configured.
- Live official-source validation is partial: public probes ran, but BLS/SEC returned 403 and politics produced source-health-only evidence, not parser-verified decision evidence.
- The next authenticated Vercel daily cron run should produce a fresh post-filter live run; unauthenticated manual cron calls are now correctly rejected.
- GitHub Actions scheduled-run proof could not be inspected from this shell because `gh` is not authenticated.

## Validation
- `python3 -m unittest discover -s tests` - passed, 57 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `python3 -m json.tool vercel.json` - passed.
- `python3 -m sports_edge.cli production-readiness` - passed, 11 checks.
- `python3 -m sports_edge.cli goal-audit` - passed with `complete=false`, 11 proven, 2 partial, 2 missing.
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10` - passed.
- Production smoke: `/`, `/api/health`, `/api/dashboard-contract`, and `/api/runs/latest` returned 200.
- Production cron safety: unauthenticated `/api/cron-daily` returned 401.
- Post-push production smoke: `/` returned 200, `/api/health` returned `ok=true`, `/api/dashboard-contract` returned `paperTradingOnly=true`, and unauthenticated `/api/cron-daily` returned 401.
- Dashboard stale-scope smoke: deployed dashboard contract contains no `golden state` or `valkyries` text and reports filtering 2 out-of-scope stored markets.
- `gh run list --limit 10 --json ...` - not verified because GitHub CLI is not authenticated in this environment.

## Files Changed
- `.vercelignore`
- `vercel.json`
- `api/cron-collector.py`
- `api/cron-daily.py`
- `sports_edge/app.py`
- `sports_edge/data_agent.py`
- `sports_edge/dashboard_api.py`
- `sports_edge/production_readiness.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260611_run_vercel_cron_deploy.md`
- `docs/ai/vault_bootstrap/wikillm/polymarket/log.md`

## Next Steps
- Inspect the next scheduled Vercel daily cron log after 06:00 or 07:00 UTC and confirm it writes a fresh scoped run.
- Configure/approve Postgres if Postgres is still required as the primary source of truth; then run `python3 -m sports_edge.cli migrate`.
- Inspect GitHub Actions scheduled logs for the 15-minute collector once these changes are committed and pushed.
