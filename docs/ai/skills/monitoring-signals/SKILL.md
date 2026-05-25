---
name: polymarket-monitoring-signals
description: Use for watchlists, monitoring rules, source freshness, signals, and review cadences for paper-only Polymarket analysis.
---

# Monitoring Signals

## Purpose

Define repeatable monitoring rules for paper decisions and watchlists. Monitoring should produce evidence updates, not automated execution.

## Workflow

1. Define monitored candidates, topics, categories, and source IDs.
2. Track price movement, spread, liquidity, source updates, contradiction flags, and resolution wording changes.
3. Set clear signal thresholds before reviewing new evidence.
4. Mark action as `review`, `promote_to_paper`, `downgrade_to_watchlist`, or `reject`.
5. Log every material signal and whether it would have improved calibration or risk.

## Signal Types

- odds move: price, spread, volume, liquidity
- evidence update: primary source confirms/contradicts
- staleness: no fresh source within category-specific window
- resolution risk: wording or source ambiguity changes
- portfolio risk: category/correlation cap pressure

## Rule

Signals should wake up a review process. They must not place real-money orders or trigger automated exchange execution.
