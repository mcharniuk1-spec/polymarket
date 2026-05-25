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

