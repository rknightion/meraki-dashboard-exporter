---
title: OpenTelemetry
description: OpenTelemetry tracing configuration for the exporter
tags:
  - opentelemetry
  - tracing
  - observability
---

# OpenTelemetry

The exporter uses OpenTelemetry for **tracing only**. Metrics are exposed via
Prometheus at `/metrics` and are not exported through OTEL.

## Enable OTEL Tracing

```bash
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional
export MERAKI_EXPORTER_OTEL__SERVICE_NAME=meraki-dashboard-exporter
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"environment":"production"}'
```

- **Endpoint**: OTLP gRPC (`http://host:4317`).
- **Required**: `ENABLED=true` requires `ENDPOINT`; startup will fail without it.
- **Resource attributes**: JSON string of key/value pairs.

## Tracing Configuration

Tracing is enabled when OTEL is enabled. You can configure sampling:

```bash
# Optional sampling (default: 0.1 = 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

See [Tracing](tracing.md) for details on spans, sampling behavior, and
instrumented components.
