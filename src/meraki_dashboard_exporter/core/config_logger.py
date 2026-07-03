"""Configuration logging utilities for startup visibility."""

from __future__ import annotations

import logging
import os
from typing import Any

import structlog

from .config import Settings
from .logging import get_logger

logger = get_logger(__name__)


REDACTED = "***REDACTED***"

# Known-safe field-name substrings that are never sensitive and may be logged in
# the clear. Matched against the field portion of a config/env key (after the
# ``MERAKI_EXPORTER_``/``MERAKI_`` prefix is stripped). This is an ALLOWLIST:
# anything NOT matching one of these is redacted by default (SEC-07). Add a new
# entry here only for a field you have confirmed carries no secret material.
_SAFE_KEY_SUBSTRINGS: frozenset[str] = frozenset({
    "host",
    "port",
    "timeout",
    "retr",  # retries / retry / max_retries
    "backoff",
    "concurrency",
    "batch",
    "delay",
    "rate_limit",
    "requests_per_second",
    "rps",
    "burst",
    "fraction",
    "jitter",
    "smoothing",
    "window",
    "interval",
    "cadence",
    "version",  # build metadata, consumed via os.environ (#634)
    "commit",  # build metadata, consumed via os.environ (#634)
    "level",
    "format",
    "enabled",
    "endpoint",
    "service_name",
    "base_url",
    "url",
    "org_id",
    "resource_attributes",
    "collector",
    "use_org_endpoint",
    "validate_kwargs",
    "region",
    "include",
    "exclude",
    "filter",
    "network",
    "product",
    "tag",
})

# Authoritative sensitive-key substrings. These are always redacted even if they
# also happen to match a safe substring (belt-and-suspenders); the allowlist
# above already redacts anything unlisted, so this set is a fast, explicit guard
# for well-known secret shapes.
_SENSITIVE_KEY_SUBSTRINGS: frozenset[str] = frozenset({
    "api_key",
    "apikey",
    "password",
    "passwd",
    "passphrase",
    "secret",
    "token",
    "credential",
    "private",
    "cert",
    "cookie",
    "session",
    "bearer",
    "signature",
    "salt",
})

# Env-key prefixes stripped before matching so the ``exporter``/``meraki`` prefix
# noise cannot accidentally match safe/sensitive substrings.
_KEY_PREFIXES: tuple[str, ...] = ("meraki_exporter_", "meraki_")


def mask_sensitive_value(key: str, value: Any) -> Any:
    """Mask configuration values, redacting by default (allowlist model, SEC-07).

    The previous implementation was a substring *denylist*: any field whose name
    did not match a known secret substring was logged in the clear, so every new
    secret-bearing config field was a latent leak. This inverts the model to
    **redact by default** — a value is only shown when its key matches the
    explicit ``_SAFE_KEY_SUBSTRINGS`` allowlist and does not match the
    authoritative ``_SENSITIVE_KEY_SUBSTRINGS`` guard.

    Parameters
    ----------
    key : str
        Configuration key name (may include the ``MERAKI_EXPORTER_`` prefix).
    value : Any
        Configuration value.

    Returns
    -------
    Any
        The original value if the key is known-safe, otherwise ``"***REDACTED***"``.

    """
    field = key.lower()
    for prefix in _KEY_PREFIXES:
        if field.startswith(prefix):
            field = field[len(prefix) :]
            break

    # Authoritative sensitive guard: always redact known secret shapes.
    if any(token in field for token in _SENSITIVE_KEY_SUBSTRINGS):
        return REDACTED

    # Redact-by-default: only surface values whose key is explicitly known-safe.
    if any(token in field for token in _SAFE_KEY_SUBSTRINGS):
        return value

    return REDACTED


def get_env_vars() -> dict[str, str]:
    """Get all MERAKI_EXPORTER environment variables.

    Returns
    -------
    dict[str, str]
        Dictionary of environment variables with masked sensitive values.

    """
    env_vars = {}
    prefix = "MERAKI_EXPORTER_"

    # Get all MERAKI_EXPORTER_* variables. The bare `MERAKI_API_KEY` (without the
    # `MERAKI_EXPORTER_` prefix) is intentionally NOT included here: it is never
    # consumed as a config source (only `MERAKI_EXPORTER_MERAKI__API_KEY` is read
    # by Settings), so dumping it was dead/misleading output (#529).
    for key, value in os.environ.items():
        if key.startswith(prefix):
            masked_value = mask_sensitive_value(key, value)
            env_vars[key] = masked_value

    return env_vars


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
        "  Scheduler",
        mode=settings.scheduler.mode,
        target_utilization=settings.scheduler.target_utilization,
        resolve_interval=f"{settings.scheduler.resolve_interval_seconds}s",
        failure_retry=f"{settings.scheduler.failure_retry_seconds}s",
    )

    log_method("  Server", host=settings.server.host, port=settings.server.port)

    if scheduling:
        log_method("-" * 80)
        log_method("Scheduling Diagnostics:")

        collector_cadences = scheduling.get("collectors", [])
        if collector_cadences:
            formatted = [
                f"{entry['collector']}@{entry['cadence_seconds']}s"
                f"(+{entry['phase_offset_seconds']}s)"
                for entry in collector_cadences
            ]
            truncated, was_truncated = _truncate_list(formatted)
            log_method(
                "  Collector Cadences",
                value=truncated,
                truncated=was_truncated,
            )

        scheduler_diag = scheduling.get("scheduler", {})
        stretched = [
            f"{g['name']} {g['interval_seconds']:.0f}s ({g['stretch_factor']:.2f}x)"
            for g in scheduler_diag.get("groups", [])
            if (g.get("stretch_factor") or 1.0) > 1.0
        ]
        if stretched:
            truncated_groups, groups_truncated = _truncate_list(stretched)
            log_method(
                "  Stretched Groups",
                value=truncated_groups,
                truncated=groups_truncated,
            )

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
