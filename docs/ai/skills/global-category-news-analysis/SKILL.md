---
name: polymarket-global-category-news-analysis
description: Use for global and per-category news/context source planning, source reliability review, and category evidence scoring.
---

# Global And Category News Analysis

## Purpose

Widen and govern the source list for each Polymarket category. The analyzer should separate global context, category context, and single-bet evidence.

## Workflow

1. Load `docs/ai/source_registry.json`.
2. Select global sources plus category-specific sources.
3. Prefer official, primary, and documented public APIs.
4. Tag each source for reliability, freshness, history depth, access, and default eligibility.
5. Build query plans without fetching live data unless explicitly requested.
6. Score source coverage, contradiction risk, stale evidence, and resolution ambiguity.

## Category Priorities

- Sports: schedules, injuries, team/player stats, odds consensus, final score settlement.
- Geopolitics: official statements, conflict/event data, election boards, actor incentives, deadlines.
- Crypto: exchange market data, on-chain metrics, stablecoin/DeFi data, oracle/source timing.
- Macro: official releases, revisions, survey consensus, calendar timing.
- Weather: named stations, official observations, forecast model spread, exact thresholds.
- Culture: official award/platform pages, audience signals, wording ambiguity, subjective settlement risk.

## Output

Return source plan, query templates, source reliability notes, context scores, and explicit gaps.
