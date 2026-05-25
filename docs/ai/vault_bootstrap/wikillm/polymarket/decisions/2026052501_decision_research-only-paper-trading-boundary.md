# Decision: research-only paper-trading boundary

## Status

Accepted.

## Decision

Polymarket MVP work is limited to local research, historical backtesting, paper-trading logs, forecasts, confidence scores, EV estimates, calibration metrics, simulated ROI, and drawdown reports.

Do not implement real-money betting, wallet actions, automated order execution, credential storage, or exchange trading execution.

## Why

The active goal explicitly requires historical backtesting and paper trading only.

## Consequences

- Data models may represent hypothetical decisions and simulated fills.
- Code must not submit live orders or require private trading credentials.
- If future work needs live exchange access, it requires a new explicit approval and safety review.

