from typing import Optional, List, Union
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


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
