from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


def parse_ts(value: str) -> float | None:
    try:
        trimmed = value.strip()
        if trimmed.endswith("Z"):
            trimmed = trimmed[:-1] + "+00:00"
        return datetime.fromisoformat(trimmed).timestamp()
    except Exception:
        return None


def iter_lines(paths):
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    yield json.loads(stripped)
                except json.JSONDecodeError:
                    # Skip non-JSON lines (e.g., legacy recorder entries).
                    continue


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay NDJSON into /ingest")
    parser.add_argument("--glob", default="data/records/*.ndjson")
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--endpoint", default="/ingest")
    parser.add_argument("--speed", type=float, default=1.0)  # 2.0 = 2x faster
    parser.add_argument("--interval", type=float, default=1.0)  # fallback if no timestamps
    parser.add_argument("--limit", type=int, default=0)  # 0 = unlimited
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    url = args.host.rstrip("/") + args.endpoint
    files = sorted(Path().glob(args.glob))
    if not files:
        print(f"No files match: {args.glob}", file=sys.stderr)
        sys.exit(1)

    def run_once() -> None:
        sent = 0
        last_ts: float | None = None
        for obj in iter_lines(files):
            # delay based on timestamps if present
            delay = args.interval
            ts = obj.get("timestamp")
            timestamp = parse_ts(ts) if isinstance(ts, str) else None
            if timestamp is not None and last_ts is not None and timestamp >= last_ts:
                delay = max(0.0, (timestamp - last_ts) / max(args.speed, 0.0001))
            if timestamp is not None:
                last_ts = timestamp

            try:
                response = requests.post(url, json=obj, timeout=5)
                response.raise_for_status()
            except Exception as exc:
                print(f"POST error: {exc}", file=sys.stderr)

            sent += 1
            if args.limit and sent >= args.limit:
                break
            if delay > 0:
                time.sleep(delay)

    if args.loop:
        while True:
            run_once()
    else:
        run_once()


if __name__ == "__main__":
    main()
