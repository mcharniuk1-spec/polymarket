# 2026-06-10 Run - Structured Live External Adapters

## Task
Reduce the live external-data gap without network calls, deployment, credentials, or trading execution by replacing health-only live adapters with parser-gated read-only structured adapters.

## FACT
- Live external adapters now attempt source-specific parsing for macro release timing, politics/institutional deadlines, stocks/trade event windows, and configured market-data return inputs.
- Source reachability rows remain `official_source_http_ok` with `source_health_not_decision_evidence` and are filtered out by model evidence detection.
- Unparsed live pages are not converted into model evidence.
- A separate `configured_market_data_provider` source record prevents live parsed market-data observations from being mislabeled as fixture data.

## INTERPRETATION
The system is closer to the requested Data Agent behavior because live mode now has a structured path for approved numeric observations instead of only source-health probes. The model layer now more clearly separates real external evidence from reachability checks.

## GAP
This pass did not perform live network validation or source-specific ToS review. `goal-audit` should continue to mark live official adapters as partial until approved public endpoints are validated in the real environment.

## Validation
- `python3 -m unittest discover -s tests` - passed, 47 tests.
- `python3 -m py_compile sports_edge/*.py api/*.py scripts/*.py` - passed.
- `node --check web/app.js` - passed.
- `python3 -m json.tool config/news-sources.json` - passed.
- `python3 -m sports_edge.cli migrate --dry-run` - passed.
- `python3 -m sports_edge.cli goal-audit` - passed, complete remains false by design.
- `python3 -m sports_edge.cli run-daily --source fixture --as-of 2026-06-10 --dry-run` - passed.
- `python3 -m sports_edge.cli run-collector --source fixture --as-of 2026-06-10T06:07:30Z --dry-run` - passed.
- `python3 -m sports_edge.cli run-managed-cycle --source fixture --cycle-type manual --target-count 30 --dry-run` - passed.

## Files Changed In This Pass
- `sports_edge/external_adapters.py`
- `sports_edge/model_scoring.py`
- `tests/test_pipeline.py`
- `README.md`
- `docs/ai/runs/20260610_run_structured_live_external_adapters.md`

## Next Step
After approved network/source validation is available, run live read-only adapter validation and capture source-specific proof without promoting unparsed pages or low-reliability social data into decisions.
