"""Configuration logging utilities for startup visibility."""

from __future__ import annotations

import json
import os
from typing import Any

from .config import Settings
from .logging import get_logger

logger = get_logger(__name__)


def mask_sensitive_value(key: str, value: Any) -> Any:
    """Mask sensitive configuration values.

    Parameters
    ----------
    key : str
        Configuration key name.
    value : Any
        Configuration value.

    Returns
    -------
    Any
        Masked value if sensitive, original value otherwise.

    """
    sensitive_keys = {
        "api_key",
        "meraki_api_key",
        "password",
        "secret",
        "token",
        "credential",
    }

    # Check if key contains any sensitive terms
    key_lower = key.lower()
    if any(sensitive in key_lower for sensitive in sensitive_keys):
        if isinstance(value, str) and value:
            # Show first and last 2 characters for verification
            if len(value) > 8:
                return f"{value[:2]}...{value[-2:]}"
            else:
                return "***MASKED***"

    return value


def get_env_vars() -> dict[str, str]:
    """Get all MERAKI_EXPORTER environment variables.

    Returns
    -------
    dict[str, str]
        Dictionary of environment variables with masked sensitive values.

    """
    env_vars = {}
    prefix = "MERAKI_EXPORTER_"

    # Also include MERAKI_API_KEY without prefix
    if "MERAKI_API_KEY" in os.environ:
        env_vars["MERAKI_API_KEY"] = mask_sensitive_value(
            "MERAKI_API_KEY", os.environ["MERAKI_API_KEY"]
        )

    # Get all MERAKI_EXPORTER_* variables
    for key, value in os.environ.items():
        if key.startswith(prefix) or key == "MERAKI_API_KEY":
            masked_value = mask_sensitive_value(key, value)
            env_vars[key] = masked_value

    return env_vars


def log_configuration(settings: Settings) -> None:
    """Log the current configuration at startup.

    Parameters
    ----------
    settings : Settings
        Application settings to log.

    """
    logger.info("=" * 80)
    logger.info("Meraki Dashboard Exporter Configuration")
    logger.info("=" * 80)

    # Log environment variables
    env_vars = get_env_vars()
    if env_vars:
        logger.info("Environment Variables:")
        for key, value in sorted(env_vars.items()):
            logger.info(f"  {key}={value}")
    else:
        logger.info("No MERAKI_EXPORTER environment variables found")

    logger.info("-" * 80)

    # Log feature status
    logger.info("Feature Status:")

    # API Configuration
    logger.info(f"  API Base URL: {settings.meraki.api_base_url}")
    logger.info(f"  API Timeout: {settings.api.timeout}s")
    logger.info(f"  API Max Retries: {settings.api.max_retries}")
    logger.info(f"  API Max Concurrent Requests: {settings.api.concurrency_limit}")
    # OpenTelemetry
    if settings.otel.enabled:
        logger.info("  OpenTelemetry: ENABLED")
        logger.info(f"    - Endpoint: {settings.otel.endpoint}")
        logger.info(f"    - Export Interval: {settings.otel.export_interval}s")
        logger.info(f"    - Service Name: {settings.otel.service_name}")
        if settings.otel.resource_attributes:
            logger.info(
                f"    - Resource Attributes: {json.dumps(settings.otel.resource_attributes)}"
            )
    else:
        logger.info("  OpenTelemetry: DISABLED")

    # Update Intervals
    logger.info("  Update Intervals:")
    logger.info(f"    - Fast: {settings.update_intervals.fast}s (sensor metrics)")
    logger.info(f"    - Medium: {settings.update_intervals.medium}s (device/org metrics)")
    logger.info(f"    - Slow: {settings.update_intervals.slow}s (config/license metrics)")

    # Server Configuration
    logger.info("  Server:")
    logger.info(f"    - Host: {settings.server.host}")
    logger.info(f"    - Port: {settings.server.port}")

    # Organization Configuration
    if settings.meraki.org_id:
        logger.info(f"  Organization Filter: {settings.meraki.org_id}")
    else:
        logger.info("  Organization Filter: None (all organizations)")

    # Collector Status
    all_collectors = ["organization", "device", "network_health", "alerts", "mt_sensor", "config"]
    enabled = settings.collectors.enabled_collectors
    disabled = [c for c in all_collectors if c not in enabled]

    # Format collector names for display
    display_names = {
        "organization": "Organization",
        "device": "Device",
        "network_health": "Network Health",
        "alerts": "Alerts",
        "mt_sensor": "MT Sensors",
        "config": "Config Changes",
    }

    enabled_display = [display_names.get(c, c) for c in enabled]
    disabled_display = [display_names.get(c, c) for c in disabled]

    logger.info(
        f"  Enabled Collectors: {', '.join(enabled_display) if enabled_display else 'None'}"
    )
    if disabled_display:
        logger.info(f"  Disabled Collectors: {', '.join(disabled_display)}")

    logger.info("=" * 80)
