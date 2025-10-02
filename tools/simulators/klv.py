import json
import os
import random
import socket
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# UDP config
UDP_IP = os.getenv("ZMETA_SIM_UDP_HOST", os.getenv("ZMETA_UDP_TARGET_HOST", "127.0.0.1"))
UDP_PORT = int(os.getenv("ZMETA_UDP_PORT", "5005"))

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("[+] Starting KLV simulator broadcaster...")

try:
    while True:
        # Randomized lat/lon around Fort Liberty area
        lat = 35.0 + random.uniform(-0.01, 0.01)
        lon = -78.0 + random.uniform(-0.01, 0.01)

        packet = {
            "sensor_id": "klv_source_001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "targetLatitude": lat,
            "targetLongitude": lon,
            "targetAltitude": 100.0,
            "sensorType": random.choice(["RF", "EO", "IR"]),
            "platformHeading": random.uniform(0, 360),
            "platformPitch": random.uniform(-2.0, 2.0),
            "platformRoll": random.uniform(-3.0, 3.0),
            "signal_strength": -45.0 + random.uniform(-5.0, 5.0),
            "sensorFOV": 12.0 + random.uniform(-2.0, 2.0),
            "modulation": random.choice(["fm", "qam", "psk"]),
            "confidence": round(random.uniform(0.6, 0.98), 2),
        }

        sock.sendto(json.dumps(packet).encode("utf-8"), (UDP_IP, UDP_PORT))
        print(f"[+] Sent KLV packet: lat={lat:.5f}, lon={lon:.5f}")
        time.sleep(1)

except KeyboardInterrupt:
    print("\n[!] Broadcast stopped by user.")
