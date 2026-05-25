# Run: Nexus Graphify Obsidian Bootstrap

## Task

Set up Nexus, Graphify, and Obsidian-oriented agent infrastructure for `/Users/getapple/Documents/Polymarket`, considering the active research-only sports odds and market-news MVP goal.

## Inputs

- Active goal: local MVP with odds ingestion, market/news context, sports statistics, odds movement, risk control, forecasts, EV estimates, paper-trading decisions, calibration metrics, simulated ROI, and drawdown.
- Repo path: `/Users/getapple/Documents/Polymarket`.
- Polymarket Nexus connector path: `/Users/getapple/Documents/Obsidian Project Vaults/Polymarket/.obsidian/plugins/nexus/connector.js`.
- Graphify executable: `/Users/getapple/.local/bin/graphify`.

## Outputs

- Repo-local `AGENTS.md` and `CLAUDE.md`.
- Repo-local `.mcp.json`, `.cursor/mcp.json`, and Cursor rules.
- Repo-local project goal and Nexus/Obsidian/Graphify contract notes.
- Initial Graphify generated output in `graphify-out/`.
- Staged WikiLLM and Obsidian vault bootstrap files under `docs/ai/vault_bootstrap/`.

## Checks

- `scripts/verify_ai_stack.sh`: passed.
- `node --check /Users/getapple/Documents/Obsidian Vault/.obsidian/plugins/nexus/connector.js`: passed.
- `graphify update .`: generated 31 nodes, 23 edges, and 8 communities.
- `graphify query "What is this repo set up to do?" --budget 1200`: returned the expected Nexus/Graphify setup nodes.
- `python3 -m unittest discover -s tests`: passed, 4 tests.
- `python3 -m sports_edge.cli run-demo`: passed, wrote `data/paper_trades.jsonl` and `reports/performance_report.md`.
- `python3 -m sports_edge.app --host 127.0.0.1 --port 8765`: running locally after sandbox escalation.
- `curl --max-time 5 -sS http://127.0.0.1:8765/api/summary`: passed.
- `curl --max-time 5 -sS http://127.0.0.1:8765/`: returned dashboard HTML.

## Blockers

GAP: Live Nexus `toolManager_getTools` for the global vault timed out after 120 seconds. Use filesystem-backed notes until the Obsidian/Nexus runtime is reloaded and responds.

GAP: A later `graphify update .` pass stalled after the MVP scaffold appeared and was stopped. The existing `graphify-out/graph.json` remains valid JSON, but it may not include every later scaffold file until Graphify is rerun cleanly.

## Next steps

- Copy staged WikiLLM files into `/Users/getapple/Documents/getapple/core/wiki/projects/polymarket`.
- Copy staged Obsidian vault files into `/Users/getapple/Documents/Obsidian Project Vaults/Polymarket`.
- Register/open the Polymarket vault in Obsidian and enable Nexus.
- Re-run live Nexus `toolManager_getTools` before using MCP note operations.
