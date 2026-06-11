# Polymarket Agent Contract

Use the workspace contract from `/Users/getapple/Documents/Polymarket/docs/ai/NEXUS_OBSIDIAN_GRAPHIFY.md`.

Project identity: Polymarket research-only prediction-market analytics and paper-bankroll MVP.

Active analytical scope: macroeconomics, politics, and stocks/trade-related markets only.

Operating agents: Context Agent, Data Agent, and Decision Agent. Internal odds/context/category/model helpers must roll up to those three agents in user-facing outputs.

Primary durable memory layer: Polymarket Obsidian project vault plus WikiLLM project `polymarket`. Use the global Obsidian control vault for cross-project routing.

Before broad work:

1. Read this file.
2. Read `docs/ai/PROJECT_GOAL.md`.
3. Read `docs/ai/NEXUS_OBSIDIAN_GRAPHIFY.md`.
4. If `graphify-out/graph.json` exists, use `graphify query`, `graphify explain`, or `graphify path` before broad file reads.

Safety boundary: build public/read-only ingestion, historical backtesting, and paper-trading analysis only. Do not implement real-money betting, wallet actions, automated order execution, credential storage, or exchange trading execution.
