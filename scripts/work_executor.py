#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RUNS_PATH = Path("data/generated/intelligence/analysis_runs.json")
LATEST_PATH = Path("data/generated/intelligence/latest.json")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SLOT_SECONDS = 15 * 60
SLOT_TOLERANCE_SECONDS = 75


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def classify_effective(session: dict[str, Any]) -> str:
    status = session.get("status", "unknown")
    if status == "success":
        return "effective"
    if status == "partial":
        return "partial"
    return "not effective"


def audit_analysis_runs(runs: list[dict[str, Any]]) -> tuple[str, list[str], bool, bool]:
    if not runs:
        return "No analysis runs found.", ["No sessions recorded"], False, False

    sessions = sorted(runs, key=lambda row: row.get("createdAt", ""), reverse=True)
    lines: list[str] = []
    scheduled_ids: list[datetime] = []
    for row in sessions:
        ts = row.get("createdAt", "")
        cycle = row.get("cycleType", "manual")
        status = row.get("status", "unknown")
        local_codex = row.get("localCodexStatus", "n/a")
        market_count = row.get("marketCount", 0)
        line = f"{ts} | cycle={cycle} | markets={market_count} | status={status} | local_codex={local_codex} | effective={classify_effective(row)}"
        lines.append(line)
        if cycle == "scheduled_15m":
            scheduled_ids.append(parse_ts(ts))

    cadence_ok = True
    gap_alerts: list[str] = []
    for index in range(len(scheduled_ids) - 1):
        current = scheduled_ids[index]
        previous = scheduled_ids[index + 1]
        delta = abs((current - previous).total_seconds())
        if delta > SLOT_SECONDS + SLOT_TOLERANCE_SECONDS:
            cadence_ok = False
            expected_next = previous + timedelta(seconds=SLOT_SECONDS)
            gap_alerts.append(
                f"scheduled 15m gap at {previous.isoformat().replace('+00:00', 'Z')} -> {current.isoformat().replace('+00:00', 'Z')} "
                f"(observed {round(delta / 60, 1)}m, expected ~15m)"
            )

    status_lines = []
    if not scheduled_ids:
        cadence_ok = False
        status_lines.append("No scheduled_15m sessions were found in run history.")
    elif len(scheduled_ids) == 1:
        status_lines.append("Only one scheduled_15m session exists; cadence cannot be validated yet.")
    elif gap_alerts:
        status_lines.extend(gap_alerts)
    else:
        status_lines.append("Scheduled 15m cadence is consistent for recorded sessions.")

    latest_status = all(session.get("status") in {"success", "partial"} for session in sessions)
    latest_session = sessions[0]
    status_lines.append(
        f"Latest session at {latest_session.get('createdAt')} was {latest_session.get('status')} "
        f"(cycle={latest_session.get('cycleType')})."
    )

    return "\n".join(lines), status_lines, cadence_ok, latest_status


def run_command(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        return result.returncode
    return 0


def build_execution_plan(args: argparse.Namespace) -> list[list[str]]:
    return [
        [
            sys.executable,
            "-m",
            "sports_edge.cli",
            "run-multi-agent",
            "--source",
            args.source,
            "--target-count",
            str(args.target_count),
        ],
        [
            sys.executable,
            "-m",
            "sports_edge.cli",
            "run-intelligence",
            "--source",
            args.source,
            "--target-count",
            str(args.target_count),
            "--cycle-type",
            "scheduled_15m",
            *(("--no-codex",) if args.no_codex else tuple()),
            *(("--no-queue",) if args.no_queue else tuple()),
        ],
        [sys.executable, "scripts/run_codex_queue.py", "--summary"],
    ]


def load_latest_source() -> str | None:
    payload = load_json(LATEST_PATH)
    return payload.get("sourceMode") or payload.get("source_mode")


def main() -> int:
    parser = argparse.ArgumentParser(description="Polymarket work executor/checker")
    parser.add_argument("--check-only", action="store_true", help="Only run the analysis check and print a report.")
    parser.add_argument("--execute", action="store_true", help="Run the full local agent sequence.")
    parser.add_argument("--source", choices=["fixture", "live"], default="fixture", help="Data source for re-run flow")
    parser.add_argument("--target-count", type=int, default=300)
    parser.add_argument("--no-codex", action="store_true", help="Skip local Codex analysis during re-run flow")
    parser.add_argument("--no-queue", action="store_true", help="Skip codex queue writes during re-run flow")
    parser.add_argument("--show-plan-only", action="store_true", help="Print the recommended execution sequence without running it")
    args = parser.parse_args()

    try:
        runs = load_json(RUNS_PATH)
    except FileNotFoundError:
        print("No analysis run history file found. No historical sessions to evaluate.")
        runs = []

    sessions_text, status_text, cadence_ok, latest_ok = audit_analysis_runs(runs if isinstance(runs, list) else [])
    print("SESSION CHECK")
    print(sessions_text)
    print("\nVALIDATION")
    for item in status_text:
        print(f"- {item}")

    try:
        latest_source = load_latest_source()
        source_msg = latest_source or "unknown"
    except Exception:
        source_msg = "unknown"

    latest_mode = Counter([row.get("cycleType") for row in runs]).most_common(1)[0][0] if runs else "n/a"
    summary = {
        "runs": len(runs),
        "latest_cycle": latest_mode,
        "latest_source_mode": source_msg,
        "scheduled_15m_present": any((row.get("cycleType") == "scheduled_15m") for row in runs),
        "all_recent_sessions_effective": latest_ok,
        "scheduled_cadence_ok": cadence_ok,
    }
    print("\nSUMMARY")
    for key, value in summary.items():
        print(f"- {key}: {value}")

    if args.check_only:
        return 0 if cadence_ok and latest_ok else 2

    plan = build_execution_plan(args)
    print("\nEXECUTION PLAN")
    for idx, command in enumerate(plan, start=1):
        print(f"{idx}. {' '.join(command)}")

    if args.show_plan_only and not args.execute:
        return 0

    if args.execute:
        for command in plan:
            code = run_command(command)
            if code != 0:
                print(f"Execution stopped on command with code {code}")
                return code
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
