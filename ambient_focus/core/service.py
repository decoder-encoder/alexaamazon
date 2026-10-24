"""
Orchestration layer for focus sessions.

FocusService owns the human-in-the-loop state machine, runs device channels
concurrently, and schedules the automatic cleanup. Tools call this class. This
class knows nothing about MCP, so it can be unit-tested without a server.

Session lifecycle
-----------------
    stage() -> AWAITING_CONFIRMATION
        confirm()  -> ACTIVATING -> ACTIVE   (timer scheduled)  -> COMPLETING -> COMPLETED
        confirm()  -> ACTIVATING -> FAILED   (no channel responded, no timer)
        decline()  -> DECLINED
        (no reply) -> EXPIRED                (checked lazily on the next call)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ..config import Settings
from ..devices.base import Channels
from .results import ChannelResult, Outcome
from .sessions import FocusSession, SessionStatus, SessionStore, utcnow

logger = logging.getLogger("ambient_focus.service")


class FocusError(Exception):
    """A user-correctable error with a stable, machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ActivationReport:
    """Outcome of confirm(), ready to serialize for the LLM host."""

    status: str
    session: FocusSession
    results: dict[str, ChannelResult]
    message: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "session_id": self.session.session_id,
            "hardware_modified": self.status != "failed",
            "duration_minutes": self.session.duration_minutes,
            "channels": {name: result.to_dict() for name, result in self.results.items()},
            "message": self.message,
        }
        if self.session.activated_at is not None and self.session.ends_at is not None:
            payload["started_at"] = self.session.activated_at.isoformat()
            payload["ends_at"] = self.session.ends_at.isoformat()
        return payload


async def _gather_named(jobs: dict[str, Awaitable[ChannelResult]]) -> dict[str, ChannelResult]:
    """Run channel operations concurrently and return one result per channel name."""
    names = list(jobs)
    outcomes = await asyncio.gather(*jobs.values(), return_exceptions=True)
    results: dict[str, ChannelResult] = {}
    for name, outcome in zip(names, outcomes):
        if isinstance(outcome, BaseException):
            logger.error("%s: unexpected %s during gather", name, type(outcome).__name__)
            results[name] = ChannelResult.failure(name, "unexpected_error", type(outcome).__name__)
        else:
            results[name] = outcome
    return results


def _compose_message(status: str, session: FocusSession, results: dict[str, ChannelResult]) -> str:
    """Build the sentence the LLM host can relay to the user."""
    if status == "failed":
        return (
            "None of the environment controls responded, so no focus timer was started. "
            "Check the channel details and try again."
        )
    message = (
        f"Focus mode is on for {session.duration_minutes} minutes. "
        "Everything will be restored automatically."
    )
    failed = [name for name, res in results.items() if res.outcome is Outcome.FAILED]
    skipped = [name for name, res in results.items() if res.outcome is Outcome.SKIPPED]
    if failed:
        message += f" These controls did not respond: {', '.join(failed)}."
    if skipped:
        message += f" These are not configured and were skipped: {', '.join(skipped)}."
    return message


class FocusService:
    """Coordinates sessions, device channels, and cleanup timers."""

    def __init__(self, settings: Settings, channels: Channels, store: SessionStore) -> None:
        self._settings = settings
        self._store = store
        self.channels = channels
        self._timers: dict[str, asyncio.Task[None]] = {}

    @property
    def pending_ttl_seconds(self) -> int:
        """How long a staged session waits for confirmation."""
        return self._settings.pending_ttl_seconds

    # ------------------------------------------------------------------
    # Step 1: stage (never touches hardware)
    # ------------------------------------------------------------------
    async def stage(self, duration_minutes: int, enable_dnd: bool, enable_music: bool) -> FocusSession:
        """Validate the request and store it as a session awaiting confirmation."""
        if not 1 <= duration_minutes <= self._settings.max_focus_minutes:
            raise FocusError(
                "duration_out_of_range",
                f"duration_minutes must be between 1 and {self._settings.max_focus_minutes}.",
            )
        session = await self._store.create(duration_minutes, enable_dnd, enable_music)
        logger.info(
            "Session %s staged (duration=%dm, dnd=%s, music=%s)",
            session.session_id,
            duration_minutes,
            enable_dnd,
            enable_music,
        )
        return session

    # ------------------------------------------------------------------
    # Step 2: confirm or decline
    # ------------------------------------------------------------------
    async def decline(self, session_id: str) -> FocusSession:
        """Record that the user declined. No hardware is touched."""
        session = await self._claim_pending(session_id, SessionStatus.DECLINED)
        logger.info("Session %s declined by user", session_id)
        return session

    async def confirm(self, session_id: str) -> ActivationReport:
        """Activate all requested channels concurrently and start the cleanup timer."""
        session = await self._claim_pending(session_id, SessionStatus.ACTIVATING)

        try:
            results = await self._start_channels(session)
        except Exception as exc:
            logger.exception("Session %s: activation crashed", session_id)
            await self._store.update(session, status=SessionStatus.FAILED)
            raise FocusError(
                "activation_crashed",
                "An internal error occurred while activating the environment. No timer was started.",
            ) from exc

        if not any(result.ok for result in results.values()):
            await self._store.update(session, status=SessionStatus.FAILED, activation_results=results)
            logger.warning("Session %s failed: no channel responded", session_id)
            return ActivationReport(
                status="failed",
                session=session,
                results=results,
                message=_compose_message("failed", session, results),
            )

        now = utcnow()
        await self._store.update(
            session,
            status=SessionStatus.ACTIVE,
            activated_at=now,
            ends_at=now + timedelta(minutes=session.duration_minutes),
            activation_results=results,
        )
        self._timers[session_id] = asyncio.create_task(
            self._auto_end_after(session_id, session.duration_minutes * 60),
            name=f"focus-timer-{session_id}",
        )

        status = "partially_active" if any(r.outcome is Outcome.FAILED for r in results.values()) else "active"
        logger.info("Session %s active until %s", session_id, session.ends_at)
        return ActivationReport(
            status=status,
            session=session,
            results=results,
            message=_compose_message(status, session, results),
        )

    async def _claim_pending(self, session_id: str, new_status: SessionStatus) -> FocusSession:
        """Move a session out of AWAITING_CONFIRMATION, enforcing existence and expiry."""
        session = await self._store.get(session_id)
        if session is None:
            raise FocusError(
                "session_not_found",
                "No focus session with that id exists. Start a new one with request_focus_session.",
            )
        if session.status is not SessionStatus.AWAITING_CONFIRMATION:
            raise FocusError(
                "session_not_awaiting_confirmation",
                f"This session is already {session.status.value}. Start a new session if the user still wants one.",
            )
        if session.age > timedelta(seconds=self._settings.pending_ttl_seconds):
            await self._store.update(session, status=SessionStatus.EXPIRED)
            raise FocusError(
                "session_expired",
                "The confirmation window for this session has expired. Start a new session.",
            )

        claimed = await self._store.compare_and_set(
            session_id, SessionStatus.AWAITING_CONFIRMATION, new_status
        )
        if claimed is None:
            # Another request won the race between get() and compare_and_set().
            raise FocusError(
                "session_not_awaiting_confirmation",
                "This session was just acted on by another request. Check its current status.",
            )
        return claimed

    async def _start_channels(self, session: FocusSession) -> dict[str, ChannelResult]:
        jobs: dict[str, Awaitable[ChannelResult]] = {
            "lights": self.channels.lights.start(session.duration_minutes),
        }
        if session.enable_dnd:
            jobs["dnd"] = self.channels.dnd.start(session.duration_minutes)
        if session.enable_music:
            jobs["music"] = self.channels.music.start(session.duration_minutes)
        return await _gather_named(jobs)

    # ------------------------------------------------------------------
    # Automatic cleanup
    # ------------------------------------------------------------------
    async def _auto_end_after(self, session_id: str, delay_seconds: float) -> None:
        """Sleep for the focus window, then restore the environment."""
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            logger.info("Session %s: timer cancelled", session_id)
            raise
        finally:
            self._timers.pop(session_id, None)
        logger.info("Session %s: focus window elapsed, restoring environment", session_id)
        await self._end(session_id)

    async def _end(self, session_id: str) -> None:
        session = await self._store.compare_and_set(session_id, SessionStatus.ACTIVE, SessionStatus.COMPLETING)
        if session is None:
            return

        try:
            results = await self._stop_channels(session)
        except Exception:
            logger.exception("Session %s: cleanup crashed", session_id)
            results = {}

        failed = [name for name, res in results.items() if res.outcome is Outcome.FAILED]
        if failed:
            logger.warning("Session %s: cleanup incomplete, failed channels: %s", session_id, failed)
        else:
            logger.info("Session %s: cleanup complete", session_id)
        await self._store.update(session, status=SessionStatus.COMPLETED, cleanup_results=results)

    async def _stop_channels(self, session: FocusSession) -> dict[str, ChannelResult]:
        jobs: dict[str, Awaitable[ChannelResult]] = {"lights": self.channels.lights.stop()}
        if session.enable_dnd:
            jobs["dnd"] = self.channels.dnd.stop()
        if session.enable_music:
            jobs["music"] = self.channels.music.stop()
        return await _gather_named(jobs)
