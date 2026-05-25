---
title: Vercel Dashboard Deploy
date: 2026-05-25
project: polymarket
status: completed
research_only: true
---

# Vercel Dashboard Deploy

## Task

Set up the Polymarket research-only dashboard so it can run locally and be reachable through Vercel, with a 15-minute refresh posture where the hosting account permits it.

## Outputs

- Added Vercel-compatible Python API functions under `api/`.
- Added shared serverless dashboard payload generation in `sports_edge/dashboard_data.py`.
- Added Vercel response helpers in `sports_edge/vercel_api.py`.
- Added `vercel.json` routing for the static dashboard, API functions, security headers, and favicon routing.
- Added `package.json` so Vercel has a stable lowercase project name.
- Added browser auto-refresh in `web/app.js` at 900 seconds.
- Deployed production dashboard:
  - Stable URL: https://polymarket-research-dashboard.vercel.app/
  - Deployment URL: https://polymarket-research-dashboard-7ifx6m5mv.vercel.app/

## Refresh Setup

- Local mode: `python3 -m sports_edge.app --host 127.0.0.1 --port 8766`
- Vercel mode: request-time serverless APIs with 900-second CDN cache headers and browser auto-refresh every 15 minutes while the page is open.
- Manual refresh endpoint: `/api/refresh`
- Scheduler-ready endpoint: `/api/cron-refresh`

## Constraint

Vercel rejected `*/15 * * * *` cron on the current Hobby account because Hobby accounts only allow daily cron frequency. True unattended 15-minute Vercel cron requires a Pro plan or an external scheduler calling `/api/cron-refresh`.

## Verification

- `python3 -m json.tool vercel.json`
- `python3 -m json.tool package.json`
- `python3 -m py_compile sports_edge/*.py api/*.py`
- `python3 -m unittest discover -s tests`
- `node --check web/app.js`
- Local API smoke: `http://127.0.0.1:8766/api/summary`
- Production page smoke: `https://polymarket-research-dashboard.vercel.app/`
- Production API smoke: `/api/summary`, `/api/cron-refresh`
- Browser snapshot verified deployed dashboard title and top-level UI with no console errors after favicon fix.

## Safety

The deployment remains research-only and paper-only. It does not implement wallet actions, real-money betting, automated order execution, credential storage, or exchange trading execution.

## Next Steps

- If 15-minute unattended refresh is required on Vercel itself, upgrade the Vercel project to Pro and restore this cron block:

```json
"crons": [
  {
    "path": "/api/cron-refresh",
    "schedule": "*/15 * * * *"
  }
]
```

- Alternatively, configure an external scheduler to call `https://polymarket-research-dashboard.vercel.app/api/cron-refresh` every 15 minutes.
