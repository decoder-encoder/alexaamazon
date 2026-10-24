"""MCP tool modules. Each module registers its own tools on the server."""

from mcp.server.fastmcp import FastMCP

from ..core.service import FocusService
from . import confirm_focus, request_focus


def register_tools(mcp: FastMCP, service: FocusService) -> None:
    """Attach every tool module to the server."""
    request_focus.register(mcp, service)
    confirm_focus.register(mcp, service)
