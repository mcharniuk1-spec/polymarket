# Issue: Nexus live tool call timed out

## Status

Open.

## Problem

FACT: During Polymarket setup on 2026-05-25, `mcp__nexus_global__.toolManager_getTools` timed out after 120 seconds.

FACT: Repo-local MCP config and connector syntax validation passed.

INTERPRETATION: File/config readiness is present, but live Nexus tool-manager readiness is not proven in this session.

## Impact

Agents should not claim live Obsidian/Nexus operations are available for Polymarket until `toolManager_getTools` returns successfully.

## Next validation

Reload or reopen Obsidian with the target vault, then call `toolManager_getTools` before any `toolManager_useTools` call.

