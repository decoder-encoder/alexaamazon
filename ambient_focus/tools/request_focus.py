"""MCP tool 1 of 2: stage a focus session. This tool never changes a device."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.service import FocusError, FocusService
from ..core.sessions import FocusSession
from ._responses import error_response, join_natural, respond


def _staged_payload(service: FocusService, session: FocusSession) -> dict[str, Any]:
    """Describe the staged session and the question the host should ask the user."""
    actions = ["set the lights to focus mode"]
    if session.enable_dnd:
        actions.append("turn on Do Not Disturb on the phone")
    if session.enable_music:
        actions.append("start focus music")

    channels = service.channels
    return {
        "status": "awaiting_confirmation",
        "session_id": session.session_id,
        "requires_user_confirmation": True,
        "hardware_modified": False,
        "duration_minutes": session.duration_minutes,
        "expires_in_seconds": service.pending_ttl_seconds,
        "planned_actions": {
            "lights": True,
            "do_not_disturb": session.enable_dnd,
            "focus_music": session.enable_music,
        },
        "channel_readiness": {
            "lights": channels.lights.is_ready(),
            "do_not_disturb": channels.dnd.is_ready() if session.enable_dnd else None,
            "focus_music": channels.music.is_ready() if session.enable_music else None,
        },
        "suggested_question": (
            f"Should I {join_natural(actions)} for {session.duration_minutes} minutes?"
        ),
        "instructions_for_host": (
            "Ask the user the suggested_question and wait for a clear answer. Do not call "
            "confirm_and_execute_focus with confirmed=true unless the user explicitly agrees. "
            "If the user declines, call confirm_and_execute_focus with confirmed=false."
        ),
    }


def register(mcp: FastMCP, service: FocusService) -> None:
    """Register request_focus_session on the given FastMCP server."""

    @mcp.tool()
    async def request_focus_session(
        duration_minutes: int,
        enable_dnd: bool = True,
        enable_music: bool = True,
    ) -> str:
        """
        Stage a deep-work focus session. This is step 1 of 2 and does NOT change any device.

        Call this when the user asks to start focus, deep work, or do-not-disturb mode.
        It returns a JSON document with status "awaiting_confirmation" and a
        suggested_question. Read that question to the user and wait for an explicit
        answer. Then call confirm_and_execute_focus with the returned session_id and
        confirmed=true only if the user agrees, or confirmed=false if they decline.

        Args:
            duration_minutes: Length of the focus window in minutes.
            enable_dnd: Whether to put the phone into Do Not Disturb mode.
            enable_music: Whether to start focus music.
        """
        try:
            session = await service.stage(duration_minutes, enable_dnd, enable_music)
        except FocusError as exc:
            return error_response(exc)
        return respond(_staged_payload(service, session))
