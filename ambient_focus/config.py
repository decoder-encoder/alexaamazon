"""
Runtime configuration, loaded once from environment variables.

Every setting has a safe default. Invalid values raise ConfigError at startup,
so mistakes surface immediately instead of during a focus session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

VALID_TRANSPORTS = frozenset({"stdio", "sse", "streamable-http"})
VALID_LIGHTS_BACKENDS = frozenset({"homeassistant", "webhook", "none"})
VALID_MUSIC_BACKENDS = frozenset({"local", "webhook", "none"})


class ConfigError(ValueError):
    """Raised when an environment variable holds an invalid value."""


@dataclass(frozen=True)
class Settings:
    """Immutable, validated runtime configuration."""

    # Server
    transport: str
    log_level: str

    # Session behaviour
    pending_ttl_seconds: int
    max_focus_minutes: int
    http_timeout_seconds: float

    # Lights (Home Assistant recommended)
    lights_backend: str
    ha_base_url: str | None
    ha_token: str | None
    ha_light_entities: tuple[str, ...]
    lights_webhook_url: str | None

    # Do Not Disturb (MacroDroid, Android)
    macrodroid_device_id: str | None
    macrodroid_base_url: str
    macrodroid_dnd_on_trigger: str
    macrodroid_dnd_off_trigger: str

    # Music
    music_backend: str
    music_dir: str | None
    music_player: str
    music_webhook_url: str | None


def _text(name: str, default: str | None = None) -> str | None:
    """Read a string variable. Blank values are treated as unset."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _int(name: str, default: int) -> int:
    raw = _text(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = _text(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _choice(name: str, default: str, allowed: frozenset[str]) -> str:
    value = (_text(name) or default).lower()
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _url(name: str, default: str | None = None) -> str | None:
    value = _text(name, default)
    return value.rstrip("/") if value else None


def load_settings() -> Settings:
    """Build and validate Settings from the process environment."""
    entities = tuple(
        entity.strip()
        for entity in (_text("HA_LIGHT_ENTITIES") or "").split(",")
        if entity.strip()
    )

    settings = Settings(
        transport=_choice("MCP_TRANSPORT", "stdio", VALID_TRANSPORTS),
        log_level=(_text("LOG_LEVEL", "INFO") or "INFO").upper(),
        pending_ttl_seconds=_int("PENDING_TTL_SECONDS", 300),
        max_focus_minutes=_int("MAX_FOCUS_MINUTES", 480),
        http_timeout_seconds=_float("HTTP_TIMEOUT_SECONDS", 8.0),
        lights_backend=_choice("LIGHTS_BACKEND", "homeassistant", VALID_LIGHTS_BACKENDS),
        ha_base_url=_url("HA_BASE_URL"),
        ha_token=_text("HA_TOKEN"),
        ha_light_entities=entities,
        lights_webhook_url=_text("LIGHTS_WEBHOOK_URL"),
        macrodroid_device_id=_text("MACRODROID_DEVICE_ID"),
        macrodroid_base_url=_url("MACRODROID_BASE_URL", "https://trigger.macrodroid.com") or "",
        macrodroid_dnd_on_trigger=_text("MACRODROID_DND_ON_TRIGGER", "dnd_on") or "dnd_on",
        macrodroid_dnd_off_trigger=_text("MACRODROID_DND_OFF_TRIGGER", "dnd_off") or "dnd_off",
        music_backend=_choice("MUSIC_BACKEND", "local", VALID_MUSIC_BACKENDS),
        music_dir=_text("MUSIC_DIR"),
        music_player=_text("MUSIC_PLAYER", "mpv") or "mpv",
        music_webhook_url=_text("MUSIC_WEBHOOK_URL"),
    )

    if settings.pending_ttl_seconds <= 0:
        raise ConfigError("PENDING_TTL_SECONDS must be greater than 0")
    if settings.max_focus_minutes <= 0:
        raise ConfigError("MAX_FOCUS_MINUTES must be greater than 0")
    if settings.http_timeout_seconds <= 0:
        raise ConfigError("HTTP_TIMEOUT_SECONDS must be greater than 0")

    return settings
