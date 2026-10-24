"""MCP tool 2 of 2: confirm or decline a staged focus session. Only this tool changes hardware."""

from mcp.server.fastmcp import FastMCP

from ..core.service import FocusError, FocusService
from ._responses import error_response, respond


def register(mcp: FastMCP, service: FocusService) -> None:
    """Register confirm_and_execute_focus on the given FastMCP server."""

    @mcp.tool()
    async def confirm_and_execute_focus(session_id: str, confirmed: bool) -> str:
        """
        Execute or decline a staged focus session. This is step 2 of 2.

        Call this only after request_focus_session returned a session_id and the user
        answered the suggested question. Pass confirmed=true only for an explicit yes
        (for example "Yes, go ahead"). Pass confirmed=false if the user declines.
        On success the lights, Do Not Disturb, and music switch on together, and
        everything is restored automatically when the focus window ends.

        Args:
            session_id: The session_id returned by request_focus_session.
            confirmed: True only if the user explicitly approved the actions.
        """
        try:
            if not confirmed:
                session = await service.decline(session_id)
                return respond(
                    {
                        "status": "declined",
                        "session_id": session.session_id,
                        "hardware_modified": False,
                        "message": "Understood. No changes were made to your environment.",
                    }
                )
            report = await service.confirm(session_id)
        except FocusError as exc:
            return error_response(exc)
        return respond(report.to_payload())
