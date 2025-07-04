"""Main entry point for the Meraki Dashboard Exporter."""

from __future__ import annotations

import signal
import sys
from typing import Any

import uvicorn

from .app import create_app
from .core.config import Settings
from .core.logging import get_logger

logger = get_logger(__name__)


def main() -> None:
    """Run the Meraki Dashboard Exporter."""
    settings = Settings()
    app = create_app()

    logger.info(
        "Starting Meraki Dashboard Exporter",
        host=settings.host,
        port=settings.port,
    )

    # Configure uvicorn to handle signals properly
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,  # We handle logging ourselves
        # Disable uvicorn's signal handlers so our app can handle them
        use_colors=False,
        loop="asyncio",
    )

    server = uvicorn.Server(config)

    # Set up signal handling for graceful shutdown
    def signal_handler(sig: int, frame: Any) -> None:
        logger.info("Received signal, initiating shutdown...")
        server.should_exit = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        sys.exit(0)


if __name__ == "__main__":
    main()
