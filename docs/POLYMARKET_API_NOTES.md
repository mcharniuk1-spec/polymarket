# Polymarket Public API Notes

Verified with the cooperating API/research agent on 2026-05-25.

## Read-Only Data Surfaces

- Gamma base URL: `https://gamma-api.polymarket.com`
  - Use for market/event discovery, tags, categories, sports metadata, teams, and public search.
  - Relevant endpoints include `/events`, `/events/keyset`, `/markets`, `/markets/keyset`, `/tags`, `/sports`, `/sports/market-types`, `/teams`, and `/public-search`.
- CLOB base URL: `https://clob.polymarket.com`
  - Use as canonical executable-market data: `/book`, `/books`, `/price`, `/prices`, `/midpoint`, `/midpoints`, `/spread`, `/spreads`, `/last-trade-price`, `/last-trades-prices`, `/prices-history`, and `/batch-prices-history`.
- Data API base URL: `https://data-api.polymarket.com`
  - Use for public trades, activity, holders, open interest, live volume, and public participation signals.
- WebSockets:
  - Market channel: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
  - User channel: `wss://ws-subscriptions-clob.polymarket.com/ws/user`
  - Sports channel: `wss://sports-api.polymarket.com/ws`
  - RTDS live data: `wss://ws-live-data.polymarket.com`

## Implementation Rules

- Do not scrape UI for market discovery, orderbooks, prices, history, trades, live volume, or activity when official APIs exist.
- Do not use archived `Polymarket/py-clob-client`; use direct read-only REST or current V2/unified SDKs when needed.
- Keep this MVP paper-only: no wallet, signing, relayer, credential storage, order posting, or automated execution.
- Filter live markets on active/open/orderbook availability before ranking.
- Store bid, ask, spread, midpoint, depth, timestamp, and source separately for slippage-aware EV.
- Record missing history intervals explicitly instead of silent forward filling.
