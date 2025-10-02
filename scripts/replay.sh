#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 path/to/records.ndjson [base_url]" >&2
  exit 1
fi

FILE="$1"
BASE_URL="${2:-http://127.0.0.1:8000}"
SECRET="${ZMETA_SHARED_SECRET:-}"
HEADER=()
if [[ -n "$SECRET" ]]; then
  HEADER+=("-H" "X-ZMeta-Secret:$SECRET")
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  curl -sS -X POST "$BASE_URL/ingest" -H "Content-Type: application/json" "${HEADER[@]}" -d "$line"
  sleep 0.1
done < "$FILE"
