"""
Shared asynchronous HTTP client for webhook-style device integrations.

Every request returns a ChannelResult and never raises. URLs and headers are
never logged or returned, because they can contain tokens or device keys.
Only the channel name, error category, and status code are reported.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .results import ChannelResult

logger = logging.getLogger("ambient_focus.http")


class WebhookClient:
    """Owns one pooled httpx.AsyncClient for the whole process."""

    def __init__(self, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
        )

    async def request(
        self,
        channel: str,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> ChannelResult:
        """Send one request and translate every failure mode into a ChannelResult."""
        try:
            response = await self._client.request(method, url, json=json_body, headers=headers)
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("%s: request timed out after %.1fs", channel, self._timeout_seconds)
            return ChannelResult.failure(
                channel, "timeout", f"no response within {self._timeout_seconds:g} seconds"
            )
        except httpx.NetworkError as exc:
            # DNS failures, refused connections, and dropped sockets.
            logger.warning("%s: network error (%s)", channel, type(exc).__name__)
            return ChannelResult.failure(
                channel,
                "network_error",
                "could not reach the service; check connectivity and the host address",
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("%s: service returned HTTP %s", channel, status)
            return ChannelResult.failure(
                channel,
                "http_error",
                f"service responded with HTTP {status}; check the endpoint and credentials",
            )
        except httpx.HTTPError as exc:
            logger.warning("%s: transport error (%s)", channel, type(exc).__name__)
            return ChannelResult.failure(channel, "transport_error", type(exc).__name__)
        except Exception as exc:  # Defensive: a device call must never crash the server.
            logger.error("%s: unexpected error (%s)", channel, type(exc).__name__)
            return ChannelResult.failure(channel, "unexpected_error", type(exc).__name__)

        logger.info("%s: %s succeeded (HTTP %s)", channel, method, response.status_code)
        return ChannelResult.success(channel, f"HTTP {response.status_code}")

    async def aclose(self) -> None:
        """Close the pooled connections. Call this on shutdown."""
        await self._client.aclose()
