from typing import Optional, List, Union
from pydantic import BaseModel, Field, field_validator, ValidationError
from datetime import datetime


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
    source_format: str

    @field_validator('modality', mode='after')
    def validate_modality(cls, v: str) -> str:
        known = {"thermal", "rf", "eo", "ir", "acoustic"}
        lower = v.lower()
        if lower not in known:
            raise ValueError(f"Unknown modality: {v}")
        return lower
