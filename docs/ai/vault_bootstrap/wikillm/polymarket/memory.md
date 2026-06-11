# Memory

## Pattern 1

- Pattern: Polymarket project work is research-only and must stop before execution infrastructure.
- Evidence:
  - FACT: The active goal specifies historical backtesting and paper-trading only.
  - FACT: Repo-local routing files prohibit real-money betting, wallet actions, automated order execution, credential storage, and exchange trading execution.
- Implication: Future implementation should treat order execution, wallet integration, and credential-handling requests as out of scope unless Max explicitly changes the project boundary.

## Pattern 2

- Pattern: Nexus readiness must be reported by layer.
- Evidence:
  - FACT: `.mcp.json` and `.cursor/mcp.json` point to a valid connector path.
  - FACT: `node --check` passes for the global Obsidian Nexus connector.
  - FACT: live `toolManager_getTools` timed out on 2026-05-25.
- Implication: Future runs can use repo config readiness, but must validate live Nexus before performing vault actions through MCP.

## Pattern 3

- Pattern: Local fixture-first validation is not the same as completing the full Polymarket system goal.
- Evidence:
  - FACT: `python3 -m sports_edge.cli goal-audit` reports 10 proven, 2 partial, and 3 missing requirements after the 2026-06-10 finish pass.
  - FACT: Postgres migration application, production cron success, Vercel dashboard verification, and approved live-source parsing were not performed in that run.
- Implication: Future operators should use `goal-audit` before claiming completion and should only mark the goal complete after external DB/deployment/live-source proof exists.
