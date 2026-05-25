#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sports_edge.intelligence import main as intelligence_main  # noqa: E402
from sports_edge.codex_queue import drain_codex_queue  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or watch Polymarket intelligence cycles")
    parser.add_argument("--watch", action="store_true", help="Run repeatedly until stopped")
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--cycle-type", choices=["scheduled_15m", "post_ingestion", "manual"], default="manual")
    parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--target-count", type=int, default=300)
    parser.add_argument("--no-codex", action="store_true")
    parser.add_argument("--no-queue", action="store_true")
    parser.add_argument("--no-drain-queue", action="store_true")
    parser.add_argument("--queue-drain-limit", type=int, default=12)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    forwarded = [
        "--cycle-type",
        args.cycle_type,
        "--source",
        args.source,
        "--target-count",
        str(args.target_count),
    ]
    if args.no_codex:
        forwarded.append("--no-codex")
    if args.no_queue:
        forwarded.append("--no-queue")
    if args.no_persist:
        forwarded.append("--no-persist")

    if not args.watch:
        result = intelligence_main(forwarded)
        if not args.no_drain_queue:
            print(json.dumps(drain_codex_queue(limit=args.queue_drain_limit), indent=2, sort_keys=True))
        return result

    while True:
        watch_args = ["--cycle-type", "scheduled_15m", "--source", args.source, "--target-count", str(args.target_count)]
        if args.no_codex:
            watch_args.append("--no-codex")
        if args.no_queue:
            watch_args.append("--no-queue")
        if args.no_persist:
            watch_args.append("--no-persist")
        intelligence_main(watch_args)
        if not args.no_drain_queue:
            print(json.dumps(drain_codex_queue(limit=args.queue_drain_limit), indent=2, sort_keys=True))
        time.sleep(max(args.interval_seconds, 1))


if __name__ == "__main__":
    raise SystemExit(main())
