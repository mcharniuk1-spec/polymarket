---
name: polymarket-decision-probability-review
description: Use for probability quality, calibration, EV, Brier/log-loss, and decision review in the paper-only Polymarket MVP.
---

# Decision And Probability Review

## Purpose

Review whether a forecast deserves a paper decision. The decision layer must favor calibrated, explainable, lower-risk opportunities over raw EV claims.

## Literature Anchors

- Brier score for probability quality: Brier 1950.
- Reliability, resolution, and uncertainty: Murphy 1973.
- Proper scoring rules and honest probabilistic forecasts: Gneiting and Raftery 2007.
- Prediction-market prices as useful but imperfect probabilities: Wolfers and Zitzewitz 2004.

## Workflow

1. Compare forecast probability with market probability and category base rate.
2. Review Brier/log-loss history for the model and category.
3. Check calibration bucket, confidence, spread, liquidity, and settlement ambiguity.
4. Penalize stale evidence, weak source coverage, contradictory sources, and correlated exposure.
5. Produce decision: `PAPER_BET`, `WATCHLIST`, `NO_BET`, or `REJECTED`.

## Required Output

- market probability, fair probability, edge, EV
- confidence and calibration status
- source and settlement risk flags
- reason for decision
- failure conditions

## Rule

No probability estimate is reliable without calibration evidence or an explicit gap label.
