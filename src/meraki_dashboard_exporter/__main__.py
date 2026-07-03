"""Main entry point for the Meraki Dashboard Exporter."""

from __future__ import annotations

import sys

import uvicorn
from pydantic import ValidationError

from .core.config import Settings
from .core.logging import get_logger

logger = get_logger(__name__)


def _print_redacted_summary(settings: Settings) -> None:
    """Print a redacted, human-readable configuration summary to stdout.

    The Meraki API key is NEVER read or printed here - a fixed ``***REDACTED***``
    placeholder is emitted so the secret cannot leak via the check output.

    Parameters
    ----------
    settings : Settings
        Validated application settings.

    """
    org_filter = settings.meraki.org_id or "None (all organizations)"
    lines = [
        f"  API Base URL:       {settings.meraki.api_base_url}",
        "  API Key:            ***REDACTED***",
        f"  Organization:       {org_filter}",
        f"  Server:             {settings.server.host}:{settings.server.port}",
        f"  Log Level:          {settings.logging.level}",
        f"  API Timeout:        {settings.api.timeout}s",
        f"  API Max Retries:    {settings.api.max_retries}",
        (
            "  Update Intervals:   "
            f"fast={settings.update_intervals.fast}s "
            f"medium={settings.update_intervals.medium}s "
            f"slow={settings.update_intervals.slow}s"
        ),
        f"  OpenTelemetry:      {'ENABLED' if settings.otel.enabled else 'DISABLED'}",
        (
            "  Enabled Collectors: "
            f"{', '.join(sorted(settings.collectors.active_collectors)) or 'None'}"
        ),
    ]
    for line in lines:
        print(line)


def _run_auth_probe(settings: Settings) -> bool:
    """Perform a one-shot Meraki auth probe via ``getOrganizations``.

    This is only invoked when ``--probe`` is passed; the default ``--check`` is
    fully offline. Any exception (auth failure, network error) is treated as a
    failed probe.

    Parameters
    ----------
    settings : Settings
        Validated application settings (supplies the API key/base URL).

    Returns
    -------
    bool
        ``True`` if ``getOrganizations`` succeeded, ``False`` otherwise.

    """
    from .api.client import AsyncMerakiClient

    client = AsyncMerakiClient(settings)
    try:
        client.api.organizations.getOrganizations()
    except Exception as exc:  # noqa: BLE001 - CLI probe: any failure is a failure
        print(f"  auth probe error: {exc}", file=sys.stderr)
        return False
    return True


def _run_config_check(settings: Settings, *, probe: bool) -> None:
    """Validate configuration, print a redacted summary, and exit.

    Exits 0 when the configuration is valid (and, if ``--probe`` was requested,
    the auth probe succeeds); exits non-zero when the probe fails. Invalid
    configuration never reaches this function - it is rejected earlier by the
    ``Settings()`` validation path with a non-zero exit.

    Parameters
    ----------
    settings : Settings
        Validated application settings.
    probe : bool
        Whether to additionally run a live ``getOrganizations`` auth probe.

    """
    print("Meraki Dashboard Exporter - configuration check\n")
    print("Configuration: VALID\n")
    _print_redacted_summary(settings)

    if probe:
        print("\nRunning auth probe (getOrganizations)...")
        if not _run_auth_probe(settings):
            print("Auth probe: FAILED", file=sys.stderr)
            sys.exit(1)
        print("Auth probe: OK")

    sys.exit(0)


def main() -> None:
    """Run the Meraki Dashboard Exporter."""
    args = sys.argv[1:]

    # Check for help flag before loading settings
    if any(arg in {"--help", "-h"} for arg in args):
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
            "  --check       Validate configuration, print a redacted summary, and exit\n"
            "                (non-zero exit on invalid config). Offline by default.\n"
            "  --probe       With --check, also run a live getOrganizations auth probe\n"
            "\n"
            "Environment Variables:\n"
            "  MERAKI_EXPORTER_MERAKI__API_KEY    Meraki Dashboard API key (required)\n"
            "  MERAKI_EXPORTER_MERAKI__ORG_ID     Organization ID (optional)\n"
            "  MERAKI_EXPORTER_SERVER__HOST       Host to bind to (default: 0.0.0.0)\n"
            "  MERAKI_EXPORTER_SERVER__PORT       Port to bind to (default: 9099)\n"
            "  MERAKI_EXPORTER_LOGGING__LEVEL     Log level (default: INFO)\n"
            "\n"
            "For more information, visit: https://github.com/rknightion/meraki-dashboard-exporter\n"
        )
        sys.exit(0)

    check_mode = "--check" in args or "--validate" in args
    probe = "--probe" in args

    try:
        settings = Settings()
    except ValidationError as e:
        # Check if it's specifically the API key that's missing. The `meraki` field is a
        # required nested model (MerakiSettings), so a missing API key surfaces as either
        # loc == ("meraki",) (the whole nested model is absent) or
        # loc == ("meraki", "api_key") (the model is partially populated).
        for error in e.errors():
            if error["loc"] and error["loc"][0] == "meraki" and error["type"] == "missing":
                print(
                    "\n❌ ERROR: Meraki API key is required but not found!\n"
                    "\nPlease set the MERAKI_EXPORTER_MERAKI__API_KEY environment variable:\n"
                    "  export MERAKI_EXPORTER_MERAKI__API_KEY='your-api-key-here'\n"
                    "\nOr create a .env file with:\n"
                    "  MERAKI_EXPORTER_MERAKI__API_KEY=your-api-key-here\n"
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

    # Config-validation / dry-run mode: validate, summarise, optionally probe, exit.
    # This never starts the server (no polling).
    if check_mode:
        _run_config_check(settings, probe=probe)

    # Import the app creation function directly
    from .app import create_app

    # Create the app instance
    app = create_app()

    # Run uvicorn directly with proper signal handling
    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,  # We handle logging ourselves
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
