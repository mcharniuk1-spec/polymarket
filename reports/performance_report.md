# Sports Odds Research Performance Report

Generated: 2026-05-26T08:12:24Z

## Guardrails

- Mode: research-only paper trading.
- Execution: no sportsbook connection, no real-money betting, no automatic order placement.
- Data: bundled historical fixture data for local MVP validation.

## Summary Metrics

- Forecasts: 16
- Paper trades: 3
- Win/loss: 3/0
- Win rate: 100.0%
- Simulated ROI: 68.3%
- Total PnL: 0.51 units
- Max drawdown: 0.0%
- Brier score: 0.1555

## Calibration

| Bucket | Count | Predicted midpoint | Actual win rate |
|---|---:|---:|---:|
| 0.50-0.55 | 0 | 52.5% | n/a |
| 0.55-0.60 | 1 | 57.5% | 100.0% |
| 0.60-0.65 | 2 | 62.5% | 100.0% |
| 0.65+ | 0 | 82.5% | n/a |

## Paper Trades

| Event | Selection | Odds | Prob | EV | Stake | Outcome | PnL |
|---|---|---:|---:|---:|---:|---|---:|
| Philadelphia at Atlanta | Atlanta | -122 | 56.7% | 3.2% | 0.25 | WIN | 0.20 |
| Miami at Boston | Boston | -165 | 63.4% | 1.8% | 0.25 | WIN | 0.15 |
| Calgary at Edmonton | Edmonton | -160 | 61.9% | 0.6% | 0.25 | WIN | 0.16 |

## Limitations

- Fixture data is intentionally small and not predictive of live market performance.
- News sentiment is a transparent handcrafted feature, not a production NLP model.
- Forecast quality must be revalidated with larger historical datasets before any real-world use.
