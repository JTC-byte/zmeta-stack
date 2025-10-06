import json
import random
import socket
import time
from datetime import UTC, datetime

from dotenv import load_dotenv

from backend.app.config import get_settings

load_dotenv()
settings = get_settings()

# === Configuration ===
DEST_IP = settings.simulator_target_host()
DEST_PORT = settings.udp_port
SEND_INTERVAL = 1.0  # Seconds between packets
SENSOR_ID = "sim_thermal_01"
MODALITY = "thermal"


def generate_thermal_packet() -> bytes:
    base_lat = 35.2712
    base_lon = -78.6375
    metadata = {
        "timestamp": datetime.now(UTC).isoformat(),  # ISO format, UTC aware
        "sensor_id": SENSOR_ID,
        "modality": MODALITY,
        "location": {
            "lat": base_lat + random.uniform(-0.0005, 0.0005),
            "lon": base_lon + random.uniform(-0.0005, 0.0005),
            "alt": 144.5 + random.uniform(-2, 2),
        },
        "orientation": {
            "yaw": random.uniform(0, 360),
            "pitch": random.uniform(-10, 10),
            "roll": random.uniform(-5, 5),
        },
        "data": {
            "type": "hotspot",
            "value": random.uniform(45, 85),
            "units": "degC",
            "confidence": round(random.uniform(0.7, 1.0), 2),
        },
        "pid": "target_simulated_1",
        "tags": ["simulated", "test", "thermal"],
        "note": "Test packet from simulated broadcaster",
        "source_format": "simulated_json_v1",
    }
    return json.dumps(metadata).encode("utf-8")


def run_broadcaster() -> None:
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
