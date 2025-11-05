# ZMeta Stack - Live Map - Ingest - Rules - Alerts

A lightweight ISR workbench:
**ingest -> normalize to ZMeta -> rules/alerts -> WebSocket -> live Leaflet map -> record to NDJSON**.

- FastAPI backend: REST **`/api/v1/ingest`**, UDP **`:5005`**, WebSocket **`/ws`**
- Same-origin UI served at **`/ui/live_map.html`** (root `/` redirects)
- **Adapters** normalize simulator/KLV payloads to **ZMeta**
- **YAML rules** raise alerts (info/warn/crit) that pulse on the map
- Recorder writes **NDJSON** under `data/records/` (gitignored)

> Dev defaults: permissive CORS, no auth - great for local work. Lock down before exposing externally.

---
## Documentation

- [Ingest -> Rules -> Alerts pipeline](docs/ingest_pipeline.md) (served live at `/docs/local/ingest_pipeline` and aliased at `/docs/pipeline`)


## Quick start (Windows PowerShell)

### One-command startup

```powershell
scripts\dev.ps1
```

### Manual setup

```powershell
# Clone & enter
git clone https://github.com/JTC-byte/zmeta-stack.git
cd zmeta-stack

# Create venv + install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the backend (IMPORTANT: use the venv's Python)
python -m uvicorn backend.app.main:app --reload
```

Open the map: **http://127.0.0.1:8000** -> redirects to `/ui/live_map.html`

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

**B) Thermal simulator (module run)**
```powershell
.\.venv\Scripts\Activate.ps1
python -m tools.simulators.thermal
```

**C) KLV simulator (module run)**
```powershell
.\.venv\Scripts\Activate.ps1
python -m tools.simulators.klv
```
**D) GUI control panel (module run)**
```powershell
.\.venv\Scripts\Activate.ps1
python -m tools.gui_app
# Docs button opens http://127.0.0.1:8000/docs/pipeline
```


**E) Single REST packet (PowerShell)**
```powershell
$body = @{
  sensor_id="rf_sim_001"; modality="rf"; timestamp="2025-01-01T00:00:00Z"
  source_format="zmeta"; confidence=0.95
  location=@{ lat=35.271; lon=-78.637 }
  data=@{ type="rf_detection"; value=@{ frequency_hz=915000000; rssi_dbm=-45.2; bandwidth_hz=20000; dwell_s=0.8 } }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/ingest" -Method POST -ContentType "application/json" -Body $body
```

You should see a marker near **[35.271, -78.637]** (info markers = blue, warn = orange, crit = red).
(blue=info, orange=warn, red=crit).

---

## Quick start (macOS / Linux)

```bash
git clone https://github.com/JTC-byte/zmeta-stack.git
cd zmeta-stack
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# run through the venv's Python so the reloader uses the right interpreter
python -m uvicorn backend.app.main:app --reload

# in another shell (activate venv), run a simulator:
#   python -m tools.simulators.rf
#   python -m tools.simulators.klv
```

---

## Helper scripts

- **Windows:** `scripts/dev.ps1` (use `-NoGui` or `-NoSimulator`)
- **macOS/Linux:** `scripts/dev.sh` (supports `--no-gui` / `--no-sim`)

Both scripts ensure the virtual environment exists, install requirements, then launch the backend, GUI, and RF simulator. Stop them with `Ctrl+C`.

---

## Configuration

Environment variables let you tune ports, URLs, and simulator targets:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ZMETA_APP_TITLE` | `ZMeta Backend` | UI title surfaced via `/api/v1/status` and docs. |
| `ZMETA_UDP_HOST` | `0.0.0.0` | Bind address for the UDP listener. |
| `ZMETA_UDP_PORT` | `5005` | UDP port for ingest + simulators. |
| `ZMETA_UDP_QUEUE_MAX` | `4096` | Max UDP queue depth for the background listener. |
| `ZMETA_UI_BASE_URL` | `http://127.0.0.1:8000` | Base URL used for helper prints and GUI hints. |
| `ZMETA_WS_GREETING` | `Connected to ZMeta WebSocket` | Text sent after a client connects. |
| `ZMETA_CORS_ORIGINS` | `*` | Comma-separated origins allowed by FastAPI CORS middleware. |
| `ZMETA_SIM_UDP_HOST` | (unset) | Optional override for simulator UDP target host. |
| `ZMETA_UDP_TARGET_HOST` | `127.0.0.1` | Default simulator UDP target when override not set. |
| `ZMETA_SHARED_SECRET` | (empty) | Optional shared secret required for `/ingest` and `/ws`. |
| `ZMETA_AUTH_HEADER` | `x-zmeta-secret` | Header name to read the shared secret from. |
| `ZMETA_ENV` | `dev` | Hint for environment-specific behavior (e.g., prod CORS tightening). |
| `ZMETA_WS_QUEUE` | `64` | Max per-client WebSocket buffer size before dropping messages. |
| `ZMETA_RECORDER_RETENTION_HOURS` | (unset) | If set, older NDJSON files are pruned after this many hours. |

A starter `.env.example` is included - copy it to `.env` and tweak as needed.

## Appearance

  - Web HUD: use the Appearance panel (top-right) to select `nostromo`, `shinjuku`, or `section9` and toggle grid, scanlines, and glow. Choices persist via localStorage.
  - Desktop GUI: currently uses the default ttk styling; appearance controls are paused for now. Connection preferences (base URL, secret) still persist in `~/.inceptio_prefs.json`.



### Secure mode

Set `ZMETA_SHARED_SECRET` (and optionally `ZMETA_AUTH_HEADER`) to require clients to present a shared secret.

- REST clients: include the header `X-ZMeta-Secret: <value>` (or whichever header you configure).
- WebSocket clients: pass the header or append `?secret=<value>` to `/ws`.
- `/healthz` surfaces `auth_mode`, `auth_header`, and `allowed_origins` so you can confirm the mode.

When hardening a deployment, also tighten `ZMETA_CORS_ORIGINS` and set `ZMETA_ENV=prod`.

## Endpoints

- GET / -> redirects to /ui/live_map.html
- GET /ui/live_map.html -> live map UI (Leaflet + WS)
- GET /ui/ws_test.html -> prints every WebSocket message
- GET /favicon.ico -> alias to /ui/favicon.svg (tab icon)
- GET /api -> legacy redirect to /api/v1/status
- GET /healthz -> legacy redirect to /api/v1/healthz
- GET /api/v1/status -> lightweight service status ({ "status": ..., "clients": ... })
- GET /api/v1/healthz -> detailed ingest/WebSocket metrics
- POST /api/v1/ingest -> accepts JSON; validates as **ZMeta** or auto-**adapts** then validates
- GET /api/v1/rules -> list loaded rule names
- POST /api/v1/rules/reload -> reload config/rules.yaml without restarting

---

## Adapters (normalize "anything" -> ZMeta)

**Location:** `tools/ingest_adapters.py`  
Flow:
1. Try native ZMeta validation.
2. If validation fails, try adapters:
   - **Simulated RF** (MHz -> Hz) -> `data.type: "rf_detection"`
   - **Thermal** (degC) -> `data.type: "thermal_hotspot"`
   - **KLV-like dicts** -> via `tools/translators/klv_to_zmeta.py`

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
  - Thermal hotspot >= 70 degC
  - AOI example near default sim coordinates

Map UI shows:
You should see a marker near **[35.271, -78.637]** (info markers = blue, warn = orange, crit = red).
- **Stats panel** (WS status, clients, EPS, alerts)  
- Marker **tooltips** with modality plus relative/ISO timestamps  
- Track trails with age-based fade, plus auto-follow and Fit All controls

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
tools/ingest_adapters.py           # normalize inbound payloads -> ZMeta
tools/rules.py                     # load/apply rules; de-dup alerts
tools/simulators/{rf.py, klv.py}   # simulators (module-run)
tools/translators/klv_to_zmeta.py  # KLV -> ZMeta translator
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

- **"WS: connected" but stats don't move**  
  Always open via backend origin: `http://127.0.0.1:8000/ui/live_map.html`.  
  Opening the file directly with `file://...` blocks `/healthz`.

- **No markers**  
  Check `/healthz` -> `validated_total` should increase.  
  If only `udp_received_total` rises, payload likely needs an adapter tweak.

- **No alert pulses**  
  Confirm adapted packet matches rule fields.  
  Use `/ui/ws_test.html` to see live WS messages (feature + alert JSON).

- **On Windows: `ModuleNotFoundError: No module named 'yaml'`**  
  That's uvicorn using a global Python.  
  Activate the venv and launch via:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  python -m uvicorn backend.app.main:app --reload
  ```

- **Too many repeated alerts**  
  Short-window de-dup is set to **3s** - adjust `AlertDeduper(ttl_s=3.0)` in `backend/app/main.py`.

---

## Dev hygiene

- Use a virtualenv  
- Keep `data/records/` out of Git  
- Ignore `__pycache__/`, `.pyc` (already in `.gitignore`)  
- Consider `ruff` / `black` / `pre-commit` for consistent formatting





## Replay recorded data

- Bash: `scripts/replay.sh data/records/20250101_12.ndjson http://127.0.0.1:8000`
- PowerShell: `scripts/replay.ps1 -Path data/records/20250101_12.ndjson -BaseUrl http://127.0.0.1:8000`


## Containers

- Build locally: `docker build -t zmeta .`
- Dev compose: `docker-compose up` (hot reload on port 8000).


---

## Future Updates

Here is what we have queued up, in rough priority order:

1. **Phone Tracker Integration** – ingest mobile device feeds for live map display and alerting.
2. **GUI Auth Support** – shared-secret entry in the desktop control panel with secure header/query handling.
3. **Expanded Health Dashboard** – surface adapter counts, WebSocket queue drops, and per-client stats.
4. **Rules Management UI** – list/add/reload detection rules from the GUI instead of YAML-only workflow.
5. **Electron/Tauri Frontend** – TypeScript/React desktop bundle with built-in map, health, and rules pages.
6. **Enhanced Visualization** – clustering, timeline playback, and live metrics charts.
