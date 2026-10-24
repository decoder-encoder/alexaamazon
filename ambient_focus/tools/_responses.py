"""Helpers that turn internal results into the JSON strings the LLM host receives."""

from __future__ import annotations

import json
from typing import Any

from ..core.service import FocusError


def respond(payload: dict[str, Any]) -> str:
    """Serialize a payload as readable JSON."""
    return json.dumps(payload, indent=2, default=str)


def error_response(error: FocusError) -> str:
    """Serialize a FocusError as a structured error the host can act on."""
    return respond({"status": "error", "error": error.code, "message": error.message})


def join_natural(items: list[str]) -> str:
    """Join items for speech: ["a"] -> "a", ["a", "b"] -> "a and b", ["a", "b", "c"] -> "a, b, and c"."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
