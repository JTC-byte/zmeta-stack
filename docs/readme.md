# ZMeta Stack (local overview)

This page is the quick on-ramp for running and validating the local stack. For the full data path details, see [Ingest -> Rules -> Alerts pipeline](/docs/local/ingest_pipeline).

## What runs
- Backend: FastAPI (`backend/app/main.py`) serving HTTP ingest, WS broadcast, and docs.
- Transports: UDP listener (`backend/app/udp.py`) and WebSocket hub (`/ws`) for live map updates.
- Rules: YAML-driven rules engine (`tools/rules.py`) with alert dedupe (`backend/app/state.py`).
- Recorder: NDJSON sink under `data/records/` with optional retention trimming.
- UI: Leaflet-based live map at `/ui/live_map.html` plus helper pages (`/ui/ws_test.html`, `/ui/phone_tracker_client.html`).

## Start/stop
- Dev scripts: `scripts/dev.ps1` (Windows) or `scripts/dev.sh` (macOS/Linux) to launch uvicorn + simulators.
- Manual: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload`.
- Stopping gracefully closes UDP, recorder, and WS sender tasks.

## Health + status
- `/healthz` — JSON health snapshot (WS clients, EPS, last packet age, adapter and WS counters).
- `/api/v1/status` — basic status + adapter counts + WS queue/drop stats.
- `/docs/local` — rendered docs index (this page included).
- `/docs/pipeline` — direct link to the pipeline flow doc.

## Data flow (short form)
1) HTTP/UDP ingest -> `ingest_payload` validates/adapts -> auto sequence -> recorder enqueue + WS broadcast.  
2) Rules run -> alerts deduped -> WS broadcast.  
3) Metrics track receive/validate/drop/WS stats; `/healthz` polls them for the HUD.

See the pipeline doc for per-module links and extension points.

## Auth
- Shared-secret is optional; set `ZMETA_SHARED_SECRET` to require `x-zmeta-secret` (or `?secret=` for WS/ingest).
- When enabled, both HTTP ingest and WS connections must present the secret.

## Files to know
- `config/rules.yaml` — rule definitions.
- `data/records/` — NDJSON archives (hourly files).
- `scripts/check_endpoints.py` — quick probe for `/docs/local`, `/docs/pipeline`, and ingest.
