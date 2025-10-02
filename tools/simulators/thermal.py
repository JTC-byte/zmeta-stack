from datetime import datetime, UTC
import os
import socket
import json
import time
import random

from dotenv import load_dotenv

load_dotenv()

# === Configuration ===
DEST_IP = os.getenv("ZMETA_SIM_UDP_HOST", os.getenv("ZMETA_UDP_TARGET_HOST", "127.0.0.1"))        # Localhost; change to multicast/group IP if needed
DEST_PORT = int(os.getenv("ZMETA_UDP_PORT", "5005"))             # Must match listener
SEND_INTERVAL = 1.0          # Seconds between packets
SENSOR_ID = "sim_thermal_01"
MODALITY = "thermal"

# === Thermal simulator payload generator ===
def generate_thermal_packet():
    base_lat = 35.2712
    base_lon = -78.6375
    metadata = {
        "timestamp": datetime.now(UTC).isoformat(),  # ISO format, UTC aware
        "sensor_id": SENSOR_ID,
        "modality": MODALITY,
        "location": {
            "lat": base_lat + random.uniform(-0.0005, 0.0005),
            "lon": base_lon + random.uniform(-0.0005, 0.0005),
            "alt": 144.5 + random.uniform(-2, 2)
        },
        "orientation": {
            "yaw": random.uniform(0, 360),
            "pitch": random.uniform(-10, 10),
            "roll": random.uniform(-5, 5)
        },
        "data": {
            "type": "hotspot",
            "value": random.uniform(45, 85),
            "units": "degC",
            "confidence": round(random.uniform(0.7, 1.0), 2)
        },
        "pid": "target_simulated_1",
        "tags": ["simulated", "test", "thermal"],
        "note": "Test packet from simulated broadcaster",
        "source_format": "simulated_json_v1"
    }
    return json.dumps(metadata).encode('utf-8')

# === Main Broadcast Loop ===
def run_broadcaster():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[+] Starting thermal simulator -> sending to {DEST_IP}:{DEST_PORT}")
    try:
        while True:
            packet = generate_thermal_packet()
            sock.sendto(packet, (DEST_IP, DEST_PORT))
            print(f"  -> Sent packet @ {datetime.now(UTC).isoformat()}")
            time.sleep(SEND_INTERVAL)
    except KeyboardInterrupt:
        print("\n[!] Broadcast stopped.")

if __name__ == "__main__":
    run_broadcaster()
