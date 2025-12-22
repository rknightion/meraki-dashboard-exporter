# Configuration Reference

This document provides a comprehensive reference for all configuration options available in the Meraki Dashboard Exporter.

## Overview

The exporter can be configured using environment variables.
All configuration is based on Pydantic models with built-in validation.

## Environment Variable Format

Configuration follows a hierarchical structure using environment variables:

- **All settings**: `MERAKI_EXPORTER_{SECTION}__{SETTING}`
- **Double underscore** (`__`) separates nested configuration levels

!!! example "Environment Variable Examples"
    ```bash
    # Meraki API configuration
    export MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here
    export MERAKI_EXPORTER_MERAKI__ORG_ID=123456

    # Logging configuration
    export MERAKI_EXPORTER_LOGGING__LEVEL=INFO

    # API settings
    export MERAKI_EXPORTER_API__TIMEOUT=30
    export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=5
    ```

## Meraki Settings

Core Meraki API configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_MERAKI__API_KEY` | `SecretStr` | `_(required)_` | Meraki Dashboard API key |
| `MERAKI_EXPORTER_MERAKI__ORG_ID` | `str | None` | `_(none)_` | Meraki organization ID (optional, will fetch all orgs if not set) |
| `MERAKI_EXPORTER_MERAKI__API_BASE_URL` | `str` | `https://api.meraki.com/api/v1` | Meraki API base URL (use regional endpoints if needed) |

## Logging Settings

Logging configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_LOGGING__LEVEL` | `str` | `INFO` | Logging level (pattern: ^(DEBUG\|INFO\|WARNING\|ERROR\|CRITICAL)$) |

## API Settings

Configuration for Meraki API interactions

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_API__MAX_RETRIES` | `int` | `3` | Maximum number of retries for API requests (min: 0, max: 10) |
| `MERAKI_EXPORTER_API__TIMEOUT` | `int` | `30` | API request timeout in seconds (min: 10, max: 300) |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` | `int` | `5` | Maximum concurrent API requests (min: 1, max: 20) |
| `MERAKI_EXPORTER_API__BATCH_SIZE` | `int` | `20` | Default batch size for API operations (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__DEVICE_BATCH_SIZE` | `int` | `20` | Batch size for device operations (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__NETWORK_BATCH_SIZE` | `int` | `30` | Batch size for network operations (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__CLIENT_BATCH_SIZE` | `int` | `20` | Batch size for client operations (e.g., MR client metrics) (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__BATCH_DELAY` | `float` | `0.5` | Delay between batches in seconds (min: 0.0, max: 5.0) |
| `MERAKI_EXPORTER_API__RATE_LIMIT_RETRY_WAIT` | `int` | `5` | Wait time in seconds when rate limited (min: 1, max: 60) |
| `MERAKI_EXPORTER_API__ACTION_BATCH_RETRY_WAIT` | `int` | `10` | Wait time for action batch retries (min: 1, max: 60) |

## Update Intervals

Control how often different types of metrics are collected

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_UPDATE_INTERVALS__FAST` | `int` | `60` | Interval for fast-moving data (sensors) in seconds (min: 30, max: 300) |
| `MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM` | `int` | `300` | Interval for medium-moving data (device metrics) in seconds (min: 300, max: 1800) |
| `MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW` | `int` | `900` | Interval for slow-moving data (configuration) in seconds (min: 600, max: 3600) |

`MEDIUM` must be greater than or equal to `FAST`, `SLOW` must be greater than or equal to `MEDIUM`, and `MEDIUM` must be a multiple of `FAST`.

## Server Settings

HTTP server configuration for the metrics endpoint

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_SERVER__HOST` | `str` | `0.0.0.0` | Host to bind the exporter to |
| `MERAKI_EXPORTER_SERVER__PORT` | `int` | `9099` | Port to bind the exporter to (min: 1, max: 65535) |

## Webhook Settings

Webhook receiver configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_WEBHOOKS__ENABLED` | `bool` | `False` | Enable webhook receiver endpoint |
| `MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` | `SecretStr | None` | `_(none)_` | Shared secret for webhook validation (recommended) |
| `MERAKI_EXPORTER_WEBHOOKS__REQUIRE_SECRET` | `bool` | `True` | Require shared secret validation (disable for testing only) |
| `MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE` | `int` | `1048576` | Maximum webhook payload size in bytes (min: 1024, max: 10485760) |

Webhooks are received on `POST /api/webhooks/meraki` when enabled.

## OpenTelemetry Settings

OpenTelemetry observability configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_OTEL__ENABLED` | `bool` | `False` | Enable OpenTelemetry export |
| `MERAKI_EXPORTER_OTEL__ENDPOINT` | `str | None` | `_(none)_` | OpenTelemetry collector endpoint |
| `MERAKI_EXPORTER_OTEL__SERVICE_NAME` | `str` | `meraki-dashboard-exporter` | Service name for OpenTelemetry |
| `MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL` | `int` | `60` | Export interval for OpenTelemetry metrics (min: 10, max: 300) |
| `MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES` | `dict[str, str]` | `{}` | Additional resource attributes for OpenTelemetry |
| `MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_PROMETHEUS` | `bool` | `True` | Export Meraki network metrics to Prometheus /metrics endpoint |
| `MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_OTEL` | `bool` | `False` | Export Meraki network metrics to OpenTelemetry collector |
| `MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_PROMETHEUS` | `bool` | `True` | Export internal exporter metrics (meraki_exporter_*) to Prometheus |
| `MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_OTEL` | `bool` | `False` | Export internal exporter metrics to OpenTelemetry collector |
| `MERAKI_EXPORTER_OTEL__TRACING_ENABLED` | `bool` | `True` | Enable distributed tracing (requires enabled=true and endpoint) |

## Monitoring Settings

Internal monitoring and alerting configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_MONITORING__MAX_CONSECUTIVE_FAILURES` | `int` | `10` | Maximum consecutive failures before alerting (min: 1, max: 100) |
| `MERAKI_EXPORTER_MONITORING__HISTOGRAM_BUCKETS` | `list[float]` | `[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]` | Histogram buckets for collector duration metrics |
| `MERAKI_EXPORTER_MONITORING__LICENSE_EXPIRATION_WARNING_DAYS` | `int` | `30` | Days before license expiration to start warning (min: 7, max: 90) |
| `MERAKI_EXPORTER_MONITORING__METRIC_TTL_MULTIPLIER` | `float` | `2.0` | Multiplier for metric TTL (collection_interval * multiplier) (min: 1.0, max: 10.0) |

## Collector Settings

Enable/disable specific metric collectors

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS` | `set[str]` | `["alerts", "clients", "config", "device", "mtsensor", "networkhealth", "organization"]` | Enabled collector names |
| `MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS` | `set[str]` | `[]` | Explicitly disabled collectors (overrides enabled) |
| `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT` | `int` | `120` | Timeout for individual collector runs in seconds (min: 30, max: 600) |

## Client Settings

Client data collection and DNS resolution settings

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_CLIENTS__ENABLED` | `bool` | `False` | Enable client data collection |
| `MERAKI_EXPORTER_CLIENTS__DNS_SERVER` | `str | None` | `_(none)_` | DNS server for reverse lookups (uses system default if not set) |
| `MERAKI_EXPORTER_CLIENTS__DNS_TIMEOUT` | `float` | `5.0` | DNS lookup timeout in seconds (min: 0.5, max: 10.0) |
| `MERAKI_EXPORTER_CLIENTS__DNS_CACHE_TTL` | `int` | `21600` | DNS cache TTL in seconds (default: 6 hours) (min: 300, max: 86400) |
| `MERAKI_EXPORTER_CLIENTS__CACHE_TTL` | `int` | `3600` | Client cache TTL in seconds (for ID/hostname mappings, not metrics) (min: 300, max: 86400) |
| `MERAKI_EXPORTER_CLIENTS__MAX_CLIENTS_PER_NETWORK` | `int` | `10000` | Maximum clients to track per network (min: 100, max: 50000) |

## Additional Runtime Options

Some runtime knobs are read directly from environment variables and are not part of the Pydantic settings model:

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_OTEL__SAMPLING_RATE` | `float` | `0.1` | Trace sampling rate between 0 and 1 |
