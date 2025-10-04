from __future__ import annotations

from functools import lru_cache
from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_prefix='ZMETA_', env_file='.env', extra='ignore')

    app_title: str = 'ZMeta Backend'
    udp_host: str = '0.0.0.0'
    udp_port: int = 5005
    udp_queue_max: int = 4096
    ui_base_url: str = 'http://127.0.0.1:8000'
    ws_greeting: str = 'Connected to ZMeta WebSocket'
    allowed_origins: List[str] = Field(default_factory=lambda: ['*'], alias='CORS_ORIGINS')
    auth_header: str = Field(default='x-zmeta-secret', alias='AUTH_HEADER')
    shared_secret: str = Field(default='', alias='SHARED_SECRET')
    environment: str = Field(default='dev', alias='ENV')
    ws_queue_max: int = Field(default=64, alias='WS_QUEUE')

    @field_validator('allowed_origins', mode='before')
    @classmethod
    def _split_csv(cls, value: Any) -> List[str] | Any:
        if isinstance(value, str):
            if not value.strip():
                return []
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('shared_secret', mode='before')
    @classmethod
    def _strip_secret(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    def auth_enabled(self) -> bool:
        return bool(self.shared_secret)

    def verify_shared_secret(self, provided: str | None) -> bool:
        if not self.auth_enabled():
            return True
        return provided == self.shared_secret

    def ui_url(self, path: str) -> str:
        base = self.ui_base_url.rstrip('/')
        return f'{base}{path}'


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


def auth_enabled() -> bool:
    return settings.auth_enabled()


def verify_shared_secret(provided: str | None) -> bool:
    return settings.verify_shared_secret(provided)


def ui_url(path: str) -> str:
    return settings.ui_url(path)


__all__ = [
    'ALLOWED_ORIGINS',
    'APP_TITLE',
    'AUTH_HEADER',
    'ENVIRONMENT',
    'SHARED_SECRET',
    'UDP_HOST',
    'UDP_PORT',
    'UDP_QUEUE_MAX',
    'UI_BASE_URL',
    'WS_GREETING',
    'WS_QUEUE_MAX',
    'auth_enabled',
    'get_settings',
    'settings',
    'ui_url',
    'verify_shared_secret',
]
