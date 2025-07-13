"""Main entry point for the Meraki Dashboard Exporter."""

from __future__ import annotations

import sys

import uvicorn
from pydantic import ValidationError

from .core.config import Settings
from .core.logging import get_logger

logger = get_logger(__name__)


def main() -> None:
    """Run the Meraki Dashboard Exporter."""
    # Check for help flag before loading settings
    if len(sys.argv) > 1 and sys.argv[1] in {"--help", "-h"}:
        print(
            "Meraki Dashboard Exporter\n"
            "\n"
            "A Prometheus exporter for Cisco Meraki Dashboard API metrics.\n"
            "\n"
            "Usage:\n"
            "  meraki-dashboard-exporter [options]\n"
            "\n"
            "Options:\n"
            "  --help, -h    Show this help message\n"
            "\n"
            "Environment Variables:\n"
            "  MERAKI_API_KEY                     Meraki Dashboard API key (required)\n"
            "  MERAKI_EXPORTER_ORG_ID            Organization ID (optional)\n"
            "  MERAKI_EXPORTER_HOST              Host to bind to (default: 0.0.0.0)\n"
            "  MERAKI_EXPORTER_PORT              Port to bind to (default: 9099)\n"
            "  MERAKI_EXPORTER_LOG_LEVEL         Log level (default: INFO)\n"
            "  MERAKI_EXPORTER_DEVICE_TYPES      Comma-separated device types (default: MS,MR,MV,MT)\n"
            "\n"
            "For more information, visit: https://github.com/rknightion/meraki-dashboard-exporter\n"
        )
        sys.exit(0)

    try:
        settings = Settings()
    except ValidationError as e:
        # Check if it's specifically the API key that's missing
        for error in e.errors():
            if error["loc"] == ("api_key",) and error["type"] == "missing":
                print(
                    "\n❌ ERROR: Meraki API key is required but not found!\n"
                    "\nPlease set the MERAKI_API_KEY environment variable:\n"
                    "  export MERAKI_API_KEY='your-api-key-here'\n"
                    "\nOr create a .env file with:\n"
                    "  MERAKI_API_KEY=your-api-key-here\n"
                    "\nYou can obtain an API key from the Meraki Dashboard:\n"
                    "  1. Log in to https://dashboard.meraki.com\n"
                    "  2. Go to Organization > Settings > Dashboard API access\n"
                    "  3. Enable API access and generate a new API key\n",
                    file=sys.stderr,
                )
                sys.exit(1)

        # For other validation errors, show a more readable format
        print("\n❌ Configuration Error:\n", file=sys.stderr)
        for error in e.errors():
            loc = " > ".join(str(x) for x in error["loc"])
            print(f"  - {loc}: {error['msg']}", file=sys.stderr)
        print("\nPlease check your configuration and try again.\n", file=sys.stderr)
        sys.exit(1)

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
