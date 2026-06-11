# 2026-06-11 Run - Vercel Production Redeploy

## Task
Deploy the Polymarket research dashboard/API after the migration proof-output update and verify the automation surface without running approval-gated database writes.

## FACT
- Commit `d0fdc20b3dbb31501f65e2e21a3beb0b1534b7e6` was pushed to `origin/main`.
- GitHub Actions run `27327357076` for `d0fdc20` completed with conclusion `success`.
- `npx vercel deploy --prod -y` completed successfully.
- Production deployment id: `dpl_FgJp9cAwu9TGAorsJyhLxEAUhGjD`.
- Production URL: `https://polymarket-research-dashboard-k06nkw1hy.vercel.app`.
- Canonical alias: `https://polymarket-research-dashboard.vercel.app`.
- `npx vercel inspect polymarket-research-dashboard-k06nkw1hy.vercel.app` reported status `Ready` and listed API functions including `api/cron-collector`, `api/cron-daily`, `api/cron-refresh`, and `api/dashboard-contract`.
- `vercel.json` contains cron entries for `/api/cron-daily` at `0 6 * * *` and `0 7 * * *`.
- `.github/workflows/polymarket-15m.yml` contains the 15-minute collector schedule plus the 06:00/07:00 UTC daily windows.

## INTERPRETATION
The dashboard/API and cron function surface have been redeployed to production. This proves deployment readiness, but it does not by itself prove a scheduled production cron has executed with durable storage.

## GAP
- No approved Postgres migration was run.
- `docs/ai/proofs/20260611_postgres_migration_proof.json` remains absent.
- `docs/ai/proofs/20260611_production_cron_run.json` remains absent until a real scheduled job succeeds and sanitized evidence is captured.

## Validation
- `python3 -m sports_edge.cli external-proof-bundle --as-of 2026-06-10` - passed; still lists the external proof sequence as approval-required.
- `python3 -m sports_edge.cli goal-audit` - passed with `complete=false`, 11 proven, 2 partial, and 2 missing.
- `npx vercel inspect polymarket-research-dashboard-k06nkw1hy.vercel.app` - passed; deployment status `Ready`.

## Next Steps
- Run the approved Postgres migration command only when durable database credentials and write approval are ready.
- Capture sanitized scheduled-run proof after the production cron executes successfully.
