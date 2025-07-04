# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a prometheus exporter that connects to the Cisco Meraki Dashhboard API and exposes various metrics as a prometheus exporter. It also acts as an opentelementry collector pushing metrics and logs to an OTEL endpoint.

## Development Patterns

We use the Meraki Dashboard Python API from https://github.com/meraki/dashboard-api-python
Meraki Dashboard API Docs are available at https://developer.cisco.com/meraki/api-v1/api-index/
We use uv for all python project management. New dependencies can be added with `uv add requests`
We use ruff for all python linting
We use ty for all python type checking
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
- Use `total_pages='all'` for pagination
- You are responsible for timekeeping and keeping data about the Meraki API up to date in our internal state (we do not wait for users to hit the exporter to update data)

## Metrics Guidelines
- Use asyncio + anyio; expose /metrics via a Starlette or FastAPI app; Prometheus client supports async.
- Early returns: Keep; combines neatly with match (PEP 636) for dispatching OTel signals.
- Logging: structlog configured with an OTLP JSON processor so logs and traces share context.
- Constants: class MetricName(StrEnum): HTTP_REQUESTS_TOTAL = "http_requests_total", avoiding scattered strings.
