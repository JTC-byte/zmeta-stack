from __future__ import annotations
import argparse, json, time, sys
from pathlib import Path
from datetime import datetime
import requests

def parse_ts(s: str) -> float | None:
    try:
        s = s.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None

def iter_lines(paths):
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # skip non-JSON lines (e.g., old pre-fix entries)
                    continue

def main():
    ap = argparse.ArgumentParser(description="Replay NDJSON into /ingest")
    ap.add_argument("--glob", default="data/records/*.ndjson")
    ap.add_argument("--host", default="http://127.0.0.1:8000")
    ap.add_argument("--endpoint", default="/ingest")
    ap.add_argument("--speed", type=float, default=1.0)   # 2.0 = 2x faster
    ap.add_argument("--interval", type=float, default=1.0) # fallback if no timestamps
    ap.add_argument("--limit", type=int, default=0)        # 0 = unlimited
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()

    url = args.host.rstrip("/") + args.endpoint
    files = sorted(Path().glob(args.glob))
    if not files:
        print(f"No files match: {args.glob}", file=sys.stderr)
        sys.exit(1)

    def run_once():
        sent = 0
        last_ts = None
        for obj in iter_lines(files):
            # delay based on timestamps if present
            delay = args.interval
            ts = obj.get("timestamp")
            t = parse_ts(ts) if isinstance(ts, str) else None
            if t is not None and last_ts is not None and t >= last_ts:
                delay = max(0.0, (t - last_ts) / max(args.speed, 0.0001))
            if t is not None:
                last_ts = t

            try:
                r = requests.post(url, json=obj, timeout=5)
                r.raise_for_status()
            except Exception as e:
                print(f"POST error: {e}", file=sys.stderr)

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
