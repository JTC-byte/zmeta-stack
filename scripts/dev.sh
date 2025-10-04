#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NO_GUI=0
NO_SIM=0
CHECK_HEALTH=0
HEALTH_BASE_URL=""
HEALTH_ENDPOINT=""
HEALTH_TIMEOUT=5
HEALTH_RETRIES=15
HEALTH_POLL_DELAY=1
HEALTH_OUTPUT="pretty"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-gui)
      NO_GUI=1
      ;;
    --no-sim|--no-simulator)
      NO_SIM=1
      ;;
    --check-health)
      CHECK_HEALTH=1
      ;;
    --health-base-url)
      if [[ $# -lt 2 ]]; then
        echo "--health-base-url requires an argument" >&2
        exit 1
      fi
      CHECK_HEALTH=1
      HEALTH_BASE_URL="$2"
      shift
      ;;
    --health-endpoint)
      if [[ $# -lt 2 ]]; then
        echo "--health-endpoint requires an argument" >&2
        exit 1
      fi
      CHECK_HEALTH=1
      HEALTH_ENDPOINT="$2"
      shift
      ;;
    --health-timeout)
      if [[ $# -lt 2 ]]; then
        echo "--health-timeout requires an argument" >&2
        exit 1
      fi
      CHECK_HEALTH=1
      HEALTH_TIMEOUT="$2"
      shift
      ;;
    --health-retries)
      if [[ $# -lt 2 ]]; then
        echo "--health-retries requires an argument" >&2
        exit 1
      fi
      CHECK_HEALTH=1
      HEALTH_RETRIES="$2"
      shift
      ;;
    --health-delay)
      if [[ $# -lt 2 ]]; then
        echo "--health-delay requires an argument" >&2
        exit 1
      fi
      CHECK_HEALTH=1
      HEALTH_POLL_DELAY="$2"
      shift
      ;;
    --health-output)
      if [[ $# -lt 2 ]]; then
        echo "--health-output requires an argument" >&2
        exit 1
      fi
      CHECK_HEALTH=1
      HEALTH_OUTPUT="$2"
      shift
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

cleanup() {
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT

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

if [[ $CHECK_HEALTH -eq 1 ]]; then
  echo "Running API health check (up to ${HEALTH_RETRIES} attempts)"
  health_cmd=(python "$ROOT/scripts/run_health_check.py" --timeout "$HEALTH_TIMEOUT" --output "$HEALTH_OUTPUT")
  if [[ -n "$HEALTH_BASE_URL" ]]; then
    health_cmd+=(--base-url "$HEALTH_BASE_URL")
  fi
  if [[ -n "$HEALTH_ENDPOINT" ]]; then
    health_cmd+=(--endpoint "$HEALTH_ENDPOINT")
  fi

  attempt=1
  until "${health_cmd[@]}"; do
    if (( attempt >= HEALTH_RETRIES )); then
      echo "Health check failed after ${HEALTH_RETRIES} attempts." >&2
      exit 1
    fi
    attempt=$((attempt + 1))
    echo "Health check not ready yet (attempt ${attempt}/${HEALTH_RETRIES}); retrying in ${HEALTH_POLL_DELAY}s..."
    sleep "$HEALTH_POLL_DELAY"
  done
  echo "Health check succeeded."
fi


echo "Components launched. Press Ctrl+C to stop."
wait
