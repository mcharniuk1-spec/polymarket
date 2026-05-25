# Polymarket Codex Automation: Full Run

Purpose: run the complete managed research cycle: chronological agent replay plus ML/correlation update.

Steps:
1. Run the Run Agents workflow from `run-agents-instructions.md`.
2. Run the Run ML workflow from `run-ml-instructions.md`.
3. Refresh latest dashboard payload.
4. Report whether both parts completed, partially completed, or had no new data.

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
