# Intelligence Pipeline

This project has a temporary MVP intelligence layer that runs after the existing Polymarket ingestion/modeling flow.

The layer is research-only and paper-only. It never places bets, signs orders, reads wallet credentials, or executes exchange actions.

## Operational Rule

Every 15 minutes:

1. Collect/model market data through the existing pipeline.
2. Run deterministic signal detection from market deltas, model outputs, and news metadata.
3. Only in a trusted local environment, optionally call the local Codex CLI for additional JSON commentary.
4. If local Codex is not available, write a compact Codex backfill queue item.
5. Always store a compact structured output.
6. The dashboard reads stored output or a safe server-side deterministic endpoint.

## Commands

Run once:

```bash
npm run intelligence:once
```

Run every 15 minutes locally until stopped:

```bash
npm run intelligence:15m
```

Show queued local Codex backfill work:

```bash
npm run intelligence:queue
```

Drain queued Codex backfills once:

```bash
npm run intelligence:drain-codex-queue
```

Run a local Codex queue worker that checks every minute:

```bash
npm run intelligence:codex-worker
```

Manual Python command:

```bash
python3 -m sports_edge.cli run-intelligence --source fixture --target-count 300 --cycle-type manual --no-codex
```

Scheduler-safe command:

```bash
python3 scripts/run_intelligence_cycle.py --watch --interval-seconds 900 --source fixture
```

## Local Codex Boundary

Local Codex analysis is disabled by default. To enable it locally:

```bash
export ENABLE_LOCAL_CODEX_ANALYSIS=true
export CODEX_ANALYSIS_MODE=local-cli
export CODEX_ANALYSIS_MODEL=gpt-5-codex
npm run intelligence:once
```

Rules:

- Do not commit, copy, print, or move Codex auth files.
- Vercel must not use local Codex auth.
- If Codex CLI is missing, unauthenticated, rate-limited, invalid, or returns non-JSON output, the cycle is marked partial and deterministic fallback remains the source of truth.
- If Codex is unavailable, a durable local queue item is written under `data/generated/intelligence/codex_queue/` when the run is persisted.
- When Codex becomes available locally, `npm run intelligence:drain-codex-queue` or `npm run intelligence:codex-worker` processes pending queue items chronologically.
- No raw prompts or secrets are stored.

## Codex Backfill Queue

The queue exists to preserve the decision sequence when collection/modeling runs while local Codex is not active.

For each persisted cycle with no successful local Codex review, the project writes:

- `data/generated/intelligence/codex_queue/pending/<queue-id>.json`
- `data/generated/intelligence/codex_queue/index.json`

Each item stores only compact, research-only review context:

- cycle id, timestamp, type, source mode, target count;
- input snapshot metadata;
- cycle summary and market ids;
- compact review records for the top markets;
- deterministic model/news/decision/reliability outputs.

The drain command processes pending items in chronological order. Successful reviews move to `processed/`; repeated failures move to `failed/` after the retry limit. This does not place bets, alter wallet state, or create execution instructions.

## Vercel

Vercel has safe endpoints:

- `/api/intelligence` displays the latest generated intelligence JSON bundled with the deployment, or computes a safe fixture fallback if none exists.
- `/api/intelligence-refresh` computes deterministic intelligence server-side without local Codex.
- `/api/cron-refresh` runs the managed scheduler cycle, accepts `source`, `target_count`, `cycle_type`, and `global_review`, and requires `Authorization: Bearer $CRON_SECRET` when `CRON_SECRET` is configured.
- `/api/codex-queue` returns queue summary or attempts a drain in local environments.
- `/api/run-history` returns persisted chronological runs and gap records.
- `/api/model-state` returns online logistic model health.
- `/api/correlation-matrix` returns related-market correlation matrices.

The default production scheduler is GitHub Actions because it can call the deployed endpoint every 15 minutes independent of Vercel Cron plan limits. Configure repository secrets:

- `VERCEL_CRON_URL=https://polymarket-research-dashboard.vercel.app/api/cron-refresh`
- `CRON_SECRET=<same value configured on Vercel>`

Configure Vercel environment variables:

- `CRON_SECRET`
- `DATABASE_URL` or `POSTGRES_URL`

PostgreSQL is the preferred durable state backend. With a database URL set, the cron endpoint creates/uses:

- `pipeline_state` for dashboard-compatible JSON state.
- `collection_runs` for each scheduled/manual run.
- `market_snapshots` for every gathered outcome, newest-first by `published_at`, with gather/decision/resolution timestamps.
- `market_news_items` for attached source reviews and URLs.
- `model_metric_snapshots` for Brier/calibration/model-health checkpoints.

`BLOB_READ_WRITE_TOKEN` is still supported as a fallback JSON mirror, but it does not provide the same queryable bet history.

Local fallback remains available:

```bash
python3 -m sports_edge.cli run-managed-cycle --source fixture --target-count 300
python3 -m sports_edge.cli run-agent-replay
python3 -m sports_edge.cli run-ml-update --global-review
```

Important Vercel limitation: without PostgreSQL, Vercel Blob, or another durable external store, Vercel cannot reliably persist a cross-run queue from serverless functions. In that case the endpoint returns `codexQueue.status = emitted_not_persisted` with a queue item in the JSON response. Configure PostgreSQL for reliable 15-minute run history and dashboard state.

## Storage

Generated files:

- `data/generated/intelligence/latest.json`
- `data/generated/intelligence/analysis_runs.json`
- `data/generated/intelligence/source_snapshots.json`
- `data/generated/intelligence/market_analysis_results.json`
- `data/generated/intelligence/codex_queue/pending/*.json`
- `data/generated/intelligence/codex_queue/processed/*.json`
- `data/generated/intelligence/codex_queue/failed/*.json`

The write is idempotent by cycle id. Scheduled 15-minute cycles use the 15-minute time bucket in the id so reruns update the same cycle instead of creating uncontrolled duplicates.

## Source Reliability

Source config:

`config/news-sources.json`

Reliability tiers:

- Tier 1: official institutions, primary data, regulators, courts, government, exchange/platform official data, audited releases.
- Tier 2: reputable media, established financial/economic outlets, recognized research organizations.
- Tier 3: social media, blogs, aggregators, opinion, unverified community content.

Rules:

- Never invent news, links, claims, probabilities, or model outputs.
- Tier 3 is weak/noisy and cannot be the only basis for a strong conclusion.
- If no reliable source explains a market move, the output says the move is unexplained by current reliable sources.
- Observed data and interpretation are stored separately.

Reliability labels:

- `reliable`: score > 0.8
- `probable/usable with caution`: score between 0.5 and 0.8
- `unreliable/weak`: score < 0.5

## Dashboard Fields

The `Intelligence` page shows:

- last analysis run time;
- status;
- market count;
- average reliability;
- unusual move count;
- local Codex status;
- Codex backfill queue status and pending count;
- decision signals;
- probability history and forecast interval graph;
- current/previous probability, delta, volatility, forecast interval, and deviation;
- source reliability tier badges;
- risk factors and uncertainty notes;
- fallback state.

## MVP Limits

- Fixture mode is the default and is deterministic.
- Hosted Vercel does not persist newly generated results without a database/blob store.
- Local Codex is optional and local-only.
- No automated trading or irreversible action exists.
