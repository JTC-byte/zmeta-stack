from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field, field_validator
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
    power_dbm: Optional[float] = None         # transmit or received power (dBm)
    rssi_dbm: Optional[float] = None          # received signal strength (dBm)
    doa_deg: Optional[float] = None           # direction of arrival (bearing)
    snr_db: Optional[float] = None            # signal-to-noise ratio (dB)
    path_loss_db: Optional[float] = None      # optional derived propagation loss
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
