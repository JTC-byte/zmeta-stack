# Phone Tracker Adapter

The phone tracker adapter lets you push a lightweight GPS payload from any mobile automation (iOS Shortcuts, Android Tasker, OwnTracks webhooks, etc.) and have it normalized into ZMeta automatically. Once the adapter fires, the backend emits purple markers and purple alert rings so the live map immediately identifies the phone track.

## Payload format

Send a JSON body with `source_format="phone_tracker_v1"` to `POST /api/v1/ingest`. Required fields are bolded.

```json
{
  "source_format": "phone_tracker_v1",
  "device_id": "jt-phone",
  "timestamp": "2025-01-11T20:15:01Z",
  "lat": 35.2719,
  "lon": -78.6375,
  "alt_m": 88.2,
  "speed_mps": 1.3,
  "heading_deg": 181,
  "accuracy_m": 4.2,
  "battery_pct": 0.77,
  "note": "shortcut push"
}
```

- **`source_format`** must be `phone_tracker_v1` so the adapter picks it up.
- **`timestamp`** should be an ISO-8601 string (`2025-01-11T20:15:01Z`).
- **`lat`/`lon`** are required floats (degrees). `alt_m`, `speed_mps`, `heading_deg`, `accuracy_m`, `battery_pct`, and `confidence` are optional.
- `device_id` populates `sensor_id`. If omitted, the phone defaults to `phone_tracker`.
- Tags automatically include `phone_tracker`, so the UI colors the marker/trail purple. Alerts use the custom rule `phone_tracker_fix`.

## Backend prerequisites

1. Launch the stack (`scripts\dev.ps1` on Windows or `scripts/dev.sh` on macOS/Linux). Make sure the backend is reachable from your phone (same Wi-Fi, firewall open on port 8000).
2. If you enable the optional shared-secret, add it to your phone request header (`X-ZMETA-SECRET`) or query string (`?secret=...`).

## iOS Shortcuts recipe

1. Add **Get Current Location** and **Get Current Date** actions.
2. Use **Dictionary** to build the payload keys shown above.  
   - `timestamp`: from *Get Current Date* formatted as ISO 8601.  
   - `lat`/`lon`: from *Get Current Location*.  
   - `device_id`: pick a descriptive name like `"jt-phone"`.
3. Add **Get Contents of URL**  
   - URL: `http://<laptop-ip>:8000/api/v1/ingest`  
   - Method: POST  
   - Request Body: JSON (use the dictionary)  
   - Headers: set `Content-Type: application/json` (plus `X-ZMETA-SECRET` if needed).
4. Run the Shortcut manually or attach it to an Automation (e.g., time-based, NFC tap, or “Arrive” trigger). Every run drops a purple marker on `/ui/live_map.html`.

## Android Tasker / HTTP Shortcuts

**Tasker example**

1. Profile → Event → Location (set update rate).  
2. Task steps:
   - *Variable Set* `%TS_ISO` using `Java Function -> java.time.Instant->now().toString()` (Tasker 5.15+) or a formatted `%DATE %TIME`.  
   - *HTTP Request* action:  
     - Method: POST  
     - URL: `http://<laptop-ip>:8000/api/v1/ingest`  
     - Body (raw JSON): use Tasker variables
       ```json
       {
         "source_format": "phone_tracker_v1",
         "device_id": "jt-phone",
         "timestamp": "%TS_ISO",
         "lat": %LOCN,
         "lon": %LOCE,
         "alt_m": %LOCA,
         "speed_mps": %LOCSPD,
         "heading_deg": %LOCBEARING
       }
       ```
     - Headers: `Content-Type: application/json` (plus shared-secret header if configured).

**HTTP Shortcuts (open-source app)**

1. Create a new shortcut → Method: POST → URL: `http://<laptop-ip>:8000/api/v1/ingest`.  
2. Under “Request body”, choose JSON and insert the payload fields. Use the app’s *Location* placeholders for `lat`/`lon`.  
3. Enable “Send device location” so the shortcut prompts for GPS access, then save.

## Testing from a laptop

Use PowerShell or curl to verify the adapter before wiring your phone:

```powershell
$body = @{
  source_format = "phone_tracker_v1"
  device_id = "jt-phone"
  timestamp = (Get-Date).ToUniversalTime().ToString("s") + "Z"
  lat = 35.2719
  lon = -78.6375
  speed_mps = 1.3
} | ConvertTo-Json -Compress

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/ingest" -ContentType "application/json" -Method POST -Body $body
```

You should see `{ "ok": true, ... }` plus a purple point on `/ui/live_map.html`.

## Option C: Browser-only client

Prefer to avoid dedicated apps? The repo now includes a tiny web UI that runs entirely in your browser.

1. Make sure the backend is running (`scripts\dev.ps1`) so it serves static files.
2. On your phone (same Wi-Fi), open `http://<laptop-ip>:8000/ui/phone_tracker_client.html`.
3. Enter:
   - Backend URL (auto-fills if you visit via the backend hostname—leave as-is unless you proxy).  
   - Device ID (defaults to `jt-phone`).  
   - Shared secret if you enabled it.
4. Tap **Send Fix**. The page prompts for location permission, gathers a single GPS fix, then POSTs a `phone_tracker_v1` payload using the adapter schema above.
5. Use **Start Auto** / **Stop Auto** to stream updates every 10 seconds while the page stays open.

Everything stays local: the page only POSTs to your backend and never contacts third-party servers. Open `/ui/live_map.html` on your PC to watch the purple marker update in sync.

## Troubleshooting

- Nothing on the map? Hit `/ui/ws_test.html` to confirm the WebSocket is receiving `phone_geo_fix` packets.  
- Adapter not firing? Ensure `source_format` is exactly `phone_tracker_v1` and the payload includes `timestamp`, `lat`, and `lon`.  
- Firewall issues? Allow inbound TCP 8000 on the laptop so your phone can reach the FastAPI server.  
- Update frequency too high? Use your automation app’s interval/geofence controls so you don’t spam the backend while testing.
