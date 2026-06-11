# 2026-06-11 Run - Post-Push Deploy And Cron Status

## Task
Verify the latest pushed durable daily proof gate, deployed dashboard, and cron automation status after commit `c43b55b`.

## Inputs
- Latest source commit: `c43b55b` (`Add durable daily proof gate`).
- Production URL: `https://polymarket-research-dashboard.vercel.app`.
- Scope: research-only Polymarket analytics and paper trading for macroeconomics, politics, and stocks/trade markets.

## Outputs
FACT: GitHub Actions run `27328297778` for commit `c43b55b` completed successfully.

FACT: Vercel production deployment `dpl_8gVBvoNhvFVxaUVvHWkeZ9t3h7ja` is ready and aliased to `https://polymarket-research-dashboard.vercel.app`.

FACT: Deployed functions include `api/cron-collector`, `api/cron-daily`, and `api/cron-refresh`.

FACT: Production smoke checks returned homepage `HTTP 200`, `/api/health` `HTTP 200` with `research_only=true`, durable storage configured, and cron secret configured; unauthenticated `/api/cron-daily` returned `HTTP 401`.

INTERPRETATION: Website deployment and cron route wiring are operational, and cron routes fail closed without authorization.

GAP: The goal remains incomplete until approved external proof files exist for Postgres migration application, duplicate-safe durable daily writes, approved live-source validation, and production scheduled cron evidence.

## Commands / Checks
- `git status --short`
- `git rev-parse HEAD`
- `git log -1 --oneline`
- `curl --max-time 20 -sS https://api.github.com/repos/mcharniuk1-spec/polymarket/actions/runs?branch=main&per_page=3`
- `npx vercel ls polymarket-research-dashboard`
- `npx vercel inspect https://polymarket-research-dashboard-k06nkw1hy.vercel.app`
- `npx vercel deploy --prod --yes`
- `npx vercel inspect https://polymarket-research-dashboard-i1uzba62a.vercel.app`
- `curl --max-time 20 -i -sS https://polymarket-research-dashboard.vercel.app/api/health`
- `curl --max-time 20 -i -sS https://polymarket-research-dashboard.vercel.app/api/cron-daily`
- `curl --max-time 20 -I -sS https://polymarket-research-dashboard.vercel.app/`
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10`
- `python3 -m sports_edge.cli goal-audit`
- `python3 -m sports_edge.cli production-readiness`

## Status
Completed for CI/deployment smoke verification and production redeploy. Overall goal remains externally incomplete by design.

## Next Steps
1. Run approved Postgres migration proof when durable database credentials are available.
2. Run approved non-dry-run fixture daily write and duplicate rerun, then create `docs/ai/proofs/20260611_durable_daily_write.json`.
3. Run approved read-only live-source validation and create `docs/ai/proofs/20260611_live_source_validation.json`.
4. Capture sanitized scheduled collector and Sofia daily evidence, then create `docs/ai/proofs/20260611_production_cron_run.json`.
