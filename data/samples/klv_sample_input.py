# KLV to ZMeta mapping plan:
# KLV "timestamp"         -> ZMeta "timestamp"
# KLV "targetLatitude"    -> ZMeta "lat"
# KLV "targetLongitude"   -> ZMeta "lon"
# KLV "targetAltitude"    -> ZMeta "alt"
# KLV "sensorType"        -> ZMeta "modality"
# No KLV field for "confidence" — default to 1.0
# No KLV field for "frequency" — leave as None
# klv_sample_input.py

klv_sample = {
    "timestamp": "2025-08-05T15:30:00Z",
    "targetLatitude": 34.0219,
    "targetLongitude": -118.4814,
    "targetAltitude": 120.0,
    "sensorType": "RF",
    "signal_strength": -47.8,
    "modulation": "QPSK"
}
