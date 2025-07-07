# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a prometheus exporter that connects to the Cisco Meraki Dashboard API and exposes various metrics as a prometheus exporter. It also acts as an opentelemetry collector pushing metrics and logs to an OTEL endpoint.

## Development Patterns

We use the Meraki Dashboard Python API from https://github.com/meraki/dashboard-api-python
Meraki Dashboard API Docs are available at https://developer.cisco.com/meraki/api-v1/api-index/
We use uv for all python project management. New dependencies can be added with `uv add requests`
We use ruff for all python linting
We use mypy for all python type checking
We do all builds via docker and ensure first class docker support for running


## Code Style

- **Formatting**: Black formatter with 88-char line length
- **Type hints**: from __future__ import annotations, TypeAlias, ParamSpec, Self, typing.NamedTuple(slots=True), typing.Annotated for units / constraints
- **Docstrings**: NumPy-docstrings + type hints
- **Constants**: Literal & Enum / StrEnum (Keep StrEnum for metric / label names; use Literal for tiny closed sets.)
- **Imports**: Group logically (stdlib, third-party, local)
- **Early returns**: Reduce nesting where possible

## API Guidelines

- Use Meraki Python SDK (never direct HTTP)
- Use `total_pages='all'` for pagination when appropriate (not all endpoints support it)
- You are responsible for timekeeping and keeping data about the Meraki API up to date in our internal state (we do not wait for users to hit the exporter to update data)
- Be aware of API module organization - endpoints like `getOrganizationWirelessClientsOverviewByDevice` are in the `wireless` module, not `organizations`
- Memory metrics use the `getOrganizationDevicesSystemMemoryUsageHistoryByInterval` endpoint without `total_pages` parameter

## Metrics Guidelines
- Use asyncio + anyio; expose /metrics via a Starlette or FastAPI app; Prometheus client supports async.
- Early returns: Keep; combines neatly with match (PEP 636) for dispatching OTel signals.
- Logging: structlog configured with an OTLP JSON processor so logs and traces share context.
- Constants: class MetricName(StrEnum): HTTP_REQUESTS_TOTAL = "http_requests_total", avoiding scattered strings.

## Update Rings

The system uses two update tiers (removed SLOW tier):
- **FAST** (60s): Sensor metrics (MT devices) - real-time environmental data
- **MEDIUM** (600s): Organization metrics, Device metrics (including port traffic), Network health

## Known API Limitations

- CPU usage and uptime metrics are not available via API for any device types
- Channel utilization metrics are collected via network health collector, not per-device
- POE budget information is not available via API (would require model lookup tables)
- Switch power usage is approximated by summing POE port consumption

## Response Format Handling

Many Meraki API responses can return data in different formats:
- Some endpoints wrap data in `{"items": [...]}` format
- Others return arrays directly
- Always check response type and handle both cases

## Testing and Validation

- Run linting: `uv run ruff check .`
- Run type checking: `uv run mypy .`
- After making changes, restart the exporter process to load new code
- Check metrics at http://localhost:9099/metrics

## Deprecated/Removed Metrics

The following metrics have been removed or replaced:
- `meraki_mr_channel_utilization_percent` → replaced by `meraki_ap_channel_utilization_2_4ghz_percent` and `meraki_ap_channel_utilization_5ghz_percent`
- `meraki_device_cpu_usage_percent` → removed (not available via API)
- `meraki_device_uptime_seconds` → removed (not available via API)

## Collector Internal Metrics

The base collector automatically tracks performance metrics:
- `meraki_collector_duration_seconds` - Time spent collecting metrics
- `meraki_collector_errors_total` - Total number of collector errors
- `meraki_collector_last_success_timestamp_seconds` - Unix timestamp of last successful collection
- `meraki_collector_api_calls_total` - Total number of API calls made

These metrics are populated automatically when collectors run and should be used for monitoring the health of the exporter itself.
