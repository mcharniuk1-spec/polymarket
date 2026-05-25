---
name: polymarket-past-modeling
description: Use for historical model fitting, feature review, leakage checks, calibration, and mistake analysis in the Polymarket paper MVP.
---

# Polymarket Past Modeling

## Purpose

Model past market outcomes only with information available at the decision time. Treat model quality as provisional until calibration and out-of-sample diagnostics pass.

## Workflow

1. Define the target outcome, horizon, category, and decision use.
2. Build baselines first: market price, category base rate, simple trend, and no-bet policy.
3. Add features only when provenance and timestamp alignment are clear.
4. Use time-aware validation and rolling-origin checks where history allows.
5. Score with Brier score, log loss, calibration buckets, ROI, drawdown, and mistake attribution.

## Guardrails

- No leakage from settlement, post-event news, closing prices, or future outcomes.
- No model is reliable without diagnostics against a baseline.
- Separate correlation, plausible mechanism, and tested causal evidence.

## Output

Report model class, features, train/test split, benchmark comparison, calibration, residual risks, and rejected features.
