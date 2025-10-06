import json
import random
import socket
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

from backend.app.config import get_settings

load_dotenv()
settings = get_settings()

# UDP target
UDP_IP = settings.simulator_target_host()
UDP_PORT = settings.udp_port

# Fixed RF sensor metadata
SENSOR_ID = "sim_rf_01"
MODALITY = "rf"
BASE_LAT = 35.2714
BASE_LON = -78.6376
BASE_ALT = 145.0


def simulate_location() -> dict[str, float]:
    """Randomize location slightly to simulate motion."""

    return {
        "lat": BASE_LAT + random.uniform(-0.0005, 0.0005),
        "lon": BASE_LON + random.uniform(-0.0005, 0.0005),
        "alt": BASE_ALT + random.uniform(-2.0, 2.0),
    }


def run_broadcaster() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[RF] Broadcasting RF packets to {UDP_IP}:{UDP_PORT}")

    while True:
        packet = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sensor_id": SENSOR_ID,
            "modality": MODALITY,
            "location": simulate_location(),
            "orientation": {
                "yaw": random.uniform(0, 360),
                "pitch": random.uniform(-10, 10),
                "roll": random.uniform(-5, 5),
            },
            "data": {
                "type": "frequency",
                "value": round(random.uniform(902.0, 928.0), 3),
                "units": "MHz",
                "confidence": round(random.uniform(0.5, 1.0), 2),
            },
            "pid": "rf_signal_simulated_1",
            "tags": ["simulated", "rf", "test"],
            "note": "Simulated RF metadata packet",
            "source_format": "simulated_json_v1",
        }

        json_data = json.dumps(packet).encode("utf-8")
        sock.sendto(json_data, (UDP_IP, UDP_PORT))

        print(f"[RF] Sent RF packet @ {packet['timestamp']} | Freq: {packet['data']['value']} MHz")
        time.sleep(1)


if __name__ == "__main__":
    try:
        run_broadcaster()
    except KeyboardInterrupt:
        print("\n[!] RF broadcaster stopped.")
