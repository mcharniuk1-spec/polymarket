# 2026-06-11 Run: Vercel Blob Limit Mitigation

## Task

Mitigate Vercel Blob free-tier transfer exhaustion without global re-setup, without deleting remote storage, and without disrupting other Vercel projects.

## Inputs

- User-provided screenshot: Vercel Blob Data Transfer used 100% of the 10 GB free-tier allowance and warns that store access will be paused for 30 days.
- Vercel account/project inspection through authenticated local Vercel CLI.
- Existing Polymarket repo deployment and storage code.

## Findings

FACT: The Vercel account has three visible projects: `polymarket-research-dashboard`, `siberia-site`, and `archflow`.

FACT: Public smoke checks returned HTTP 200 for:

- `https://polymarket-research-dashboard.vercel.app/`
- `https://polymarket-research-dashboard.vercel.app/api/health`
- `https://siberia-site.vercel.app/`
- `https://archflow-phi-jade.vercel.app/`

FACT: Vercel production env names for Polymarket include `CRON_SECRET` and `BLOB_READ_WRITE_TOKEN`, but no Postgres URL.

FACT: Before this change, `BLOB_READ_WRITE_TOKEN` alone caused the app to treat Vercel Blob as durable storage and `JsonStateStore` attempted Blob reads/writes automatically.

FACT: Local generated artifacts remain on disk. Large generated runtime files were excluded from future Vercel deployments rather than deleted.

## Changes

- Made Vercel Blob storage opt-in through `POLYMARKET_ENABLE_BLOB=1`.
- Added `blob_storage_enabled()` and `durable_storage_configured()` helpers.
- Updated health and cron routes so Blob tokens alone no longer count as durable storage.
- Updated GitHub Actions scheduled durable checks to use deployed cron auth or Postgres only, not Blob.
- Excluded heavy generated runtime artifacts and reports from Vercel deployments through `.vercelignore` and function `excludeFiles`.
- Updated README and intelligence pipeline docs.
- Added tests proving Blob token alone does not enable Blob or durable storage.

## Validation

```bash
python3 -m unittest discover -s tests
python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py
node --check web/app.js
python3 -m sports_edge.cli production-readiness
python3 -c 'import json, os; os.environ.clear(); os.environ.update({"BLOB_READ_WRITE_TOKEN":"masked-test-token"}); from sports_edge.app import health_payload; print(json.dumps(health_payload(), sort_keys=True))'
```

All checks passed locally before deployment.

## Status

INTERPRETATION: The Polymarket deployment can remain available without consuming more Vercel Blob transfer by default. Scheduled durable writes now require Postgres or an explicitly approved Blob opt-in after the limit issue is resolved.

GAP: This does not unpause or reset the Vercel Blob store. Only Vercel billing/usage reset, upgrade, or approved remote Blob cleanup can change the account-level Blob pause state.

## Next Steps

- Deploy the mitigation to production.
- Smoke-check Polymarket, Siberia Site, and Archflow after deployment.
- Add a Postgres production store before re-enabling scheduled durable writes.
