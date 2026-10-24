"""Entry point: ``python -m ambient_focus``."""

from __future__ import annotations

import logging
import sys

from . import __version__
from .app import configure_logging, create_app
from .config import ConfigError, load_settings

logger = logging.getLogger("ambient_focus")


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    configure_logging(settings.log_level)
    logger.info("Ambient Focus MCP server v%s starting (transport=%s)", __version__, settings.transport)

    server = create_app(settings)
    server.run(transport=settings.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
