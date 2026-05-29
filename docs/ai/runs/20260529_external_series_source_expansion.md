# 2026-05-29 External Series Source Expansion

## Safety Boundary

FACT: This project remains research-only and paper-only. No wallet actions, credential storage, order posting, automated betting, or exchange execution are in scope.

FACT: The current live full scan fetches Polymarket Gamma market metadata and sampled CLOB price history. External crypto, sports, macro, trade, company, and conflict sources are now registered in the source registry, but they are not yet wired into live scoring unless a fetcher explicitly exists.

## Added Source Coverage

The registry now covers the following new source classes:

| Scope | Source IDs | Default use |
|---|---|---|
| Crypto prices and oracle context | `crypto-binance-public-market-data`, `crypto-coinbase-exchange-market-data`, `crypto-kraken-public-market-data`, `crypto-deribit-public-market-data`, `crypto-okx-public-market-data`, `crypto-coinmetrics-community`, `crypto-defillama`, `crypto-chainlink-market-data-feeds` | Public exchange and network data can be used after entity mapping and as-of storage. OKX is disabled until terms review; CoinGecko remains key/plan gated. |
| Sports tables, fixtures, player/team stats, esports, and tennis | `sports-official-league-standings-tables`, `sports-mlb-stats-api`, `sports-openligadb`, `sports-football-data-org`, `sports-balldontlie`, `sports-pandascore-esports`, `sports-tennis-official-rankings-results`, existing official schedule/injury sources | Official and public no-key sources are visible by default. Keyed sports/esports APIs stay disabled until access review. |
| Geopolitics, government, and conflict | `geopolitics-ucdp-api`, `geopolitics-official-sanctions-lists`, `geopolitics-ofac-sanctions-list-service`, `geopolitics-congress-gov-api`, `geopolitics-regulations-gov-api`, `geopolitics-usaspending-api`, existing GDELT, ReliefWeb, UN, NATO, EU, election sources | Official statements and public feeds can be attached immediately; UCDP, ACLED, Congress.gov, and Regulations.gov require access review/key where noted. |
| Macro and G20 panels | `macro-oecd-data-api`, `macro-eurostat-api`, `macro-ecb-data-portal`, `macro-census-international-trade`, existing World Bank, IMF, BLS, Treasury, BEA, FRED, EIA | Public official APIs can provide country and regional panels. Keyed APIs remain disabled until configured. |
| Trade and companies | `global-wto-timeseries`, `global-un-comtrade`, `global-sec-edgar-companyfacts`, `macro-census-international-trade` | SEC EDGAR is public no-key; WTO, UN Comtrade, and Census trade require free key/access review before live adapters. |

## Category Workflow

1. Entity resolver maps each market group to actors, teams, players, countries, commodities, companies, chains, tokens, or leagues.
2. Source planner selects Polymarket plus global plus category-specific sources from `docs/ai/source_registry.json`.
3. Fetchers only read public or configured approved APIs and store raw observations with `observed_at`, `released_at`, `fetched_at`, `source_id`, `entity_id`, and request parameters.
4. Feature builder uses only observations with `released_at <= decision_at`.
5. Model agents compute market-implied, market-history, news/context, external-series, and sibling-market features separately.
6. Decision agent treats external-series and correlation outputs as context, not as hard overrides.
7. Evaluation agent records whether later price movement, settlement, or news invalidated the thesis.

## Proposed Durable Schema

These tables should be added to PostgreSQL when external fetchers are implemented:

| Table | Purpose |
|---|---|
| `external_series` | Registry for external time series: source, category, entity, unit, frequency, source URL, license/access status. |
| `external_series_points` | Versioned observations with observed/released/fetched timestamps, value, revision id, and raw payload. |
| `entity_aliases` | Maps Polymarket text to teams, players, tokens, countries, companies, leagues, and source-specific IDs. |
| `market_series_links` | Links market/event/outcome ids to external series with relation type, sign prior, lag prior, and confidence. |
| `market_feature_snapshots` | As-of feature vector used by the agents at decision time, including missingness/staleness flags. |
| `correlation_snapshots` | Raw, lagged, residual, and forecast-error correlations with overlap count, window, lag, and confidence interval. |
| `source_evidence_items` | Fetched news/context/source facts with source id, URL, publication/release time, relevance, and reliability. |

JSON fallback keys should mirror these tables for local runs until Postgres is configured.

## Modeling Additions

For market and external series:

- Normalize price-like series as log returns or probability-logit deltas.
- Normalize macro and sports levels as rolling z-scores, percent changes, rate changes, and release-surprise deltas where consensus is available.
- Align all series into as-of buckets, preserving true release time and revision version.
- Compute raw correlation only over overlapping observed windows.
- Compute lagged correlation over configured lags, for example 15m, 1h, 6h, 24h, 7d depending on category.
- Compute residual correlation after removing baseline market price, spread, liquidity, volume, news/context score, and event/sibling effects.
- Compute forecast-error correlation once next-price labels or resolved outcomes are known.
- Use Fisher-z intervals when overlap count is sufficient; otherwise mark sparse.
- Inflate forecast intervals for stale external data, low liquidity, wide spread, missing source evidence, high model disagreement, and unstable correlations.

Fallback Gamma-derived pseudo-history must be excluded from correlation training or heavily downweighted and labeled `fallback_derived`.

## Category Priorities

| Category | Immediate focus | Why |
|---|---|---|
| Sports | MLB/NBA, tennis, esports, soccer tables where market groups are dense | Event grouping is strong, sibling bets are frequent, and official result/stat sources can improve reliability. |
| Culture | Awards, platforms, box office, Steam/Wikimedia attention signals | Current paper decisions were strongest here, but settlement wording must be checked carefully. |
| Crypto | BTC/ETH/SOL and major exchange pairs, stablecoin/DeFi stress, oracle timing | Many markets and strike ladders exist, but high volatility requires stronger external time-series controls before paper allocation increases. |
| Macro | G20 inflation, rates, GDP, jobs, energy, trade/tariff indicators | Strong official sources exist, but release calendars and revisions must be modeled before decisions become reliable. |
| Geopolitics | Elections, sanctions, official deadlines, conflict-event counts | Use official sources first; GDELT/UCDP/ReliefWeb are context and trend inputs, not single-source settlement proof. |
| Weather | Keep official station/model sources separate from current external expansion | Already has a strong source registry, but many decisions remain blocked by wording/source precision. |

## Execution Rules For Scheduled Runs

- Four Codex daily runs at 06:00, 12:00, 18:00, and 22:00 should run the same prompt and report fetched/planned/blocked sources.
- GitHub Actions should run the managed cycle directly on the runner with durable storage configured; Vercel should serve dashboard/API and health checks, not long full-cycle work.
- Each run must validate the source registry before collecting markets.
- Each run must label external source status as `implemented`, `client_available_not_wired`, `registered_needs_fetcher_and_asof_storage`, or `blocked_until_access_or_license_review`.
- No API key source should be silently treated as live. It must be disabled until the key and terms are configured.

## Next Implementation Order

1. Add normalized external-series Postgres projections and JSON fallback state.
2. Add entity alias mapping for tokens, teams, leagues, countries, companies, commodities, and event actors.
3. Implement read-only crypto OHLC adapters first because Binance, Coinbase, Kraken, and Deribit are public, frequent, and useful for correlation testing.
4. Implement sports official/public adapters for MLB, tennis official pages, and soccer standings/results; add PandaScore/BALLDONTLIE only after access review.
5. Add OECD/World Bank/IMF/Eurostat/ECB macro panels with release-time handling and revisions.
6. Add GDELT/ReliefWeb/official sanctions/election/USAspending fetchers for geopolitics and government context; add UCDP/ACLED/Congress.gov/Regulations.gov only after access review where required.
7. Extend correlation artifacts and dashboard with market-external, residual, and error-correlation sections.
