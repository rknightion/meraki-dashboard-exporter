"""Main entry point for the Meraki Dashboard Exporter."""

from __future__ import annotations

import uvicorn

from .core.config import Settings
from .core.logging import get_logger

logger = get_logger(__name__)


def main() -> None:
    """Run the Meraki Dashboard Exporter."""
    settings = Settings()

    logger.info(
        "Starting Meraki Dashboard Exporter",
        host=settings.host,
        port=settings.port,
    )

    # Run uvicorn directly with proper signal handling
    uvicorn.run(
        "meraki_dashboard_exporter.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,  # We handle logging ourselves
        loop="asyncio",
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
