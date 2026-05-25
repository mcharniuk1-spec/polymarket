# Rules

- Keep the project research-only unless Max explicitly changes the objective.
- Do not implement real-money betting, wallet actions, automated order execution, credential storage, or exchange trading execution.
- Separate observed data, derived features, forecasts, paper-trading decisions, and performance metrics.
- Preserve data provenance for odds, market/news context, and sports statistics.
- Use Graphify for repo structure after `graphify-out/graph.json` exists.
- Use Nexus only after `toolManager_getTools` succeeds in the current session.
- Mask secrets before writing to notes, logs, or generated outputs.

