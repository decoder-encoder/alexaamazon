"""
Composition root. This is the only module that knows how the pieces fit together.

Dependency direction:  tools -> core.service -> devices -> core.http / core.results
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .core.http import WebhookClient
from .core.service import FocusService
from .core.sessions import SessionStore
from .devices import Channels, build_channels
from .tools import register_tools

SERVER_NAME = "AmbientFocusServer"
logger = logging.getLogger("ambient_focus")


def configure_logging(level: str) -> None:
    """Send logs to stderr. Under stdio transport, stdout carries the protocol."""
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _warn_about_unready_channels(channels: Channels) -> None:
    for channel in (channels.lights, channels.dnd, channels.music):
        reason = channel.missing_config()
        if reason is not None:
            logger.warning("%s channel will be skipped: %s", channel.name, reason)


def create_app(settings: Settings) -> FastMCP:
    """Build the fully wired FastMCP server. Performs no network I/O."""
    http = WebhookClient(settings.http_timeout_seconds)
    channels = build_channels(settings, http)
    _warn_about_unready_channels(channels)

    service = FocusService(settings, channels, SessionStore())

    mcp = FastMCP(SERVER_NAME)
    register_tools(mcp, service)
    return mcp
