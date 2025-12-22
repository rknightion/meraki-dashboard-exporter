---
title: Tracing
description: Distributed tracing for Meraki API calls and HTTP endpoints
tags:
  - opentelemetry
  - tracing
  - observability
---

# Tracing

When OpenTelemetry is enabled, the exporter emits traces for Meraki API calls and FastAPI endpoints. Tracing uses OTLP gRPC and a parent-based, head-sampling strategy.

## Configuration

```bash
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional sampling (default: 0.1 = 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

Sampling behavior:
- `0.0` disables tracing
- `0.1` samples ~10% of traces (default)
- `1.0` samples all traces
- Child spans follow parent sampling decisions

## Instrumented Components

- **Meraki SDK (requests)**: API call timing, status, rate-limit headers
- **httpx**: Any httpx usage is traced
- **FastAPI**: All endpoints except `/health` and `/metrics`
- **Threading**: `asyncio.to_thread()` operations
- **Logging**: Trace IDs added to logfmt output

## Span Attributes

Common attributes include:
- `api.endpoint`
- `api.status_code`
- `api.duration_seconds`
- `api.retry_count`
- `meraki.request_id`, `meraki.retry_after`, `meraki.rate_limit.remaining`
- `http.response.size`

## Span Metrics (RED)

When tracing is enabled, the exporter generates RED metrics from spans:
- `meraki_span_requests_total`
- `meraki_span_duration_seconds` (histogram)
- `meraki_span_errors_total`

These appear in `/metrics` and can be queried for SLIs/SLOs.

## Troubleshooting

- Confirm OTEL is enabled and the collector is reachable.
- Check logs for tracing initialization errors.
- Ensure `MERAKI_EXPORTER_OTEL__SAMPLING_RATE` is > 0.
- Remember that `/health` and `/metrics` are excluded from tracing.

## Log Correlation Example

```text
timestamp=2025-12-22T10:30:45.123Z level=info event="Collected metrics" trace_id=... span_id=...
```
