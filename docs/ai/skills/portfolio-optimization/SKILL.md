---
name: polymarket-portfolio-optimization
description: Use for paper-only bankroll allocation, exposure caps, fractional Kelly, correlation review, drawdown control, and lower-risk recommendation ranking.
---

# Portfolio Optimization

## Purpose

Optimize a simulated paper portfolio across candidate bets. This skill never authorizes real-money execution.

## Workflow

1. Rank by calibrated EV, confidence, liquidity, spread, source reliability, contradiction risk, and resolution ambiguity.
2. Apply paper bankroll, per-market, per-category, and correlated-topic caps.
3. Use fractional Kelly only after probability calibration is reviewed.
4. Reduce size under drawdown, stale evidence, thin liquidity, wide spread, or ambiguous settlement.
5. Keep watchlist candidates separate from active paper bets.

## Decision Labels

- `OPTIMAL_PAPER`: best risk-adjusted simulated allocation under caps.
- `LOWER_RISK_PAPER`: smaller stake or better evidence quality, but lower EV.
- `WATCHLIST`: edge or evidence is incomplete.
- `REJECTED`: rule, evidence, settlement, or source risk blocks the paper bet.

## Required Output

- allocation table
- cap usage by market/category/topic
- drawdown state
- risk penalties
- failure conditions

## Rule

A portfolio decision is incomplete without exposure caps and correlation notes.
