# Configuration Reference

This document provides a comprehensive reference for all configuration options available in the Meraki Dashboard Exporter.

## Overview

The exporter can be configured using environment variables or configuration files.
All configuration is based on Pydantic models with built-in validation.

## Environment Variable Format

Configuration follows a hierarchical structure using environment variables:

- **Main settings**: `MERAKI_EXPORTER_{SETTING}`
- **Nested settings**: `MERAKI_EXPORTER_{SECTION}__{SETTING}`
- **Special case**: `MERAKI_API_KEY` (no prefix required)

!!! example "Environment Variable Examples"
    ```bash
    # Main setting
    export MERAKI_EXPORTER_LOG_LEVEL=INFO

    # Nested setting
    export MERAKI_EXPORTER_API__TIMEOUT=30

    # API key (special case)
    export MERAKI_API_KEY=your_api_key_here
    ```

## Main Settings

These are the primary configuration options for the exporter:

| Environment Variable | Type | Default | Required | Description |
|---------------------|------|---------|----------|-------------|
| `MERAKI_EXPORTER_PROFILE` | `str | None` | `_(none)_` | ❌ No | Configuration profile to use (development, production, high_volume, minimal) |
| `MERAKI_API_KEY` | `SecretStr` | `PydanticUndefined` | ✅ Yes | Meraki Dashboard API key |
| `MERAKI_EXPORTER_ORG_ID` | `str | None` | `_(none)_` | ❌ No | Meraki organization ID (optional, will fetch all orgs if not set) |
| `MERAKI_EXPORTER_API_BASE_URL` | `str` | `https://api.meraki.com/api/v1` | ❌ No | Meraki API base URL (use regional endpoints if needed) |
| `MERAKI_EXPORTER_LOG_LEVEL` | `Literal` | `INFO` | ❌ No | Logging level |

## API Settings

Configuration for Meraki API interactions

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_API__MAX_RETRIES` | `int` | `3` | Maximum number of retries for API requests |
| `MERAKI_EXPORTER_API__TIMEOUT` | `int` | `30` | API request timeout in seconds |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` | `int` | `5` | Maximum concurrent API requests |
| `MERAKI_EXPORTER_API__BATCH_SIZE` | `int` | `10` | Default batch size for API operations |
| `MERAKI_EXPORTER_API__BATCH_DELAY` | `float` | `0.5` | Delay between batches in seconds |
| `MERAKI_EXPORTER_API__RATE_LIMIT_RETRY_WAIT` | `int` | `5` | Wait time in seconds when rate limited |
| `MERAKI_EXPORTER_API__ACTION_BATCH_RETRY_WAIT` | `int` | `10` | Wait time for action batch retries |

## Update Intervals

Control how often different types of metrics are collected

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_UPDATE_INTERVALS__FAST` | `int` | `60` | Interval for fast-moving data (sensors) in seconds |
| `MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM` | `int` | `300` | Interval for medium-moving data (device metrics) in seconds |
| `MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW` | `int` | `900` | Interval for slow-moving data (configuration) in seconds |

## Server Settings

HTTP server configuration for the metrics endpoint

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_SERVER__HOST` | `str` | `0.0.0.0` | Host to bind the exporter to |
| `MERAKI_EXPORTER_SERVER__PORT` | `int` | `9099` | Port to bind the exporter to |
| `MERAKI_EXPORTER_SERVER__PATH_PREFIX` | `str` | `` | URL path prefix for all endpoints |
| `MERAKI_EXPORTER_SERVER__ENABLE_HEALTH_CHECK` | `bool` | `True` | Enable /health endpoint |

## OpenTelemetry Settings

OpenTelemetry observability configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_OTEL__ENABLED` | `bool` | `False` | Enable OpenTelemetry export |
| `MERAKI_EXPORTER_OTEL__ENDPOINT` | `str | None` | `_(none)_` | OpenTelemetry collector endpoint |
| `MERAKI_EXPORTER_OTEL__SERVICE_NAME` | `str` | `meraki-dashboard-exporter` | Service name for OpenTelemetry |
| `MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL` | `int` | `60` | Export interval for OpenTelemetry metrics |
| `MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES` | `dict` | `PydanticUndefined` | Additional resource attributes for OpenTelemetry |

## Monitoring Settings

Internal monitoring and alerting configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_MONITORING__MAX_CONSECUTIVE_FAILURES` | `int` | `10` | Maximum consecutive failures before alerting |
| `MERAKI_EXPORTER_MONITORING__HISTOGRAM_BUCKETS` | `list` | `[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]` | Histogram buckets for collector duration metrics |
| `MERAKI_EXPORTER_MONITORING__LICENSE_EXPIRATION_WARNING_DAYS` | `int` | `30` | Days before license expiration to start warning |

## Collector Settings

Enable/disable specific metric collectors

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS` | `set` | `PydanticUndefined` | Enabled collector names |
| `MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS` | `set` | `PydanticUndefined` | Explicitly disabled collectors (overrides enabled) |
| `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT` | `int` | `120` | Timeout for individual collector runs in seconds |

## Client Settings

Client data collection and DNS resolution settings

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_CLIENTS__ENABLED` | `bool` | `False` | Enable client data collection |
| `MERAKI_EXPORTER_CLIENTS__DNS_SERVER` | `str | None` | `_(none)_` | DNS server for reverse lookups (uses system default if not set) |
| `MERAKI_EXPORTER_CLIENTS__DNS_TIMEOUT` | `float` | `2.0` | DNS lookup timeout in seconds |
| `MERAKI_EXPORTER_CLIENTS__CACHE_TTL` | `int` | `3600` | Client cache TTL in seconds (for ID/hostname mappings, not metrics) |
| `MERAKI_EXPORTER_CLIENTS__MAX_CLIENTS_PER_NETWORK` | `int` | `10000` | Maximum clients to track per network |

## Configuration Profiles

Pre-defined configuration profiles provide optimized settings for different deployment scenarios. Activate a profile using `MERAKI_EXPORTER_PROFILE`.

### Development

**Description:** Development environment with relaxed limits

**Usage:**
```bash
export MERAKI_EXPORTER_PROFILE=development
```

**Key Settings:**

- **API Concurrency:** 2 concurrent requests
- **Batch Size:** 5 items per batch
- **API Timeout:** 60 seconds
- **Update Intervals:** 60s / 300s / 900s
- **Max Failures:** 3
- **Collector Timeout:** 120 seconds
- **Client Collection:** Disabled

### Production

**Description:** Production environment with standard settings

**Usage:**
```bash
export MERAKI_EXPORTER_PROFILE=production
```

**Key Settings:**

- **API Concurrency:** 5 concurrent requests
- **Batch Size:** 10 items per batch
- **API Timeout:** 30 seconds
- **Update Intervals:** 60s / 300s / 900s
- **Max Failures:** 10
- **Collector Timeout:** 120 seconds
- **Client Collection:** Disabled

### High_Volume

**Description:** High volume environment with aggressive settings

**Usage:**
```bash
export MERAKI_EXPORTER_PROFILE=high_volume
```

**Key Settings:**

- **API Concurrency:** 10 concurrent requests
- **Batch Size:** 20 items per batch
- **API Timeout:** 45 seconds
- **Update Intervals:** 120s / 600s / 1800s
- **Max Failures:** 20
- **Collector Timeout:** 300 seconds
- **Client Collection:** Disabled

### Minimal

**Description:** Minimal configuration for testing

**Usage:**
```bash
export MERAKI_EXPORTER_PROFILE=minimal
```

**Key Settings:**

- **API Concurrency:** 1 concurrent requests
- **Batch Size:** 1 items per batch
- **API Timeout:** 30 seconds
- **Update Intervals:** 300s / 600s / 1800s
- **Max Failures:** 10
- **Collector Timeout:** 120 seconds
- **Client Collection:** Disabled

## Configuration Examples

### Basic Setup

Minimal configuration for getting started:

```bash
export MERAKI_API_KEY=your_api_key_here
export MERAKI_EXPORTER_LOG_LEVEL=INFO
```

### Production Deployment

Production-ready configuration with optimized settings:

```bash
export MERAKI_API_KEY=your_api_key_here
export MERAKI_EXPORTER_PROFILE=production
export MERAKI_EXPORTER_ORG_ID=123456
export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=10
export MERAKI_EXPORTER_API__TIMEOUT=45
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://otel-collector:4317
```

### High Volume Environment

Configuration for large organizations with many devices:

```bash
export MERAKI_API_KEY=your_api_key_here
export MERAKI_EXPORTER_PROFILE=high_volume
export MERAKI_EXPORTER_UPDATE_INTERVALS__FAST=120
export MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM=600
export MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW=1800
export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=15
export MERAKI_EXPORTER_API__BATCH_SIZE=20
export MERAKI_EXPORTER_MONITORING__MAX_CONSECUTIVE_FAILURES=20
```

### Development Environment

Configuration for development and testing:

```bash
export MERAKI_API_KEY=your_api_key_here
export MERAKI_EXPORTER_PROFILE=development
export MERAKI_EXPORTER_LOG_LEVEL=DEBUG
export MERAKI_EXPORTER_SERVER__PORT=9099
```

## Best Practices

!!! tip "Configuration Recommendations"
    - **Use profiles** for consistent deployments across environments
    - **Set organization ID** (`MERAKI_EXPORTER_ORG_ID`) to limit scope and improve performance
    - **Adjust intervals** based on your monitoring needs and API rate limits
    - **Enable OpenTelemetry** in production for better observability
    - **Monitor API usage** to stay within Meraki's rate limits

!!! warning "Important Notes"
    - The `MERAKI_API_KEY` is required and must be kept secure
    - Some metrics require specific Meraki license types
    - Network-specific collectors may not work with all device types
    - Rate limiting is automatically handled but can be tuned
