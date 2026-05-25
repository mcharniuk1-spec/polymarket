# Polymarket Project Skills

This router keeps project-specific operating knowledge local to the Polymarket MVP. Use these skills before adding new data, research, modeling, decision, or monitoring behavior.

Safety boundary: all workflows are public/read-only, historical, backtesting, or paper-trading only. Do not add wallet flows, credential storage, order placement, automated exchange execution, or claims of guaranteed profit.

## Skill Map

- `docs/ai/skills/data-ingestion/SKILL.md` - public source assessment, extraction, schema, provenance, and validation.
- `docs/ai/skills/history-builder/SKILL.md` - odds, news, event, and outcome history construction for backtests.
- `docs/ai/skills/past-modeling/SKILL.md` - historical model fitting, leakage control, calibration, and mistake analysis.
- `docs/ai/skills/forecasting/SKILL.md` - forward probability forecasts, scenario updates, and uncertainty intervals.
- `docs/ai/skills/global-category-news-analysis/SKILL.md` - global and category news/context source planning.
- `docs/ai/skills/bet-topic-research/SKILL.md` - separate research briefs for a single candidate bet or topic.
- `docs/ai/skills/decision-probability-review/SKILL.md` - Brier/log-loss, calibration, EV, and decision review.
- `docs/ai/skills/trading-psychology/SKILL.md` - behavioral controls, pre-mortems, and bias checks.
- `docs/ai/skills/portfolio-optimization/SKILL.md` - paper-only exposure caps, fractional Kelly, correlation, and drawdown rules.
- `docs/ai/skills/monitoring-signals/SKILL.md` - watchlists, signals, review cadence, and alert criteria.

## Shared Inputs

- Source registry: `docs/ai/source_registry.json`
- Polymarket API notes: `docs/POLYMARKET_API_NOTES.md`
- Project goal: `docs/ai/PROJECT_GOAL.md`
- Safety contract: `AGENTS.md`

## Shared Output Contract

Every research or modeling output should separate:

- observed data
- derived features
- forecasts
- paper decisions
- performance metrics
- unresolved gaps

Use `FACT`, `INTERPRETATION`, `HYPOTHESIS`, and `GAP` when recording durable conclusions or risk assessments.
