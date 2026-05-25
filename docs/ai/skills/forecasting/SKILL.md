---
name: polymarket-forecasting
description: Use for forward probability forecasts, scenario updates, uncertainty, and category-specific forecast interpretation.
---

# Polymarket Forecasting

## Purpose

Produce explainable probability forecasts for paper-trading decisions. Forecasts must include uncertainty, source coverage, and conditions that would invalidate the thesis.

## Workflow

1. Start from market-implied probability and category base rates.
2. Add odds movement, liquidity, spread, news context, category expert evidence, and settlement ambiguity.
3. Check for contradictions, stale evidence, and missing primary sources.
4. Produce a calibrated probability, confidence, EV, and no-bet threshold.
5. Document what would change the forecast.

## Required Output

- probability and confidence
- market price and edge
- source coverage and evidence age
- contradiction and ambiguity flags
- failure conditions
- paper-only recommendation

## Rules

Forecasts are not trading instructions. Use them only for local research, backtests, paper logs, and review.
