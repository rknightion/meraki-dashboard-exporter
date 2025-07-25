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
| `MERAKI_EXPORTER_MERAKI__API_KEY` | `SecretStr` | `PydanticUndefined` | Meraki Dashboard API key |
| `MERAKI_EXPORTER_MERAKI__ORG_ID` | `str | None` | `_(none)_` | Meraki organization ID (optional, will fetch all orgs if not set) |
| `MERAKI_EXPORTER_MERAKI__API_BASE_URL` | `str` | `https://api.meraki.com/api/v1` | Meraki API base URL (use regional endpoints if needed) |

## Logging Settings

Logging configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_LOGGING__LEVEL` | `str` | `INFO` | Logging level |

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
| `MERAKI_EXPORTER_CLIENTS__DNS_TIMEOUT` | `float` | `5.0` | DNS lookup timeout in seconds |
| `MERAKI_EXPORTER_CLIENTS__DNS_CACHE_TTL` | `int` | `21600` | DNS cache TTL in seconds (default: 6 hours) |
| `MERAKI_EXPORTER_CLIENTS__CACHE_TTL` | `int` | `3600` | Client cache TTL in seconds (for ID/hostname mappings, not metrics) |
| `MERAKI_EXPORTER_CLIENTS__MAX_CLIENTS_PER_NETWORK` | `int` | `10000` | Maximum clients to track per network |

## SNMP Settings

SNMP collector configuration for device and cloud controller metrics

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_SNMP__ENABLED` | `bool` | `False` | Enable SNMP metric collection |
| `MERAKI_EXPORTER_SNMP__TIMEOUT` | `float` | `5.0` | SNMP request timeout in seconds |
| `MERAKI_EXPORTER_SNMP__RETRIES` | `int` | `3` | SNMP request retry count |
| `MERAKI_EXPORTER_SNMP__BULK_MAX_REPETITIONS` | `int` | `25` | Maximum repetitions for SNMP BULK operations |
| `MERAKI_EXPORTER_SNMP__CONCURRENT_DEVICE_LIMIT` | `int` | `10` | Maximum concurrent SNMP device queries |
| `MERAKI_EXPORTER_SNMP__ORG_V3_AUTH_PASSWORD` | `pydantic.types.SecretStr | None` | `_(none)_` | SNMPv3 authentication password for organization/cloud controller SNMP |
| `MERAKI_EXPORTER_SNMP__ORG_V3_PRIV_PASSWORD` | `pydantic.types.SecretStr | None` | `_(none)_` | SNMPv3 privacy password for organization/cloud controller SNMP |

