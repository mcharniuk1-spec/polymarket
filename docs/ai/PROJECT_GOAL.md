---
title: Polymarket Project Goal
tags:
  - project/polymarket
  - goal
  - research-only
---

# Polymarket Project Goal

Build a research-only Polymarket analytics MVP for macroeconomics, politics, and stocks/trade-related markets with odds modeling, market/news context, paper bankroll decisions, and learning dashboards.

## Scope

- Public/read-only Polymarket market discovery where available.
- Active sections only: macroeconomics, politics, and stocks/trade-related markets.
- Odds and price-history modeling.
- Market and news context by category.
- Three user-facing agents:
  - Context Agent: broad daily context first, then candidate-specific evidence.
  - Data Agent: market data, order books, spreads, liquidity, volume, history, rules, resolution criteria, time to resolution, and external numeric readiness.
  - Decision Agent: reject/watchlist/paper-bet decisions, portfolio risk, reasoning records, and learning updates.
- Paper-only decision and bankroll management.
- Final synthesis and top-10 bet ranking.
- Local dashboard with forecasts, confidence scores, EV estimates, odds history, paper-trading decisions, win/loss rate, calibration metrics, simulated ROI, drawdown, agent performance, and mistake reviews.

## Safety Boundary

This project is historical backtesting and paper-trading only.

Do not implement:

- Real-money betting.
- Wallet, key, or exchange transaction flows.
- Automated order execution.
- Credential capture or storage.
- Claims of guaranteed profit.

## Done Criteria

The MVP is done when it runs locally, stores paper-trading logs, and generates a performance report.

If data access, APIs, model quality, or safety constraints block progress, stop and report the blocker and next required input.
