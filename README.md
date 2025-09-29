# ZMeta Stack — Live Map • Ingest • Rules • Alerts

A lightweight pipeline for ISR-style telemetry:
**ingest → normalize to ZMeta → rules/alerts → WebSocket → live Leaflet map → record to NDJSON**.

- FastAPI backend: REST **`/ingest`**, UDP **`:5005`**, WebSocket **`/ws`**
- Same-origin UI served at **`/ui/live_map.html`**
- Adapters normalize simulator/KLV payloads to **ZMeta**
- YAML rules raise **alerts** (info/warn/crit) that pulse on the map
- Recorder writes **NDJSON** under `data/records/`

> Dev defaults: wide-open CORS and no auth. Fine for local use; tighten before exposing beyond your machine.

---

## Quick start (Windows PowerShell)

```powershell
# clone & enter
git clone https://github.com/JTC-byte/zmeta-stack.git
cd zmeta-stack

# create venv + install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# run the backend (prints handy links)
python -m uvicorn backend.app.main:app --reload


> **Windows:** Each new terminal starts without the venv.
> Reactivate before running:
> ```powershell
> .\.venv\Scripts\Activate.ps1
> python -m uvicorn backend.app.main:app --reload
> ```

Open the map: **http://127.0.0.1:8000**  
(redirects to `/ui/live_map.html`)

### Send data

**Option A — RF simulator (UDP)**

- **Before repo cleanup:**
  ```powershell
  python simulated_rf_broadcaster.py
  ```
- **After cleanup (recommended module layout):**
  ```powershell
  python -m tools.simulators.rf
  ```

**Option B — Single REST packet (PowerShell)**

```powershell
$body = @{
  sensor_id="rf_sim_001"; modality="rf"; timestamp="2025-01-01T00:00:00Z"
  source_format="zmeta"; confidence=0.95
  location=@{ lat=35.271; lon=-78.637 }
  data=@{ type="rf_detection"; value=@{ frequency_hz=915000000; rssi_dbm=-45.2; bandwidth_hz=20000; dwell_s=0.8 } }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest" -Method POST -ContentType "application/json" -Body $body
```

You should see a marker near **[35.271, −78.637]** and **pulse rings** on alerts  
(blue=info, orange=warn, red=crit).

---

## Quick start (macOS / Linux)

```bash
git clone https://github.com/JTC-byte/zmeta-stack.git
cd zmeta-stack
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
# open http://127.0.0.1:8000
# then run:  python simulated_rf_broadcaster.py   (before cleanup)
# or:        python -m tools.simulators.rf        (after cleanup)
```

---

## Endpoints

- `GET /` → redirects to `/ui/live_map.html`
- `GET /ui/live_map.html` → live map UI (Leaflet + WS)
- `GET /ui/ws_test.html` → prints every WebSocket message
- `GET /healthz` → status/metrics, for example:
  ```json
  {
    "status": "ok",
    "clients": 1,
    "udp_received_total": 123,
    "validated_total": 120,
    "dropped_total": 3,
    "alerts_total": 42,
    "eps_1s": 1.0,
    "eps_10s": 0.8,
    "last_packet_age_s": 0.14
  }
  ```
- `POST /ingest` → accepts JSON; validates as **ZMeta** or auto-**adapts** then validates
- `GET /rules` → list loaded rule names
- `POST /rules/reload` → reload `config/rules.yaml` without restarting

---

## Adapters (normalize “anything” → ZMeta)

**Location:** `tools/ingest_adapters.py`

Flow:
1. Try native ZMeta validation.
2. If validation fails, try adapters:
   - **Simulated RF** (MHz → Hz) → `data.type: "rf_detection"`
   - **Simulated Thermal** (°C) → `data.type: "thermal_hotspot"`
   - **KLV-like dicts** → via `tools/translators/klv_to_zmeta.py` (after cleanup)

Resulting ZMeta is:
- broadcast over WS,  
- evaluated by rules,  
- recorded to NDJSON.

---

## Rules & alerts

- YAML file: **`config/rules.yaml`**
- Examples include:
  - RF in the **915 MHz** ISM band
  - High-confidence RF
  - Thermal hotspot ≥ 70 °C
  - A small AOI example near the default sim location

Map UI shows:
- **Pulse rings** per alert (severity-colored)  
- **Stats panel** (WS status, clients, EPS, alerts)  
- Marker **tooltips** (freq/RSSI/confidence, etc.)

Reload rules at runtime:

```powershell
Invoke-RestMethod -Method POST http://127.0.0.1:8000/rules/reload
```

---

## Recorder

Writes hourly-rotated NDJSON to `data/records/YYYYMMDD_HH.ndjson`.

Git hygiene:
- `data/records/` is **ignored** by `.gitignore`  
- Do not commit NDJSON logs

---

## Project layout (current → after cleanup)

**Current (works today):**

```
backend/              FastAPI app
config/rules.yaml     Rules (YAML)
tools/                recorder.py, rules.py, ingest_adapters.py
zmeta_map_dashboard/  live_map.html, ws_test.html
data/records/         Recorder outputs (gitignored)

# loose scripts at root (today):
simulated_rf_broadcaster.py
fake_metadata_broadcaster.py
klv_broadcaster.py
klv_to_zmeta.py
klv_sample_input.py
udp_listener.py
z_meta_schema.py
```

**After cleanup (recommended):**

```
backend/app/main.py
config/rules.yaml
schemas/zmeta.py                 # ← from z_meta_schema.py
tools/recorder.py
tools/ingest_adapters.py
tools/rules.py
tools/simulators/{rf.py, fake_meta.py, klv.py}
tools/translators/klv_to_zmeta.py
zmeta_map_dashboard/{live_map.html, ws_test.html}
data/records/ (gitignored)
data/samples/klv_sample_input.py
examples/legacy/udp_listener.py
tests/test_klv_translation.py
```

---

## Troubleshooting

- **Map shows “WS: connected” but stats don’t move**  
  Always open via the backend origin: `http://127.0.0.1:8000/ui/live_map.html`.  
  Opening the file directly with `file://…` will block `/healthz` fetches.

- **No markers**  
  Check `/healthz` → `validated_total` should rise as packets arrive.  
  If only `udp_received_total` rises, your payload likely needs an adapter tweak.

- **No alert pulses**  
  Confirm the packet (or its adapted form) matches your rule fields.  
  Use `/ui/ws_test.html` to see live WS messages (feature + alert JSON).

- **Too many repeated alerts**  
  Short-window de-dup is set to **3s**. Adjust in `backend/app/main.py` (search for `AlertDeduper(ttl_s=3.0)`).

---

## “Run at home” reminder

- Start server:
  ```
    python -m uvicorn backend.app.main:app --reload
  ```
- Open:
  ```
  http://127.0.0.1:8000
  ```
- Simulate:
  ```
  python simulated_rf_broadcaster.py         # before cleanup
  python -m tools.simulators.rf              # after cleanup
  ```

---

## Roadmap (short)

- Alert **toast** popup with rule name/message  
- **/alerts** ring buffer (backfill on map load)  
- **Replay** a recorded NDJSON over WS  
- Adapter registry v1 + YAML mapping DSL  
- AOI polygon editor in UI  
- Simple API key for ingest/WS (dev → prod)

---

## Dev hygiene

- Use a virtualenv  
- Keep `data/records/` out of Git  
- Consider adding `ruff` / `black` / `pre-commit` for consistent formatting
