---
name: polymarket-history-builder
description: Use for building historical odds, price, news, source, event, and settlement datasets for Polymarket backtesting.
---

# Polymarket History Builder

## Purpose

Build reproducible history for backtests and paper-trading analysis. History must distinguish raw observations, derived features, forecast snapshots, paper decisions, and settlement outcomes.

## Workflow

1. Identify the market, category, outcome token, settlement rule, and timestamp window.
2. Collect market metadata, price snapshots, spreads, liquidity, volume, news/context items, and final outcome.
3. Record missing history intervals explicitly; do not silently forward fill gaps.
4. Use time-ordered splits for modeling and backtesting.
5. Store source IDs, URLs, extraction timestamps, and quality flags with every observation.

## Required Checks

- no look-ahead data in decision snapshots
- settlement source is documented
- market wording and outcome mapping are stable
- price, spread, and liquidity fields are separate
- stale or missing windows are flagged

## Output

Return a dataset note with schema, time coverage, source coverage, known gaps, and backtest eligibility.
