"""Translate KLV dictionaries into ZMeta events."""\n\nfrom schemas.zmeta import ZMeta
from datetime import datetime, timezone
from typing import Dict, Any
from pydantic import ValidationError

SCHEMA_VERSION = "1.0"

def klv_to_zmeta(klv_dict: Dict[str, Any]) -> ZMeta:
    """
    Converts a KLV-style metadata dictionary into a ZMeta object.
    Handles missing values gracefully and fills sensible defaults.
    """

    try:
        zmeta_dict = {
            "sensor_id": klv_dict.get("sensor_id", "klv_source_001"),
            "timestamp": datetime.fromisoformat(
                klv_dict.get("timestamp", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            ),
            "location": {
                "lat": klv_dict.get("targetLatitude", 0.0),
                "lon": klv_dict.get("targetLongitude", 0.0),
                "alt": klv_dict.get("targetAltitude", 0.0)
            },
            "modality": klv_dict.get("sensorType", "unknown").lower(),
            "orientation": {
                "yaw": klv_dict.get("platformHeading", None),
                "pitch": klv_dict.get("platformPitch", None),
                "roll": klv_dict.get("platformRoll", None)
            },
            "data": {
                "type": klv_dict.get("sensorType", "unknown"),
                "value": {
                    "signal_strength": klv_dict.get("signal_strength", None),
                    "modulation": klv_dict.get("modulation", None),
                    "fov": klv_dict.get("sensorFOV", None)
                },
                "units": None,
                "confidence": klv_dict.get("confidence", 1.0)
            },
            "pid": klv_dict.get("pid", None),
            "tags": klv_dict.get("tags", ["converted", "klv"]),
            "note": klv_dict.get("note", "Converted from KLV"),
            "source_format": "KLV",
            "schema_version": SCHEMA_VERSION,
        }

        return ZMeta(**zmeta_dict)

    except ValidationError as ve:
        print("[!] Validation error in KLV to ZMeta:", ve)
        raise
    except Exception as e:
        print("[!] General error in KLV to ZMeta:", e)
        raise

