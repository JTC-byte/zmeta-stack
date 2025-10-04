# Ingest -> Rules -> Alerts Pipeline

This document summarizes the core data path through the ZMeta stack. The flow is the same whether packets arrive via HTTP, UDP, or one of the bundled simulators.

```
source -> ingest transport -> validation/adaptation -> dispatch -> rules/alerts -> WebSocket/UI & recorder
```

## Entry points

### HTTP (`POST /api/v1/ingest`)
- Implemented in `backend/app/routes/ingest_http.py:13-47`.
- Optional shared-secret header/query enforced through `Settings.verify_shared_secret`.
- Payloads are forwarded to `ingest_payload(..., context="http")` for normalization.

### UDP (`ZMETA_UDP_HOST`:`ZMETA_UDP_PORT`)
- `backend/app/udp.py:11-50` wraps `asyncio.DatagramProtocol`, pushes frames onto a bounded queue, and hands them to `ingest_payload(..., context="udp")`.
- Back-pressure telemetry is surfaced via the metrics provider (`metrics.note_received`, `metrics.note_dropped`).

### Simulators & Replay
- CLI simulators under `tools/simulators/` speak the same HTTP/UDP contracts.
- The NDJSON recorder feeds `scripts/replay.*`, which POST the archived events back through the HTTP ingest route.

## Normalization & sequencing
- `backend/app/ingest.py:24-44` calls `validate_or_adapt`:
  - First tries `schemas.zmeta.ZMeta.model_validate`.
  - Falls back to `tools.ingest_adapters.adapt_to_zmeta` when needed.
  - Manages auto-incrementing `sequence` values via `metrics.next_sequence()`.
- Adapter usage is tracked with `metrics.note_adapter`, while success/failure go into the metrics snapshot for `/api/v1/healthz`.

## Dispatch & recording
- `dispatch_zmeta` broadcasts the validated packet to:
  - `backend/app/ws.hub.broadcast_text` – feeds live WebSocket subscribers (`/ws`).
  - `tools.recorder.NDJSONRecorder.enqueue` – appends to `data/records/`.
- Every accepted packet calls `metrics.note_validated()` so health checks and log consumers can monitor throughput and last-packet age.

## Rules & alert emission
- Normalized payloads run through `tools.rules.rules.apply(...)` (`backend/app/ingest.py:52-66`).
- Each emitted alert passes through `backend/app/state.AlertDeduper` before broadcast, preventing stormy duplicates (3s TTL by default).
- When an alert survives dedupe, it is:
  1. JSON-serialized with `backend/app/json_utils.dumps`.
  2. Broadcast over the same WebSocket hub.
  3. Counted via `metrics.note_alert()`.

## Delivery & back-pressure handling
- The FastAPI WebSocket endpoint (`backend/app/routes/ws_routes.py:17-48`) accepts clients, enforces the optional shared-secret, and then defers to the hub.
- `WSHub` now uses timed `queue.put` calls with structured log warnings when clients fall behind (`backend/app/ws.py:54-111`).
  - Persistent slow consumers are disconnected once `max_backpressure_retries` is exceeded.
  - Drops and sends are reflected in `metrics.snapshot()` and surfaced through `/api/v1/healthz`.

## Extending the pipeline
- **New sources**: call `ingest_payload` directly (after populating a `Services` bundle) or reuse the HTTP/UDP adapters.
- **New adapters**: register in `tools/ingest_adapters` so `validate_or_adapt` can discover them automatically.
- **New rules**: add YAML under `config/rules/` and reload via the control scripts; alerts instantly inherit dedupe and broadcast behaviour.
- **Alternate storage/analytics**: hook additional sinks inside `dispatch_zmeta` (e.g., forward to Kafka) by extending the `Services` dependency or by registering FastAPI dependencies that decorate the dispatch step.

## Related modules
- `backend/app/config.py` – typed settings, shared-secret helpers, and URLs.
- `backend/app/services.py` – provides `MetricsProvider`, recorder, hub, and rules to the ingest path.
- `backend/app/metrics.py` – thread-safe counters/snapshots reported via `/status` and `/healthz`.
- `docs/` (this file) – keep architecture notes here as the pipeline evolves.
