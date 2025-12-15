# Troubleshooting quick hits

Use these checks when the HUD or ingest path looks off.

## Fast checks
- Service up: `curl -s http://127.0.0.1:8000/healthz | jq` (should return `status: ok`).
- Docs render: open `http://127.0.0.1:8000/docs/local` (HTML expected).
- Ingest happy-path: run `python scripts/check_endpoints.py --verbose` while the app is up.

## WebSocket issues
- Symptom: HUD shows `WS: closed/error` or markers stop moving.
- Verify backend WS: `curl -i http://127.0.0.1:8000/ws` should return an HTTP 426/400 (expected without WS upgrade).  
- If shared-secret is on, make sure the HUD query string includes `?secret=...` or the header is forwarded.
- Watch logs for `zmeta.ws` `backpressure` warnings; slow clients are auto-dropped after repeated queue timeouts.

## No data on the map
- Check `/healthz` fields: `validated_total` should increment; `last_packet_age_s` should be small.
- If `udp_received_total` rises but `validated_total` stays 0, incoming frames are not valid ZMeta or adapters failed.
- Use `scripts/check_endpoints.py` ingest probe, or post a known-good payload:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/v1/ingest \
    -H "Content-Type: application/json" \
    -d '{"timestamp":"2025-01-01T00:00:00Z","sensor_id":"ci-smoke","modality":"rf","location":{"lat":42,"lon":-71},"data":{"type":"rf_detection","value":{"frequency_hz":915000000}},"source_format":"zmeta","schema_version":"1.0"}'
  ```

## Auth / shared secret errors
- If ingest/WS returns 401/4401, set `ZMETA_SHARED_SECRET` in the backend env and send the same value via `x-zmeta-secret` (HTTP) or `?secret=` (WS).
- Clear stale query params in the HUD URL if you recently disabled the secret.

## Recorder / retention
- Recorder drops are logged as `zmeta.recorder` warnings with `dropped` count. If it happens, lower ingest rate or increase queue size in code.
- Retention: set `ZMETA_RECORDER_RETENTION_HOURS` to auto-prune old `data/records/*.ndjson`.

## Phone tracker connectivity
- Backend must be reachable at `http://<laptop-ip>:8000` from the phone; allow inbound TCP 8000 on the OS firewall.
- Open `http://<laptop-ip>:8000/docs` then `http://<laptop-ip>:8000/ui/phone_tracker_client.html` from the phone to confirm reachability.
- Watch uvicorn logs for GET/POST entries to ensure the phone is hitting the backend.

## Where to dig deeper
- Pipeline internals: [/docs/local/ingest_pipeline](/docs/local/ingest_pipeline)
- Adapter specifics: [/docs/local/phone_tracker_adapter](/docs/local/phone_tracker_adapter)
