"""
Device channel abstraction.

Every controllable part of the environment (lights, DND, music) implements
Channel. Subclasses provide only _start and _stop. The base class handles
configuration checks and guarantees that start() and stop() never raise.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.results import ChannelResult

logger = logging.getLogger("ambient_focus.devices")


class Channel(ABC):
    """A controllable part of the environment."""

    name: str = "channel"

    def missing_config(self) -> str | None:
        """Return a human-readable reason this channel cannot run, or None if it can."""
        return None

    def is_ready(self) -> bool:
        return self.missing_config() is None

    async def start(self, duration_minutes: int) -> ChannelResult:
        """Turn the channel on for a focus session. Never raises."""
        reason = self.missing_config()
        if reason is not None:
            return ChannelResult.skipped(self.name, reason)
        try:
            return await self._start(duration_minutes)
        except Exception as exc:
            logger.exception("%s: start failed", self.name)
            return ChannelResult.failure(self.name, "unexpected_error", type(exc).__name__)

    async def stop(self) -> ChannelResult:
        """Restore the channel after a focus session. Never raises."""
        reason = self.missing_config()
        if reason is not None:
            return ChannelResult.skipped(self.name, reason)
        try:
            return await self._stop()
        except Exception as exc:
            logger.exception("%s: stop failed", self.name)
            return ChannelResult.failure(self.name, "unexpected_error", type(exc).__name__)

    @abstractmethod
    async def _start(self, duration_minutes: int) -> ChannelResult:
        """Device-specific start logic."""

    @abstractmethod
    async def _stop(self) -> ChannelResult:
        """Device-specific stop logic."""


class DisabledChannel(Channel):
    """Placeholder for a channel turned off in configuration."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self._reason = reason

    def missing_config(self) -> str | None:
        return self._reason

    async def _start(self, duration_minutes: int) -> ChannelResult:
        return ChannelResult.skipped(self.name, self._reason)

    async def _stop(self) -> ChannelResult:
        return ChannelResult.skipped(self.name, self._reason)


@dataclass(frozen=True)
class Channels:
    """The set of channels the focus service controls."""

    lights: Channel
    dnd: Channel
    music: Channel
