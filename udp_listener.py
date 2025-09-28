import socket
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from threading import Thread
import uvicorn

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
received_packets = []

@app.get("/")
async def root():
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ZMeta Map</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            html, body, #map { height: 100%; margin: 0; padding: 0; }
        </style>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    </head>
    <body>
        <div id="map"></div>
        <script>
            const map = L.map('map').setView([35.0, -78.0], 14);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
            }).addTo(map);

            const markers = {};

            function getColor(sensorId) {
                if (sensorId === 'klv_source_001') return 'green';
                if (sensorId === 'klv_source_002') return 'blue';
                if (sensorId === 'klv_source_003') return 'red';
                if (sensorId === 'sim_rf_01') return 'orange';
                return 'gray';
            }

            async function updateMap() {
                const response = await fetch('/map');
                const data = await response.json();

                for (const f of data.features) {
                    const [lon, lat] = f.geometry.coordinates;
                    const id = f.properties.sensor_id;
                    const color = getColor(id);

                    if (markers[id]) {
                        map.removeLayer(markers[id]);
                    }

                    const circle = L.circleMarker([lat, lon], {
                        radius: 8,
                        color: color,
                        fillColor: color,
                        fillOpacity: 1
                    }).addTo(map).bindPopup("Sensor ID: " + id);

                    markers[id] = circle;
                }
            }

            setInterval(updateMap, 1000);
            updateMap();
        </script>
    </body>
    </html>
    """, media_type="text/html")


@app.get("/map")
async def get_map_data():
    return {
        "type": "FeatureCollection",
        "features": received_packets[-20:]
    }

def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print("[+] Listening on UDP", UDP_PORT)

    while True:
        try:
            data, _ = sock.recvfrom(4096)
            payload = json.loads(data.decode())

            # Try both top-level and nested location
            location = payload.get("location") or payload.get("data", {}).get("location", {})
            lat = location.get("lat") or location.get("latitude")
            lon = location.get("lon") or location.get("longitude")

            if lat is not None and lon is not None:
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": {
                        "sensor_id": payload.get("sensor_id"),
                        "timestamp": payload.get("timestamp")
                    }
                }
                received_packets.append(feature)
        except Exception as e:
            print("[!] Error parsing packet:", e)

if __name__ == "__main__":
    Thread(target=udp_listener, daemon=True).start()
    print("[+] Web dashboard running at http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
