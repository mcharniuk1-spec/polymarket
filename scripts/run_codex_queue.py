#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sports_edge.codex_queue import drain_codex_queue, queue_summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain queued local Codex intelligence backfills")
    parser.add_argument("--watch", action="store_true", help="Poll and drain until stopped")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--summary", action="store_true", help="Only print queue summary")
    args = parser.parse_args()

    if args.summary:
        print(json.dumps(queue_summary(), indent=2, sort_keys=True))
        return 0

    while True:
        result = drain_codex_queue(limit=args.limit)
        print(json.dumps(result, indent=2, sort_keys=True))
        if not args.watch:
            return 0 if result["status"] in {"success", "partial", "empty", "skipped"} else 1
        time.sleep(max(args.poll_seconds, 1))


if __name__ == "__main__":
    raise SystemExit(main())
