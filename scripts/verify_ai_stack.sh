#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONNECTOR="/Users/getapple/Documents/Obsidian Project Vaults/Polymarket/.obsidian/plugins/nexus/connector.js"

cd "$ROOT"

echo "Repo: $ROOT"

node -e "JSON.parse(require('fs').readFileSync('.mcp.json', 'utf8')); JSON.parse(require('fs').readFileSync('.cursor/mcp.json', 'utf8')); console.log('MCP JSON: ok')"

if [ -f "$CONNECTOR" ]; then
  node --check "$CONNECTOR"
  echo "Nexus connector syntax: ok"
else
  echo "Nexus connector: missing at $CONNECTOR"
  exit 1
fi

if command -v graphify >/dev/null 2>&1; then
  echo "Graphify: $(command -v graphify)"
else
  echo "Graphify: missing from PATH"
  exit 1
fi

if [ -f graphify-out/graph.json ]; then
  node -e "JSON.parse(require('fs').readFileSync('graphify-out/graph.json', 'utf8')); console.log('Graphify graph JSON: ok')"
else
  echo "Graphify graph JSON: not generated yet"
fi

echo "AI stack file readiness: ok"
