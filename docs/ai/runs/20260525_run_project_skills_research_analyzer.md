---
title: Project Skills And Research Analyzer Expansion
date: 2026-05-25
status: completed
---

# Project Skills And Research Analyzer Expansion

## Task

Implement repo-local Polymarket project skills, widen the news/source registry by category, add fixture-backed per-bet/topic research planning, and expose CLI commands for source and research review.

## Inputs

- User implementation plan for project skills and research analyzer expansion.
- `AGENTS.md`
- `docs/ai/PROJECT_GOAL.md`
- `docs/ai/NEXUS_OBSIDIAN_GRAPHIFY.md`
- Existing multi-agent paper pipeline in `sports_edge/agents.py`.

## Outputs

- Added project skill router: `docs/ai/PROJECT_SKILLS.md`.
- Added 10 project-local skills under `docs/ai/skills/`.
- Added structured source registry: `docs/ai/source_registry.json`.
- Added source registry loader/validator: `sports_edge/source_registry.py`.
- Added fixture-backed research planner: `sports_edge/bet_research.py`.
- Added CLI commands:
  - `python3 -m sports_edge.cli list-sources --category crypto`
  - `python3 -m sports_edge.cli research-bet --candidate-id fixture-crypto-001`
  - `python3 -m sports_edge.cli research-topic --category geopolitics --topic "Ukraine ceasefire deadline"`
- Extended candidate/context outputs with `global_context_score`, `category_context_score`, `bet_research_score`, source coverage, contradiction flags, staleness flags, and resolution risk flags.
- Added tests for skill frontmatter, source registry coverage, per-category research briefs, and CLI smoke commands.

## Verification

- `python3 -m json.tool docs/ai/source_registry.json`: passed.
- `python3 -m py_compile sports_edge/*.py`: passed.
- `python3 -m unittest discover -s tests`: passed, 9 tests.
- `node --check web/app.js`: passed.

## Safety

- Implementation remains research-only and paper-only.
- No wallet, signing, credential storage, order posting, or automated execution was added.
- Sources requiring API keys, paid access, restricted access, manual licensing, or unofficial endpoints are marked `allowed_by_default: false`.
- Research brief generation is fixture-backed and does not fetch live network data by default.

## GAP

External WikiLLM/Obsidian memory was not written because the current sandbox writable roots only include the Polymarket workspace and temp paths. This repo-local run note is the durable fallback for this session.

## Next Steps

- Add live adapters only after source-by-source access, licensing, rate limit, and terms review.
- Add dashboard views for source coverage, per-bet research briefs, and research flags if the UI needs them.
