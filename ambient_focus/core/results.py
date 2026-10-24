"""Typed results returned by every device channel operation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    """Result category of a single channel operation."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ChannelResult:
    """The outcome of one device operation, with a diagnostic message on failure."""

    channel: str
    outcome: Outcome
    error: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.OK

    @classmethod
    def success(cls, channel: str, detail: str = "") -> ChannelResult:
        return cls(channel=channel, outcome=Outcome.OK, detail=detail)

    @classmethod
    def failure(cls, channel: str, error: str, detail: str = "") -> ChannelResult:
        return cls(channel=channel, outcome=Outcome.FAILED, error=error, detail=detail)

    @classmethod
    def skipped(cls, channel: str, reason: str) -> ChannelResult:
        return cls(channel=channel, outcome=Outcome.SKIPPED, detail=reason)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the LLM host, leaving out empty fields."""
        data: dict[str, Any] = {"channel": self.channel, "outcome": self.outcome.value}
        if self.error:
            data["error"] = self.error
        if self.detail:
            data["detail"] = self.detail
        return data
