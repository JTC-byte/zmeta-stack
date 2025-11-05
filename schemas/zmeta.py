from typing import Optional, List, Union, Literal, Any
from pydantic import BaseModel, Field, field_validator, ValidationError
from datetime import datetime


SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1"}

Modality = Literal["thermal", "rf", "eo", "ir", "acoustic"]


class Location(BaseModel):
    lat: float
    lon: float
    alt: Optional[float] = None

class Orientation(BaseModel):
    yaw: Optional[float] = None
    pitch: Optional[float] = None
    roll: Optional[float] = None

class SensorData(BaseModel):
    type: str
    value: Union[str, float, int, dict]
    units: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class RFData(BaseModel):
    type: Literal["burst", "tone", "sweep", "unk"] = "burst"
    freq_hz: float                            # center frequency (Hz)
    bw_hz: Optional[float] = None             # bandwidth (Hz)
    tx_power_dbm: Optional[float] = None      # transmitted power (dBm)
    rx_power_dbm: Optional[float] = None      # received power (dBm)
    power_dbm: Optional[float] = None         # generic/unknown power measurement (legacy)
    rssi_dbm: Optional[float] = None          # received signal strength (dBm)
    doa_deg: Optional[float] = None           # direction of arrival (bearing)
    snr_db: Optional[float] = None            # signal-to-noise ratio (dB)
    path_loss_db: Optional[float] = None      # optional derived propagation loss
    polarization: Optional[str] = None        # e.g., "vertical", "horizontal", "circular"
    antenna_gain_dbi: Optional[float] = None  # TX/RX antenna gain (dBi)
    confidence: Optional[float] = Field(None, ge=0, le=1)


class ThermalData(BaseModel):
    type: Literal["hotspot", "bbox", "unk"] = "hotspot"
    bbox: Optional[List[float]] = None
    temp_c: Optional[float] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)


class AcousticData(BaseModel):
    type: Literal["doa", "event", "unk"] = "doa"
    doa_deg: Optional[float] = None
    class_label: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)


class EOIRData(BaseModel):
    type: Literal["bbox", "feature", "unk"] = "bbox"
    bbox: Optional[List[float]] = None
    class_label: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)


SensorPayload = Union[RFData, ThermalData, AcousticData, EOIRData]


class SecurityStamp(BaseModel):
    sig: Optional[str] = None
    sig_alg: Optional[str] = None
    key_id: Optional[str] = None
    sha256: Optional[str] = None


class Provenance(BaseModel):
    validated: Optional[bool] = None
    edge_promoted: Optional[bool] = None
    collapse_mode: Optional[bool] = None
    export_redacted: Optional[bool] = None
    source_format: str
    sensor_make: Optional[str] = None
    sensor_model: Optional[str] = None
    sensor_serial: Optional[str] = None
    firmware: Optional[str] = None
    calibration_id: Optional[str] = None


class TransportHealth(BaseModel):
    link: Optional[str] = None
    latency_ms: Optional[float] = None
    loss_pct: Optional[float] = None
    jitter_ms: Optional[float] = None
    rssi_dbm: Optional[float] = None
    snr_db: Optional[float] = None


class FusionContext(BaseModel):
    graph_entity_id: Optional[str] = None
    redundancy_count: Optional[int] = None
    trust_score: Optional[float] = Field(None, ge=0, le=1)
    task_ref: Optional[str] = None

class ZMeta(BaseModel):
    timestamp: datetime
    sensor_id: str
    modality: str
    location: Location
    orientation: Optional[Orientation] = None
    data: SensorData
    pid: Optional[str] = None
    tags: Optional[List[str]] = None
    note: Optional[str] = None
    schema_version: str = "1.0"
    sequence: Optional[int] = None
    source_format: str
    stream_id: Optional[str] = None
    bundle_id: Optional[str] = None
    partition_key: Optional[str] = None
    provenance: Optional[Provenance] = None
    transport: Optional[TransportHealth] = None
    security: Optional[SecurityStamp] = None
    fusion: Optional[FusionContext] = None

    @field_validator('modality', mode='after')
    def validate_modality(cls, v: str) -> str:
        known = {"thermal", "rf", "eo", "ir", "acoustic"}
        lower = v.lower()
        if lower not in known:
            raise ValueError(f"Unknown modality: {v}")
        return lower


    @field_validator('schema_version', mode='after')
    def validate_schema_version(cls, v: str) -> str:
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported schema_version: {v}")
        return v

    @field_validator('sequence', mode='after')
    def validate_sequence(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError('sequence must be >= 0')
        return v


class ZMetaV11(BaseModel):
    schema_version: str = "1.1"
    timestamp: datetime
    sensor_id: str
    modality: Modality
    location: Location
    data: SensorPayload
    provenance: Provenance
    orientation: Optional[Orientation] = None
    pid: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[List[str]] = None
    stream_id: Optional[str] = None
    sequence: Optional[int] = None
    bundle_id: Optional[str] = None
    partition_key: Optional[str] = None
    transport: Optional[TransportHealth] = None
    security: Optional[SecurityStamp] = None
    fusion: Optional[FusionContext] = None

    @field_validator('modality', mode='after')
    def check_modality(cls, v: str) -> str:
        known = {"thermal", "rf", "eo", "ir", "acoustic"}
        lower = v.lower()
        if lower not in known:
            raise ValueError(f"Unknown modality: {v}")
        return lower

    @field_validator('schema_version', mode='after')
    def check_schema_version(cls, v: str) -> str:
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported schema_version: {v}")
        return v


def _strip_none(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


def _sensor_payload_to_data(modality: str, payload: SensorPayload) -> SensorData:
    modality_norm = modality.lower()
    if isinstance(payload, RFData):
        value = _strip_none(
            {
                "frequency_hz": payload.freq_hz,
                "bandwidth_hz": payload.bw_hz,
                "tx_power_dbm": payload.tx_power_dbm,
                "rx_power_dbm": payload.rx_power_dbm,
                "power_dbm": payload.power_dbm,
                "rssi_dbm": payload.rssi_dbm,
                "doa_deg": payload.doa_deg,
                "snr_db": payload.snr_db,
                "path_loss_db": payload.path_loss_db,
                "polarization": payload.polarization,
                "antenna_gain_dbi": payload.antenna_gain_dbi,
            }
        )
        dtype = f"{modality_norm}_{payload.type}".strip("_")
        return SensorData(type=dtype, value=value, confidence=payload.confidence)

    if isinstance(payload, ThermalData):
        value = _strip_none({"bbox": payload.bbox, "temp_c": payload.temp_c})
        dtype = f"{modality_norm}_{payload.type}".strip("_")
        return SensorData(type=dtype, value=value, confidence=payload.confidence)

    if isinstance(payload, AcousticData):
        value = _strip_none(
            {
                "doa_deg": payload.doa_deg,
                "class_label": payload.class_label,
            }
        )
        dtype = f"{modality_norm}_{payload.type}".strip("_")
        return SensorData(type=dtype, value=value, confidence=payload.confidence)

    if isinstance(payload, EOIRData):
        value = _strip_none(
            {
                "bbox": payload.bbox,
                "class_label": payload.class_label,
            }
        )
        dtype = f"{modality_norm}_{payload.type}".strip("_")
        return SensorData(type=dtype, value=value, confidence=payload.confidence)

    generic_value = payload.model_dump(exclude={"type", "confidence"}, exclude_none=True)
    dtype = f"{modality_norm}_{getattr(payload, 'type', 'payload')}".strip("_")
    return SensorData(
        type=dtype,
        value=generic_value or {},
        confidence=getattr(payload, "confidence", None),
    )


def zmeta_from_v11(payload: ZMetaV11) -> ZMeta:
    sensor_data = _sensor_payload_to_data(payload.modality, payload.data)
    return ZMeta(
        schema_version=payload.schema_version,
        timestamp=payload.timestamp,
        sensor_id=payload.sensor_id,
        modality=payload.modality,
        location=payload.location,
        orientation=payload.orientation,
        data=sensor_data,
        pid=payload.pid,
        tags=payload.tags,
        note=payload.note,
        sequence=payload.sequence,
        source_format=payload.provenance.source_format,
        stream_id=payload.stream_id,
        bundle_id=payload.bundle_id,
        partition_key=payload.partition_key,
        provenance=payload.provenance,
        transport=payload.transport,
        security=payload.security,
        fusion=payload.fusion,
    )


def parse_zmeta(payload: Any) -> ZMeta:
    if isinstance(payload, ZMeta):
        return payload
    if isinstance(payload, ZMetaV11):
        return zmeta_from_v11(payload)
    try:
        return ZMeta.model_validate(payload)
    except ValidationError as first_error:
        try:
            v11 = ZMetaV11.model_validate(payload)
        except ValidationError:
            raise first_error
        return zmeta_from_v11(v11)
