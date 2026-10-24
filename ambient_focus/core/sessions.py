"""
Focus session model and an asyncio-safe in-memory store.

The store only protects state transitions with a lock. Network I/O never runs
while the lock is held, so one slow device cannot block other requests.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from .results import ChannelResult


def utcnow() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    """Lifecycle states of a focus session."""

    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ACTIVATING = "activating"
    ACTIVE = "active"
    COMPLETING = "completing"
    COMPLETED = "completed"
    DECLINED = "declined"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class FocusSession:
    """All state for one focus session."""

    session_id: str
    duration_minutes: int
    enable_dnd: bool
    enable_music: bool
    status: SessionStatus = SessionStatus.AWAITING_CONFIRMATION
    created_at: datetime = field(default_factory=utcnow)
    activated_at: datetime | None = None
    ends_at: datetime | None = None
    activation_results: dict[str, ChannelResult] = field(default_factory=dict)
    cleanup_results: dict[str, ChannelResult] = field(default_factory=dict)

    @property
    def age(self) -> timedelta:
        return utcnow() - self.created_at


class SessionStore:
    """In-memory session storage for a single asyncio event loop."""

    _LIVE_STATUSES = frozenset(
        {SessionStatus.ACTIVATING, SessionStatus.ACTIVE, SessionStatus.COMPLETING}
    )
    _RETENTION = timedelta(hours=2)

    def __init__(self) -> None:
        self._sessions: dict[str, FocusSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, duration_minutes: int, enable_dnd: bool, enable_music: bool) -> FocusSession:
        """Create and store a new session awaiting confirmation."""
        async with self._lock:
            self._prune()
            session = FocusSession(
                session_id=uuid.uuid4().hex,
                duration_minutes=duration_minutes,
                enable_dnd=enable_dnd,
                enable_music=enable_music,
            )
            self._sessions[session.session_id] = session
            return session

    async def get(self, session_id: str) -> FocusSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def compare_and_set(
        self,
        session_id: str,
        expected: SessionStatus,
        new: SessionStatus,
    ) -> FocusSession | None:
        """
        Atomically change status from `expected` to `new`.

        Returns the session if the transition happened, or None if the session is
        missing or not in the expected state. This is what makes double-execution
        impossible when the host retries a confirmation.
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.status is not expected:
                return None
            session.status = new
            return session

    async def update(self, session: FocusSession, **changes: object) -> None:
        """Apply field changes to a session under the lock."""
        async with self._lock:
            for name, value in changes.items():
                setattr(session, name, value)

    def _prune(self) -> None:
        """Drop finished sessions older than the retention window. Caller holds the lock."""
        for session_id, session in list(self._sessions.items()):
            if session.status not in self._LIVE_STATUSES and session.age > self._RETENTION:
                del self._sessions[session_id]
