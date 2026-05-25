---
title: Polymarket Nexus Obsidian Graphify Setup
tags:
  - project/polymarket
  - nexus
  - obsidian
  - graphify
  - agent-contract
---

# Polymarket Nexus Obsidian Graphify Setup

## Identity

FACT: This repo is `/Users/getapple/Documents/Polymarket`.

FACT: The active goal is a research-only multi-category Polymarket odds, market-news, agent-scoring, and paper-bankroll analytics MVP with paper-trading and historical backtesting only.

INTERPRETATION: The project belongs to the `polymarket` memory layer and dedicated Polymarket Obsidian project vault. Global agent-infra remains the cross-project control room.

## Required Routing

Before meaningful work:

1. Read `AGENTS.md`.
2. Read `docs/ai/PROJECT_GOAL.md`.
3. Read this file.
4. Check `graphify-out/graph.json`.
5. If the graph exists, use Graphify for orientation before broad file reads.
6. Use Nexus only for live Obsidian state, note operations, tasks, workspace memory, or runtime workflows.

## Nexus

Repo-local MCP files expose a `nexus` server that points to the Polymarket Obsidian project vault connector:

`/Users/getapple/Documents/Obsidian Project Vaults/Polymarket/.obsidian/plugins/nexus/connector.js`

Runtime states are separate:

- Connector/config readiness: `.mcp.json`, `.cursor/mcp.json`, and connector syntax validate.
- Obsidian activation readiness: Obsidian has the vault registered and the Nexus plugin enabled.
- Live MCP readiness: Nexus responds to `toolManager_getTools` and then `toolManager_useTools`.

Current setup should not claim live readiness unless `toolManager_getTools` returns successfully in the current session.

## Graphify

Use local `graphify-out/` as generated repo structure, not final human synthesis.

Commands:

```bash
graphify update .
graphify query "How is the MVP structured?"
graphify explain "paper trading"
```

Generated graph output stays in `graphify-out/`. Human conclusions belong in WikiLLM/Obsidian notes, not hand-edited graph JSON.

## Obsidian And WikiLLM

Durable knowledge should be written to:

- WikiLLM: `/Users/getapple/Documents/getapple/core/wiki/projects/polymarket`
- Project vault: `/Users/getapple/Documents/Obsidian Project Vaults/Polymarket`
- Global control vault index: `/Users/getapple/Documents/Obsidian Vault/00_Core/WikiLLM/Project_Vaults/00_Project_Vaults_Index.md`

If those paths do not exist or are not writable, record a GAP in chat and create repo-local notes under `docs/ai/` until external vault writes are approved.

## Safety Rules

Do not store secrets in repo files, Obsidian notes, Graphify output, logs, or MCP config.

Do not implement real-money betting, wallet actions, automated order execution, credential storage, or exchange trading execution.

Separate:

FACT:
INTERPRETATION:
HYPOTHESIS:
GAP:

for durable decisions, architecture changes, and risk assessments.
