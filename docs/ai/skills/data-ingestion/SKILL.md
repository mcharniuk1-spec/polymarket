---
name: polymarket-data-ingestion
description: Use for Polymarket project public/read-only data ingestion, source assessment, schema normalization, provenance capture, and validation.
---

# Polymarket Data Ingestion

## Purpose

Collect public market, odds, news, statistics, and reference data for research-only analysis. Prefer official APIs and documented public feeds over scraping. Never collect credentials, wallet data, private user data, cookies, or execution-capable secrets.

## Workflow

1. Define the target entity, fields, refresh cadence, history depth, and downstream decision use.
2. Check `docs/ai/source_registry.json` before adding a source.
3. Classify access as `public-no-key`, `free-key`, `paid`, `restricted`, `manual-licensed`, or `unofficial`.
4. Use API/documented feeds first; mark scraping or unofficial endpoints `allowed_by_default: false`.
5. Normalize timestamps to UTC, preserve source URL, extraction time, source ID, and quality flags.
6. Validate schema, missing values, duplicates, outliers, stale records, and source drift.

## Required Output

- target schema
- source IDs used
- provenance fields
- validation checks
- risk notes
- live-network status, if any

## Safety

Default implementation must be fixture-backed or public/read-only. Do not add order posting, signing, wallet, credential, or automated execution paths.
