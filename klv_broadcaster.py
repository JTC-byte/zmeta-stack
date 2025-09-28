import socket
import json
import time
import random
from datetime import datetime, timezone
from z_meta_schema import ZMeta, Location, Orientation, SensorData

# UDP config
UDP_IP = "127.0.0.1"
UDP_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("[+] Starting ZMeta continuous broadcaster...")

try:
    while True:
        # Randomized lat/lon around Fort Liberty area
        lat = 35.0 + random.uniform(-0.01, 0.01)
        lon = -78.0 + random.uniform(-0.01, 0.01)

        packet = ZMeta(
            sensor_id="klv_source_001",
            modality="rf",
            location=Location(lat=lat, lon=lon, alt=100.0),
            orientation=Orientation(yaw=90.0, pitch=0.0, roll=0.0),
            timestamp=datetime.now(timezone.utc),
            data=SensorData(  # ✅ Corrected field name
                type="rf_signal_strength",
                value=-50.0
            ),
            pid=None,
            tags=["converted", "klv"],
            note="Converted from KLV",
            source_format="KLV"
        )

        sock.sendto(packet.model_dump_json().encode(), (UDP_IP, UDP_PORT))
        print(f"[+] Sent ZMeta packet: lat={lat:.5f}, lon={lon:.5f}")
        time.sleep(1)

except KeyboardInterrupt:
    print("\n[!] Broadcast stopped by user.")
