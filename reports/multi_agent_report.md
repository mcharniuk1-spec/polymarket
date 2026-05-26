# Polymarket Multi-Agent Paper Analytics Report

Generated: 2026-05-25T17:25:12Z

## Guardrails

- Mode: paper-only research analytics.
- Execution: no wallet, no credentials, no order posting, no automated real-money betting.
- Live mode, when selected, uses public read-only Polymarket APIs for discovery and market data.
- Source note: bundled deterministic multi-category fixture; 600 default candidates gives 100 per category

## Overall Metrics

- Candidates analyzed: 300
- Paper bets: 70
- Watchlist: 12
- Rejected: 37
- Starting bankroll: 100.00 coins
- Ending bankroll: 99.37 coins
- Staked: 100.00 coins
- Unallocated deployment budget: 0.00 coins
- Win/loss: 28/42
- Win rate: 40.0%
- Simulated ROI: -0.6%
- Brier score: 0.2048
- Log loss: 0.5983
- Max drawdown: 19.8%

## Top 10 Paper Bets

| Rank | Category | Market | Prob | Price | EV | Risk | Stake | Outcome |
|---:|---|---|---:|---:|---:|---|---:|---|
| 1 | macro | Will treasury yields resolve above consensus in release window #15? / Yes | 29.8% | 25.0% | 19.0% | HIGH | 1.50 | WIN |
| 2 | weather | Will the snowfall threshold be reached in monitored region #45? / Yes | 37.7% | 33.0% | 14.1% | MEDIUM | 2.08 | WIN |
| 3 | weather | Will the rainfall threshold be reached in monitored region #48? / Yes | 22.8% | 20.0% | 14.2% | HIGH | 1.07 | LOSS |
| 4 | weather | Will the rainfall threshold be reached in monitored region #33? / Yes | 24.6% | 21.0% | 17.3% | HIGH | 1.38 | WIN |
| 5 | macro | Will unemployment resolve above consensus in release window #8? / Yes | 39.1% | 34.0% | 14.9% | HIGH | 1.50 | LOSS |
| 6 | geopolitics | Will US election produce a verified policy breakthrough before deadline #17? / Yes | 29.8% | 25.0% | 19.4% | HIGH | 1.50 | LOSS |
| 7 | macro | Will Fed decision resolve above consensus in release window #41? / Yes | 21.8% | 19.0% | 14.7% | HIGH | 1.03 | WIN |
| 8 | sports | Will Boston beat Philadelphia in the MLB fixture #45? / Yes | 31.2% | 28.0% | 11.3% | HIGH | 1.32 | LOSS |
| 9 | sports | Will Boston beat Miami in the NHL fixture #16? / Yes | 53.0% | 47.0% | 12.9% | HIGH | 1.50 | WIN |
| 10 | crypto | Will Ethereum close above the stated threshold in market window #7? / Yes | 24.6% | 22.0% | 11.9% | HIGH | 1.01 | LOSS |

## Category Stats

| Category | Candidates | Bets | Watchlist | Rejected | Win rate | Avg odds | Avg EV | PnL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sports | 50 | 13 | 0 | 0 | 38.5% | 2.38 | 1.3% | -3.93 |
| geopolitics | 50 | 12 | 1 | 0 | 50.0% | 2.35 | 1.3% | 1.72 |
| crypto | 50 | 15 | 2 | 0 | 40.0% | 2.38 | 1.9% | -2.40 |
| macro | 50 | 14 | 3 | 0 | 28.6% | 2.36 | 2.3% | -0.91 |
| weather | 50 | 14 | 4 | 0 | 42.9% | 2.39 | 2.7% | 5.30 |
| culture | 50 | 2 | 2 | 37 | 50.0% | 2.39 | 1.2% | -0.42 |

## Agent Performance

| Agent | Score | Brier | Confidence | Notes |
|---|---:|---:|---:|---|
| odds_modeling | 79.30 | 0.2070 | 37.8% | Higher score means lower Brier error on fixture-settled candidates. |
| market_context_news | 79.60 | 0.2040 | 46.7% | Higher score means lower Brier error on fixture-settled candidates. |
| category_expert | 79.56 | 0.2044 | 51.4% | Higher score means lower Brier error on fixture-settled candidates. |
| decision_bankroll | 40.00 | n/a | n/a | Decision layer score is the paper-bet win rate before long-run calibration is available. |

## Mistake Reviews

| Candidate | Category | Type | PnL | Learning note |
|---|---|---|---:|---|
| fixture-weather-047 | weather | variance_or_stake_timing | -1.07 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-007 | macro | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-geopolitics-016 | geopolitics | ambiguity_or_actor_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-sports-044 | sports | variance_or_stake_timing | -1.32 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-crypto-006 | crypto | variance_or_stake_timing | -1.01 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-029 | macro | variance_or_stake_timing | -0.95 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-sports-022 | sports | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-crypto-023 | crypto | bad_news_or_context_read | -3.00 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-weather-014 | weather | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-008 | macro | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-015 | macro | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-culture-032 | culture | ambiguity_or_actor_timing | -1.09 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-048 | macro | variance_or_stake_timing | -0.99 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-022 | macro | variance_or_stake_timing | -1.40 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-041 | macro | variance_or_stake_timing | -1.33 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-weather-007 | weather | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-weather-025 | weather | variance_or_stake_timing | -1.24 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-crypto-025 | crypto | variance_or_stake_timing | -0.92 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-macro-046 | macro | bad_news_or_context_read | -2.82 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |
| fixture-crypto-030 | crypto | variance_or_stake_timing | -1.50 | Review whether this loss came from model probability, context interpretation, liquidity, stake size, or irreducible variance. |

## API Notes

- Gamma is used for market/event/tag/sports discovery.
- CLOB orderbook, midpoint, spread, last-trade, and price-history endpoints are the canonical read surface for executable market analytics.
- Data API trade/activity/holders/open-interest endpoints should be used for public market history and participation signals.
- UI scraping is not used for data that official APIs expose.

## Reliability Note

This system estimates positive expected value and paper performance. It does not guarantee daily profit and does not execute real-money trades.
