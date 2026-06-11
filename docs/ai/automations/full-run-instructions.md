# Polymarket Codex Automation: Full Run

Purpose: run the complete managed research cycle: chronological agent replay plus ML/correlation update.

Steps:
1. Validate `docs/ai/source_registry.json` before any collection or model update.
2. If this is the daily broad research pass, run the read-only full scan so `data/generated/full_scan/*` includes current market coverage, source readiness, and guarded correlations.
3. Run the Run Agents workflow from `run-agents-instructions.md`.
4. Run the Run ML workflow from `run-ml-instructions.md`.
5. Refresh latest dashboard payload.
6. Report whether each part completed, partially completed, or had no new data.

Source and model expansion:
- Load `docs/ai/source_registry.json` and `docs/ai/runs/20260529_external_series_source_expansion.md` before broad category review.
- Treat Polymarket Gamma/CLOB as implemented live market sources; treat external crypto, sports, macro, trade, company, and conflict sources as registered/planned unless a fetcher and as-of storage are explicitly implemented.
- For every category report, include which sources were fetched, which were planned, and which were blocked by API key/license/access review.
- Do not strengthen a paper decision from an external source unless the source item has a timestamp, release time, URL/source id, and was available at or before decision time.
- Same-event and sibling markets are endogenous. Use them as exposure guardrails only, not independent causal instruments.
- Gamma-derived, fixture, and snapshot-only histories are diagnostic for correlations; do not use them to strengthen IV-style or related-odds signals.

Rules:
- Preserve chronological order.
- Do not use future data.
- Do not execute real-money actions.
- Treat each manual full scan as the current agent run for that moment. Do not merge with, emulate, or rely on GitHub/cron/15-minute managed-cycle state for current bets.
- After each manual full scan, overwrite the current dashboard state from that run so stale current-bet data is not carried forward.
- Treat `--top-limit 100` as a target for 100 approved `PAPER_BET` records with positive paper stake, not 100 candidate attempts or mixed recommendation rows.
- Do not pad the top paper-bet artifact with `WATCHLIST`, `NO_BET`, or `REJECTED` rows. If fewer than 100 approved paper bets survive the filters, report the shortfall and keep the run incomplete for publication.
- Current approved paper bets must be staked whenever there is paper budget. Allocate the full paper bankroll across the approved book, diversified across categories and weighted by reliability/risk tier, instead of leaving approved bets unstaked or over-concentrating only by rank. Event/risk caps are primary guardrails, but a paper-only residual pass may overflow them to avoid idle simulated bankroll.
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
python3 -m sports_edge.cli list-sources
python3 -m sports_edge.cli run-full-scan --all-active --top-limit 100 --history-sample-limit 300 --require-approved-top-limit --no-intelligence
python3 -m sports_edge.cli run-agent-replay
python3 -m sports_edge.cli run-ml-update --global-review
python3 -m sports_edge.cli managed-state run-history
```
