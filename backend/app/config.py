from __future__ import annotations

from functools import lru_cache
from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_prefix="ZMETA_", env_file=".env", extra="ignore")

    app_title: str = Field(default="ZMeta Backend", alias="APP_TITLE")
    udp_host: str = Field(default="0.0.0.0", alias="UDP_HOST")
    udp_port: int = Field(default=5005, alias="UDP_PORT")
    udp_queue_max: int = Field(default=4096, alias="UDP_QUEUE_MAX")
    ui_base_url: str = Field(default="http://127.0.0.1:8000", alias="UI_BASE_URL")
    ws_greeting: str = Field(default="Connected to ZMeta WebSocket", alias="WS_GREETING")
    allowed_origins: List[str] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")
    auth_header: str = Field(default="x-zmeta-secret", alias="AUTH_HEADER")
    shared_secret: str = Field(default="", alias="SHARED_SECRET")
    environment: str = Field(default="dev", alias="ENV")
    ws_queue_max: int = Field(default=64, alias="WS_QUEUE")
    sim_udp_host: str | None = Field(default=None, alias="SIM_UDP_HOST")
    udp_target_host: str = Field(default="127.0.0.1", alias="UDP_TARGET_HOST")
    recorder_retention_hours: float | None = Field(default=None, alias="RECORDER_RETENTION_HOURS")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> List[str] | Any:
        if isinstance(value, str):
            if not value.strip():
                return []
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("shared_secret", mode="before")
    @classmethod
    def _strip_secret(cls, value: Any) -> Any:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed
        return value

    @field_validator("sim_udp_host", mode="before")
    @classmethod
    def _normalize_optional_host(cls, value: Any) -> Any:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @field_validator("recorder_retention_hours", mode="before")
    @classmethod
    def _normalize_retention(cls, value: Any) -> Any:
        if value in ("", None):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("recorder_retention_hours must be numeric") from None
        if number <= 0:
            raise ValueError("recorder_retention_hours must be greater than zero")
        return number

    def auth_enabled(self) -> bool:
        return bool(self.shared_secret)

    def verify_shared_secret(self, provided: str | None) -> bool:
        if not self.auth_enabled():
            return True
        return provided == self.shared_secret

    def ui_url(self, path: str) -> str:
        base = self.ui_base_url.rstrip("/")
        return f"{base}{path}"

    def simulator_target_host(self) -> str:
        for candidate in (self.sim_udp_host, self.udp_target_host, self.udp_host):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return "127.0.0.1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

APP_TITLE = settings.app_title
UDP_HOST = settings.udp_host
UDP_PORT = settings.udp_port
UDP_QUEUE_MAX = settings.udp_queue_max
UI_BASE_URL = settings.ui_base_url
WS_GREETING = settings.ws_greeting
ALLOWED_ORIGINS = settings.allowed_origins
AUTH_HEADER = settings.auth_header
SHARED_SECRET = settings.shared_secret
ENVIRONMENT = settings.environment
WS_QUEUE_MAX = settings.ws_queue_max
SIM_UDP_HOST = settings.sim_udp_host
UDP_TARGET_HOST = settings.udp_target_host
RECORDER_RETENTION_HOURS = settings.recorder_retention_hours


def auth_enabled() -> bool:
    return settings.auth_enabled()


def verify_shared_secret(provided: str | None) -> bool:
    return settings.verify_shared_secret(provided)


def ui_url(path: str) -> str:
    return settings.ui_url(path)


def simulator_target_host() -> str:
    return settings.simulator_target_host()


__all__ = [
    "ALLOWED_ORIGINS",
    "APP_TITLE",
    "AUTH_HEADER",
    "ENVIRONMENT",
    "RECORDER_RETENTION_HOURS",
    "SHARED_SECRET",
    "SIM_UDP_HOST",
    "UDP_HOST",
    "UDP_PORT",
    "UDP_QUEUE_MAX",
    "UDP_TARGET_HOST",
    "UI_BASE_URL",
    "WS_GREETING",
    "WS_QUEUE_MAX",
    "auth_enabled",
    "get_settings",
    "settings",
    "simulator_target_host",
    "ui_url",
    "verify_shared_secret",
]
