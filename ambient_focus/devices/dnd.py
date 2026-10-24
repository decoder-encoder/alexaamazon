"""
Do Not Disturb channel for Android, using MacroDroid's free webhook trigger.

Each MacroDroid macro listens on a URL of the form:
    {base_url}/{device_id}/{trigger_name}
and sets the phone to Do Not Disturb or restores it when that URL is requested.
"""

from __future__ import annotations

from urllib.parse import quote

from ..core.http import WebhookClient
from ..core.results import ChannelResult
from .base import Channel


class MacroDroidDND(Channel):
    """Toggles Do Not Disturb through MacroDroid HTTP triggers."""

    name = "dnd"

    def __init__(
        self,
        device_id: str | None,
        base_url: str,
        on_trigger: str,
        off_trigger: str,
        http: WebhookClient,
    ) -> None:
        self._device_id = device_id
        self._base_url = base_url
        self._on_trigger = on_trigger
        self._off_trigger = off_trigger
        self._http = http

    def missing_config(self) -> str | None:
        return None if self._device_id else "MACRODROID_DEVICE_ID is not set"

    async def _start(self, duration_minutes: int) -> ChannelResult:
        return await self._trigger(self._on_trigger)

    async def _stop(self) -> ChannelResult:
        return await self._trigger(self._off_trigger)

    async def _trigger(self, trigger_name: str) -> ChannelResult:
        url = (
            f"{self._base_url}/{quote(self._device_id or '', safe='')}"
            f"/{quote(trigger_name, safe='')}"
        )
        return await self._http.request(self.name, "GET", url)
