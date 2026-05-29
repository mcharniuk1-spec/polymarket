# Polymarket Codex Automation: Full Run

Purpose: run the complete managed research cycle: chronological agent replay plus ML/correlation update.

Steps:
1. Run the Run Agents workflow from `run-agents-instructions.md`.
2. Run the Run ML workflow from `run-ml-instructions.md`.
3. Refresh latest dashboard payload.
4. Report whether both parts completed, partially completed, or had no new data.

Source and model expansion:
- Load `docs/ai/source_registry.json` and `docs/ai/runs/20260529_external_series_source_expansion.md` before broad category review.
- Treat Polymarket Gamma/CLOB as implemented live market sources; treat external crypto, sports, macro, trade, company, and conflict sources as registered/planned unless a fetcher and as-of storage are explicitly implemented.
- For every category report, include which sources were fetched, which were planned, and which were blocked by API key/license/access review.
- Do not strengthen a paper decision from an external source unless the source item has a timestamp, release time, URL/source id, and was available at or before decision time.

Rules:
- Preserve chronological order.
- Do not use future data.
- Do not execute real-money actions.
- If agents fail, do not run ML on partial untrusted outputs unless the failure is explicitly marked non-blocking.
- If ML fails, keep agent decisions and report ML failure separately.

Expected output:
- Full-run status.
- Agent runs processed.
- ML updates processed.
- Correlation matrices updated.
- Dashboard update status.
- Blockers and next required action.

Local commands:

```bash
python3 -m sports_edge.cli run-agent-replay
python3 -m sports_edge.cli run-ml-update --global-review
python3 -m sports_edge.cli managed-state run-history
```
