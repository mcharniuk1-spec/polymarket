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
