#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NO_GUI=0
NO_SIM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-gui)
      NO_GUI=1
      ;;
    --no-sim|--no-simulator)
      NO_SIM=1
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creating virtual environment (.venv)..."
  python3 -m venv "$ROOT/.venv"
fi

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"

echo "Installing dependencies"
pip install -r "$ROOT/requirements.txt"

PIDS=()
launch() {
  "$@" &
  PIDS+=($!)
}

trap 'for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done' EXIT

echo "Starting backend API"
launch python -m uvicorn backend.app.main:app --reload

if [[ $NO_GUI -eq 0 ]]; then
  echo "Starting desktop GUI"
  launch python tools/gui_app.py
fi

if [[ $NO_SIM -eq 0 ]]; then
  echo "Starting RF simulator"
  launch python -m tools.simulators.rf
fi

echo "Components launched. Press Ctrl+C to stop."
wait
