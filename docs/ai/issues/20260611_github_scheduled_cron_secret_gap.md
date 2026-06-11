# Issue - GitHub Scheduled Cron Secret Gap

## Status
Open.

## Context
The workflow update in commit `5823fc5` routes scheduled jobs through deployed Vercel cron endpoints when GitHub Actions has `CRON_SECRET` and `VERCEL_CRON_URL`, with local durable execution as a fallback.

## Evidence
FACT: Push CI for commit `5823fc5` succeeded in GitHub Actions run `27328854658`.

FACT: A scheduled run on commit `5823fc5` started at `2026-06-11T06:41:33Z` and failed in GitHub Actions run `27328905704`.

FACT: Public job metadata shows the failure occurred in the `Run managed research cycle` step.

FACT: Public job-log download returned `403` because the local GitHub CLI is not authenticated and the API requires repository admin rights for logs.

FACT: `gh auth status` reports no authenticated GitHub host.

INTERPRETATION: The likely blocker is missing GitHub Actions `CRON_SECRET`/`VERCEL_CRON_URL` or local durable storage secrets for scheduled runs. This cannot be confirmed from public metadata alone.

## Impact
The 15-minute scheduled collector cannot be proven in production, so `docs/ai/proofs/20260611_production_cron_run.json` must remain missing and the overall goal remains incomplete.

## Required Operator Action
1. Add GitHub Actions secret `CRON_SECRET` matching the Vercel production `CRON_SECRET`.
2. Add GitHub Actions secret `VERCEL_CRON_URL` as `https://polymarket-research-dashboard.vercel.app`.
3. Alternatively, add approved GitHub Actions durable storage secrets for local scheduled execution.
4. Re-run or wait for the next scheduled workflow.
5. Capture sanitized scheduled evidence and generate `docs/ai/proofs/20260611_production_cron_run.json`.

## Safety Notes
Do not store the secret value in git, logs, notes, proof files, or chat. Use GitHub/Vercel native secret storage only.
