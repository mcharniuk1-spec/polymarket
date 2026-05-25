# Polymarket Codex Automation: Run Agents

Purpose: replay and process Polymarket collection runs chronologically as if agents were live at each run timestamp.

Rules:
- Research-only and paper-only.
- Do not place bets, create wallet flows, store credentials, or execute orders.
- Load the last processed agent run checkpoint.
- Load all unprocessed collection runs sorted ascending by collection timestamp.
- For each run, use only market data, odds, price history, and news available at or before the run timestamp.
- For each bet/market, ignore news newer than the collection timestamp or the bet decision timestamp.
- Run the existing agent stack in order: market data, odds modeling, news/context, category expert, decision/bankroll, evaluation/learning.
- Persist a chronological decision timeline for each bet: ideas, agent assessments, source context, paper decision, result if known, learning notes.
- If no new runs exist, output OK and say dashboard state is unchanged.
- If a gap or missing interval exists, record it explicitly; do not forward-fill silently.
- Never train or evaluate using future data.

Expected output:
- Compact automation report.
- Updated agent decision timeline state.
- Updated dashboard latest state if new runs were processed.

Local command:

```bash
python3 -m sports_edge.cli run-agent-replay
```
