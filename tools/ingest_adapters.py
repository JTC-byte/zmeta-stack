# tools/ingest_adapters.py
"""Adapter registry used by the backend to coerce upstream payloads into ZMeta."""

from __future__ import annotations
from typing import Optional, Dict, Any, Callable, Tuple, List

SCHEMA_VERSION = "1.0"

def _get(d: Dict[str, Any], path: str, default=None):
    cur = d
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur

def _copy_loc(p: Dict[str, Any]) -> Dict[str, Any]:
    loc = p.get("location") or {}
    return {"lat": loc.get("lat"), "lon": loc.get("lon"), "alt": loc.get("alt")}

def _top_conf(p: Dict[str, Any]) -> Optional[float]:
    if isinstance(p.get("confidence"), (int, float)):
        return float(p["confidence"])
    dc = _get(p, "data.confidence")
    if isinstance(dc, (int, float)):
        return float(dc)
    return None

def adapt_simulated_v1_rf(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize the v1 RF simulator schema into canonical `rf_detection` ZMeta."""
    src = (p.get("source_format") or "").lower()
    modality = (p.get("modality") or "").lower()
    dtype = _get(p, "data.type")
    units = str(_get(p, "data.units", "")).lower().strip()
    val = _get(p, "data.value")

    matches_format = src == "simulated_json_v1" and modality == "rf"
    matches_shape = dtype == "frequency" and units == "mhz"
    if not (matches_format or matches_shape):
        return None
    if not isinstance(val, (int, float)):
        return None

    hz = int(float(val) * 1_000_000)
    out = {
        "timestamp": p.get("timestamp"),
        "sensor_id": p.get("sensor_id", "sim_rf"),
        "modality": p.get("modality", "rf"),
        "location": _copy_loc(p),
        "orientation": p.get("orientation"),
        "data": {
            "type": "rf_detection",
            "value": {
                "frequency_hz": hz
            }
        },
        "pid": p.get("pid"),
        "tags": p.get("tags"),
        "note": p.get("note"),
        "source_format": "zmeta",
        "confidence": _top_conf(p),
        "schema_version": SCHEMA_VERSION,
    }

    rssi = _get(p, "data.rssi_dbm") or _get(p, "data.value.rssi_dbm")
    if isinstance(rssi, (int, float)):
        out["data"]["value"]["rssi_dbm"] = float(rssi)
    bdw = _get(p, "data.bandwidth_hz") or _get(p, "data.value.bandwidth_hz")
    if isinstance(bdw, (int, float)):
        out["data"]["value"]["bandwidth_hz"] = int(bdw)
    dwell = _get(p, "data.dwell_s") or _get(p, "data.value.dwell_s")
    if isinstance(dwell, (int, float)):
        out["data"]["value"]["dwell_s"] = float(dwell)

    return out

def adapt_simulated_v1_thermal(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize thermal simulator payloads into `thermal_hotspot` ZMeta."""
    src = (p.get("source_format") or "").lower()
    modality = (p.get("modality") or "").lower()
    dtype = _get(p, "data.type")
    val = _get(p, "data.value")

    is_thermal = (modality == "thermal") or (dtype in ("hotspot", "temperature"))
    if not (src == "simulated_json_v1" or is_thermal):
        return None

    temp_c: Optional[float] = None
    if isinstance(val, (int, float)):
        temp_c = float(val)
    else:
        for k in ("data.temp_c", "data.temperature_c", "data.value.temp_c", "data.value.temperature_c"):
            v = _get(p, k)
            if isinstance(v, (int, float)):
                temp_c = float(v)
                break
    if temp_c is None:
        return None

    return {
        "timestamp": p.get("timestamp"),
        "sensor_id": p.get("sensor_id", "sim_thermal"),
        "modality": "thermal",
        "location": _copy_loc(p),
        "orientation": p.get("orientation"),
        "data": {"type": "thermal_hotspot", "value": {"temp_c": temp_c}},
        "pid": p.get("pid"),
        "tags": p.get("tags"),
        "note": p.get("note"),
        "source_format": "zmeta",
        "confidence": _top_conf(p),
        "schema_version": SCHEMA_VERSION,
    }

def adapt_klv_like(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Bridge generic KLV dicts into ZMeta using the shared translator."""
    if not any(k in p for k in ("targetLatitude", "targetLongitude", "sensorType", "platformHeading")):
        return None
    try:
        from tools.translators.klv_to_zmeta import klv_to_zmeta
        z = klv_to_zmeta(p)
        data = z.model_dump()
        data.setdefault("schema_version", SCHEMA_VERSION)
        return data
    except Exception:
        return None

ADAPTERS: List[Tuple[str, Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]]] = [
    ("simulated_v1_rf", adapt_simulated_v1_rf),
    ("simulated_v1_thermal", adapt_simulated_v1_thermal),
    ("klv_like", adapt_klv_like),
]

def adapt_to_zmeta(payload: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    for name, adapter in ADAPTERS:
        out = adapter(payload)
        if out is not None:
            out.setdefault("schema_version", SCHEMA_VERSION)
            return name, out
    return None
