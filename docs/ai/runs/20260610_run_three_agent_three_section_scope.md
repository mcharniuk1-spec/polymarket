# Run: Three-Agent Three-Section Scope Alignment

Date: 2026-06-10

## Task

Align the Polymarket research system with the active goal: paper trading only, three user-facing agents, and active analytical sections limited to macroeconomics, politics, and stocks/trade-related markets.

## Inputs

- `AGENTS.md`
- `docs/ai/PROJECT_GOAL.md`
- `docs/ai/NEXUS_OBSIDIAN_GRAPHIFY.md`
- Existing Graphify report and current repo implementation
- User goal text for the Prediction Market Analytical System

## Outputs

FACT: Added `sports_edge/research_scope.py` as the shared scope contract for active sections, aliases, the three-agent contract, safety flags, and reliability-label thresholds.

FACT: Updated the multi-agent pipeline, full-scan classifier, source registry, intelligence labels, external readiness, dashboard UI, tests, and docs to use macroeconomics, politics, and stocks/trade.

FACT: Live/full-scan market classification now rejects out-of-scope sports, crypto, weather, culture, and unknown categories before candidate creation.

FACT: `/api/all` now ignores stale persisted dashboard snapshots that contain out-of-scope categories, so old full-scan artifacts do not override the active fixture dashboard.

INTERPRETATION: The system is now scoped as an evidence and paper-risk console for the three requested market sections, while retaining internal helper models for odds, context, section rules, and evaluation.

## Files Changed

- `AGENTS.md`
- `README.md`
- `config/news-sources.json`
- `docs/ai/PROJECT_GOAL.md`
- `sports_edge/agents.py`
- `sports_edge/bet_research.py`
- `sports_edge/dashboard_enrichment.py`
- `sports_edge/external_sources.py`
- `sports_edge/full_scan.py`
- `sports_edge/intelligence.py`
- `sports_edge/managed_pipeline.py`
- `sports_edge/research_scope.py`
- `sports_edge/source_registry.py`
- `tests/test_pipeline.py`
- `web/app.js`
- `web/index.html`

## Checks

- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` passed.
- `node --check web/app.js` passed.
- `python3 -m json.tool config/news-sources.json >/tmp/polymarket-news-sources-check.json` passed.
- `python3 -m unittest discover -s tests` passed: 17 tests.
- Fixture dry run confirmed 30 candidates, three active sections, three-agent contract, and paper-only mode.
- Browser smoke test at `http://127.0.0.1:8765/?qa=three-agent-v2` passed with no console warnings/errors.

## Blockers And Gaps

GAP: The external WikiLLM path `/Users/getapple/Documents/getapple/core/wiki/projects/polymarket` is outside the writable sandbox for this run, so durable memory was recorded repo-locally under `docs/ai/runs/` instead.

GAP: Existing stale generated artifacts under `data/generated/` and `reports/` may still contain previous sports/crypto/weather/culture full-scan outputs. The runtime now ignores stale out-of-scope dashboard snapshots, but old files were not deleted.

## Next Steps

1. Regenerate production/dashboard artifacts from the new three-section scope.
2. Add dedicated stocks/trade registry entries and external adapters for SEC, official closes, WTO/USTR/UN Comtrade/Census releases with as-of storage.
3. Add dashboard copy labels for display names such as “Macroeconomics” and “Stocks / Trade” while preserving stable JSON IDs.
