# Polymarket Codex Automation: Run ML

Purpose: update ML models and correlation matrices from chronological Polymarket runs without time leakage.

Rules:
- Research-only and paper-only.
- Load persisted chronological snapshots, agent decisions, settled outcomes, and prior model state.
- Update online logistic models only with examples whose labels/outcomes were known at that timestamp.
- Maintain models for global, category, and recurring daily question archetypes.
- Build correlation matrices for each category using all relevant available related markets, not just top 100.
- Include direct recurring bets, sibling outcomes, same-event markets, same-actor markets, and strongly related topic markets.
- Compute price-delta correlations only over overlapping historical windows.
- Compute coefficient similarity from model weights.
- Build external-series features only from normalized points with `released_at <= decision_at`:
  log returns/deltas, rolling z-scores, EWMA trend, realized volatility, lagged deltas, source staleness, missingness flags, and entity-link confidence.
- For crypto, sports, geopolitics, macro, trade, and company panels, compute market-external raw correlation, lagged correlation, and residual/error correlation after removing baseline market price, liquidity, spread, and news/context effects.
- Store correlation metadata: window, lag, overlap count, source ids, entity link, Fisher-z confidence interval when possible, sparse/unreliable flags, and whether the series is observed or fallback-derived.
- Store related-bet influence as context features, not as hard decision overrides.
- Record sparse data, missing overlap, and unreliable correlations explicitly.

Expected output:
- Updated model state.
- Updated category correlation matrices.
- Updated model health report: sample count, Brier/log loss where available, calibration, last update timestamp.
- Compact summary for dashboard.

Local command:

```bash
python3 -m sports_edge.cli run-ml-update --global-review
```
