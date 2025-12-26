---
title: Tracing
description: Distributed tracing for Meraki API calls and HTTP endpoints
tags:
  - opentelemetry
  - tracing
  - observability
---

# Tracing

When OpenTelemetry is enabled and tracing is turned on, the exporter emits traces
for Meraki API calls and FastAPI endpoints. Tracing uses a parent-based,
head-sampling strategy.

## Configuration

Enable OTEL first (see [OpenTelemetry](otel.md)), then configure sampling:

```bash
# Optional sampling (default: 0.1 = 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

Tracing requires OTEL to be enabled with an endpoint. Disable OTEL to stop traces.

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

## Span-derived Metrics

The exporter does not emit RED metrics from spans. Use your tracing backend's
metrics generation (e.g., Tempo, Jaeger, Datadog) if you need span-derived SLIs.

## Troubleshooting

- Confirm OTEL is enabled and the collector is reachable.
- Check logs for tracing initialization errors.
- Ensure `MERAKI_EXPORTER_OTEL__SAMPLING_RATE` is > 0.
- Remember that `/health` and `/metrics` are excluded from tracing.

## Log Correlation Example

```text
timestamp=2025-12-22T10:30:45.123Z level=info event="Collected metrics" trace_id=... span_id=...
```
