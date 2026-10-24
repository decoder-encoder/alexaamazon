"""Device channels and the factory that assembles them from configuration."""

from __future__ import annotations

from ..config import Settings
from ..core.http import WebhookClient
from .base import Channel, Channels, DisabledChannel
from .dnd import MacroDroidDND
from .lights import GenericWebhookLights, HomeAssistantLights
from .music import LocalPlayerMusic, WebhookMusic

__all__ = ["Channel", "Channels", "build_channels"]


def _build_lights(settings: Settings, http: WebhookClient) -> Channel:
    if settings.lights_backend == "homeassistant":
        return HomeAssistantLights(
            settings.ha_base_url,
            settings.ha_token,
            settings.ha_light_entities,
            http,
        )
    if settings.lights_backend == "webhook":
        return GenericWebhookLights(settings.lights_webhook_url, http)
    return DisabledChannel("lights", "lights are disabled (LIGHTS_BACKEND=none)")


def _build_music(settings: Settings, http: WebhookClient) -> Channel:
    if settings.music_backend == "local":
        return LocalPlayerMusic(settings.music_dir, settings.music_player)
    if settings.music_backend == "webhook":
        return WebhookMusic(settings.music_webhook_url, http)
    return DisabledChannel("music", "music is disabled (MUSIC_BACKEND=none)")


def build_channels(settings: Settings, http: WebhookClient) -> Channels:
    """Create every device channel from configuration. Channels are never shared across roles."""
    return Channels(
        lights=_build_lights(settings, http),
        dnd=MacroDroidDND(
            settings.macrodroid_device_id,
            settings.macrodroid_base_url,
            settings.macrodroid_dnd_on_trigger,
            settings.macrodroid_dnd_off_trigger,
            http,
        ),
        music=_build_music(settings, http),
    )
