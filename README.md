# ZMeta Stack — Live Map • Ingest • Rules • Alerts

A lightweight ISR workbench:
**ingest → normalize to ZMeta → rules/alerts → WebSocket → live Leaflet map → record to NDJSON**.

- FastAPI backend: REST **`/ingest`**, UDP **`:5005`**, WebSocket **`/ws`**
- Same-origin UI served at **`/ui/live_map.html`** (root `/` redirects)
- **Adapters** normalize simulator/KLV payloads to **ZMeta**
- **YAML rules** raise alerts (info/warn/crit) that pulse on the map
- Recorder writes **NDJSON** under `data/records/` (gitignored)

> Dev defaults: permissive CORS, no auth — great for local work. Lock down before exposing externally.

---

## Quick start (Windows PowerShell)

```powershell
# Clone & enter
git clone https://github.com/JTC-byte/zmeta-stack.git
cd zmeta-stack

# Create venv + install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the backend (IMPORTANT: use the venv’s Python)
python -m uvicorn backend.app.main:app --reload
```

Open the map: **http://127.0.0.1:8000** → redirects to `/ui/live_map.html`

> **Windows note:** Every new terminal starts without the venv.  
> Reactivate before running:
> ```powershell
> .\.venv\Scripts\Activate.ps1
> python -m uvicorn backend.app.main:app --reload
> ```

### Send data

**A) RF simulator (module run)**
```powershell
# new terminal? activate venv again first
.\.venv\Scripts\Activate.ps1
python -m tools.simulators.rf
```

**B) KLV simulator (module run)**
```powershell
.\.venv\Scripts\Activate.ps1
python -m tools.simulators.klv
```

**C) Single REST packet (PowerShell)**
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

# run through the venv’s Python so the reloader uses the right interpreter
python -m uvicorn backend.app.main:app --reload

# in another shell (activate venv), run a simulator:
#   python -m tools.simulators.rf
#   python -m tools.simulators.klv
```

---

## One-click scripts (optional; coming soon)

You’ll be able to use:
- **Windows:** `scripts/dev.cmd` (or `scripts/dev.ps1`)
- **macOS/Linux:** `scripts/dev.sh`

They will: create/activate `.venv`, install deps, open the UI, and run the server.

---

## Endpoints

- `GET /` → redirects to `/ui/live_map.html`
- `GET /ui/live_map.html` → live map UI (Leaflet + WS)
- `GET /ui/ws_test.html` → prints every WebSocket message
- `GET /favicon.ico` → alias to `/ui/favicon.svg` (tab icon)
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
   - **Thermal** (°C) → `data.type: "thermal_hotspot"`
   - **KLV-like dicts** → via `tools/translators/klv_to_zmeta.py`

Resulting ZMeta is:
- broadcast over WS,  
- evaluated by rules,  
- recorded to NDJSON.

---

## Rules & alerts

- YAML file: **`config/rules.yaml`**
- Examples:
  - RF in the **915 MHz** ISM band
  - High-confidence RF
  - Thermal hotspot ≥ 70 °C
  - AOI example near default sim coordinates

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

## Project layout

```
backend/app/main.py                # FastAPI app, WS hub, routes, favicon alias
config/rules.yaml                  # YAML rules
schemas/zmeta.py                   # ZMeta Pydantic models
tools/recorder.py                  # NDJSON recorder (hourly rotate)
tools/ingest_adapters.py           # normalize inbound payloads → ZMeta
tools/rules.py                     # load/apply rules; de-dup alerts
tools/simulators/{rf.py, klv.py}   # simulators (module-run)
tools/translators/klv_to_zmeta.py  # KLV → ZMeta translator
zmeta_map_dashboard/live_map.html  # Leaflet map UI (served from /ui/)
zmeta_map_dashboard/ws_test.html   # WebSocket message viewer
zmeta_map_dashboard/favicon.svg    # tab icon (aliased at /favicon.ico)
data/records/                      # recorder outputs (gitignored)
requirements.txt                   # runtime/dev deps
```

---

## Deterministic installs (lock file)

**Why:** ensure teammates/CI get the *same* versions every time.

**A) Quick freeze**
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip freeze | Out-File -Encoding utf8 requirements.lock.txt
# later:
pip install -r requirements.lock.txt
```

**B) pip-tools with hashes**
```powershell
pip install pip-tools
pip-compile --generate-hashes -o requirements.lock.txt requirements.txt
pip install --require-hashes -r requirements.lock.txt
# refresh later:
pip-compile --upgrade --generate-hashes -o requirements.lock.txt requirements.txt
```

---

## Troubleshooting

- **“WS: connected” but stats don’t move**  
  Always open via backend origin: `http://127.0.0.1:8000/ui/live_map.html`.  
  Opening the file directly with `file://…` blocks `/healthz`.

- **No markers**  
  Check `/healthz` → `validated_total` should increase.  
  If only `udp_received_total` rises, payload likely needs an adapter tweak.

- **No alert pulses**  
  Confirm adapted packet matches rule fields.  
  Use `/ui/ws_test.html` to see live WS messages (feature + alert JSON).

- **On Windows: `ModuleNotFoundError: No module named 'yaml'`**  
  That’s uvicorn using a global Python.  
  Activate the venv and launch via:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  python -m uvicorn backend.app.main:app --reload
  ```

- **Too many repeated alerts**  
  Short-window de-dup is set to **3s** — adjust `AlertDeduper(ttl_s=3.0)` in `backend/app/main.py`.

---

## Dev hygiene

- Use a virtualenv  
- Keep `data/records/` out of Git  
- Ignore `__pycache__/`, `.pyc` (already in `.gitignore`)  
- Consider `ruff` / `black` / `pre-commit` for consistent formatting
