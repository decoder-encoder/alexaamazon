"""
Smart-light channels.

HomeAssistantLights (recommended)
    Calls Home Assistant's local REST API. Home Assistant is free and
    self-hosted, and it talks to Hue, WiZ, Tuya, Lutron, and many other brands,
    so one integration covers all of them. Authentication uses a long-lived
    access token that you create in your HA profile. No cloud key is needed.

GenericWebhookLights
    Posts JSON to any URL, such as a Node-RED flow, a Make or Pipedream scenario
    on a free tier, or a small local bridge script.
"""

from __future__ import annotations

from ..core.http import WebhookClient
from ..core.results import ChannelResult
from .base import Channel

FOCUS_RGB_COLOR = [80, 140, 255]  # Cool blue, a deep-work palette.
FOCUS_BRIGHTNESS = 180
BREAK_COLOR_TEMP_KELVIN = 3000  # Warm white.
BREAK_BRIGHTNESS = 255


class HomeAssistantLights(Channel):
    """Controls lights through Home Assistant's light.turn_on service."""

    name = "lights"

    def __init__(
        self,
        base_url: str | None,
        token: str | None,
        entities: tuple[str, ...],
        http: WebhookClient,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._entities = list(entities)
        self._http = http

    def missing_config(self) -> str | None:
        if not self._base_url or not self._token:
            return "HA_BASE_URL and HA_TOKEN must be set to use Home Assistant lights"
        if not self._entities:
            return "HA_LIGHT_ENTITIES is empty; list the light entity ids to control"
        return None

    async def _start(self, duration_minutes: int) -> ChannelResult:
        return await self._call_turn_on(
            {
                "entity_id": self._entities,
                "rgb_color": FOCUS_RGB_COLOR,
                "brightness": FOCUS_BRIGHTNESS,
            }
        )

    async def _stop(self) -> ChannelResult:
        return await self._call_turn_on(
            {
                "entity_id": self._entities,
                "color_temp_kelvin": BREAK_COLOR_TEMP_KELVIN,
                "brightness": BREAK_BRIGHTNESS,
            }
        )

    async def _call_turn_on(self, payload: dict[str, object]) -> ChannelResult:
        url = f"{self._base_url}/api/services/light/turn_on"
        headers = {"Authorization": f"Bearer {self._token}"}
        return await self._http.request(self.name, "POST", url, json_body=payload, headers=headers)


class GenericWebhookLights(Channel):
    """Posts focus events as JSON to a user-supplied URL."""

    name = "lights"

    def __init__(self, url: str | None, http: WebhookClient) -> None:
        self._url = url
        self._http = http

    def missing_config(self) -> str | None:
        return None if self._url else "LIGHTS_WEBHOOK_URL is not set"

    async def _start(self, duration_minutes: int) -> ChannelResult:
        return await self._http.request(
            self.name,
            "POST",
            self._url or "",
            json_body={"event": "focus_on", "duration_minutes": duration_minutes},
        )

    async def _stop(self) -> ChannelResult:
        return await self._http.request(
            self.name,
            "POST",
            self._url or "",
            json_body={"event": "break_mode"},
        )
