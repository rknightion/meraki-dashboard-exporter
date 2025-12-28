"""Configuration logging utilities for startup visibility."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import structlog

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
        # Never expose sensitive values (API keys, tokens, secrets).
        return "***REDACTED***"

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


def _truncate_list(values: list[str], max_items: int = 20) -> tuple[list[str], bool]:
    """Truncate a list for logging to avoid excessive output."""
    if len(values) <= max_items:
        return values, False
    return values[:max_items], True


def _get_unfiltered_logger() -> Any:
    """Create a logger that bypasses level filtering for startup summaries."""
    config = structlog.get_config()
    return structlog.wrap_logger(
        structlog.PrintLoggerFactory()(),
        processors=config.get("processors"),
        wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        context_class=config.get("context_class", dict),
        cache_logger_on_first_use=False,
    )


def log_startup_summary(
    settings: Settings,
    discovery_summary: dict[str, Any] | None = None,
    scheduling: dict[str, Any] | None = None,
) -> None:
    """Log a one-time startup summary with config + discovery context.

    This is intentionally logged at WARNING level to remain visible when the
    log level is set to WARN (and uses an unfiltered logger to avoid suppression).
    """
    startup_logger = _get_unfiltered_logger()
    log_method = startup_logger.warning

    log_method("=" * 80)
    log_method("Meraki Dashboard Exporter Startup Summary")
    log_method("=" * 80)

    # Environment variables
    env_vars = get_env_vars()
    if env_vars:
        log_method("Environment Variables:")
        for key, value in sorted(env_vars.items()):
            log_method(f"  {key}={value}")
    else:
        log_method("No MERAKI_EXPORTER environment variables found")

    log_method("-" * 80)
    log_method("Configuration Summary:")

    log_method("  API Base URL", value=settings.meraki.api_base_url)
    log_method("  API Timeout", value=f"{settings.api.timeout}s")
    log_method("  API Max Retries", value=settings.api.max_retries)
    log_method("  API Concurrency Limit", value=settings.api.concurrency_limit)
    log_method(
        "  API Batch Sizes",
        value={
            "default": settings.api.batch_size,
            "device": settings.api.device_batch_size,
            "network": settings.api.network_batch_size,
            "client": settings.api.client_batch_size,
        },
    )
    log_method("  API Batch Delay", value=f"{settings.api.batch_delay}s")
    log_method(
        "  API Rate Limiter",
        enabled=settings.api.rate_limit_enabled,
        rps=settings.api.rate_limit_requests_per_second,
        burst=settings.api.rate_limit_burst,
        share_fraction=settings.api.rate_limit_shared_fraction,
        jitter_ratio=settings.api.rate_limit_jitter_ratio,
    )
    log_method(
        "  Smoothing",
        enabled=settings.api.smoothing_enabled,
        window_ratio=settings.api.smoothing_window_ratio,
        min_batch_delay=f"{settings.api.smoothing_min_batch_delay}s",
        max_batch_delay=f"{settings.api.smoothing_max_batch_delay}s",
    )
    log_method(
        "  Collector Timeout",
        value=f"{settings.collectors.collector_timeout}s",
    )
    smoothing_cap = max(0.0, float(settings.collectors.collector_timeout) - 10.0)
    log_method(
        "  Smoothing Window Cap",
        value=f"{smoothing_cap:.1f}s",
    )
    log_method(
        "  Switch/Client Intervals",
        ms_port_usage_interval=f"{settings.api.ms_port_usage_interval}s",
        ms_packet_stats_interval=f"{settings.api.ms_packet_stats_interval}s",
        client_app_usage_interval=f"{settings.api.client_app_usage_interval}s",
        ms_port_status_org_endpoint=settings.api.ms_port_status_use_org_endpoint,
    )

    if settings.otel.enabled:
        log_method("  OpenTelemetry", status="ENABLED")
        log_method("  OTEL Endpoint", value=settings.otel.endpoint)
        log_method("  OTEL Service Name", value=settings.otel.service_name)
        log_method("  OTEL Tracing", value="enabled")
    else:
        log_method("  OpenTelemetry", status="DISABLED")

    log_method(
        "  Update Intervals",
        fast=f"{settings.update_intervals.fast}s",
        medium=f"{settings.update_intervals.medium}s",
        slow=f"{settings.update_intervals.slow}s",
    )
    log_method(
        "  Tier Jitter Window",
        fast=f"{min(10.0, settings.update_intervals.fast * 0.1):.1f}s",
        medium=f"{min(10.0, settings.update_intervals.medium * 0.1):.1f}s",
        slow=f"{min(10.0, settings.update_intervals.slow * 0.1):.1f}s",
    )

    log_method("  Server", host=settings.server.host, port=settings.server.port)

    if scheduling:
        log_method("-" * 80)
        log_method("Scheduling Diagnostics:")
        tier_schedule = scheduling.get("tiers")
        if tier_schedule:
            log_method("  Tier Schedule", value=tier_schedule)

        offsets = scheduling.get("collector_offsets", [])
        if offsets:
            formatted_offsets = [
                f"{entry['collector']}:{entry['tier']}@{entry['offset_seconds']}s"
                for entry in offsets
            ]
            truncated_offsets, offsets_truncated = _truncate_list(formatted_offsets)
            log_method(
                "  Collector Offsets",
                value=truncated_offsets,
                truncated=offsets_truncated,
            )

        endpoint_intervals = scheduling.get("endpoint_intervals")
        if endpoint_intervals:
            log_method("  Endpoint Intervals", value=endpoint_intervals)

    if settings.meraki.org_id:
        log_method("  Organization Filter", org_id=settings.meraki.org_id)
    else:
        log_method("  Organization Filter", value="None (all organizations)")

    log_method(
        "  Enabled Collectors",
        collectors=sorted(settings.collectors.active_collectors),
    )

    # Discovery summary
    if discovery_summary:
        log_method("-" * 80)
        log_method("Discovery Summary:")

        organizations = discovery_summary.get("organizations", [])
        org_names = [org.get("name", "unknown") for org in organizations]
        org_ids = [org.get("id", "") for org in organizations]
        truncated_org_names, orgs_truncated = _truncate_list(org_names)
        truncated_org_ids, _ = _truncate_list(org_ids)

        log_method(
            "  Organizations",
            count=len(organizations),
            org_names=truncated_org_names,
            org_ids=truncated_org_ids,
            truncated=orgs_truncated,
        )

        network_summary = discovery_summary.get("networks", {})
        if network_summary:
            total_networks = 0
            combined_product_types: dict[str, int] = {}
            for org_id, summary in network_summary.items():
                total_networks += summary.get("count", 0)
                product_types = summary.get("product_types", {})
                for product_type, count in product_types.items():
                    combined_product_types[product_type] = (
                        combined_product_types.get(product_type, 0) + count
                    )
                log_method(
                    "  Networks",
                    org_id=org_id,
                    org_name=summary.get("org_name", org_id),
                    count=summary.get("count", 0),
                    product_types=product_types,
                )

            log_method(
                "  Network Totals",
                total_networks=total_networks,
                product_types=combined_product_types,
            )

        errors = discovery_summary.get("errors", [])
        if errors:
            log_method("  Discovery Errors", errors=errors)

    log_method("=" * 80)
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
        logger.info(f"    - Service Name: {settings.otel.service_name}")
        logger.info("    - Tracing: enabled")
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
