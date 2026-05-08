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

- **Endpoint**: OTLP gRPC (`http://host:4317`). The exporter connects with
  `insecure=True`, so a plaintext (non-TLS) gRPC endpoint is required. Terminate
  TLS at a sidecar or local OpenTelemetry Collector if you need encryption in
  transit.
- **Required**: `ENABLED=true` requires `ENDPOINT`; startup will fail without it.
- **Resource attributes**: JSON string of key/value pairs. The
  `environment` key is promoted to the `deployment.environment` resource
  attribute (defaults to `production`).

## Tracing Configuration

Tracing is enabled whenever OTEL is enabled (with a valid endpoint). You can
configure sampling:

```bash
# Optional sampling (default: 0.1 = 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

`SAMPLING_RATE` is read directly from the environment at tracer-provider
initialization; it is not part of the pydantic settings schema, so it does not
appear in `--help` output but the `MERAKI_EXPORTER_OTEL__` prefix is still
required.

See [Tracing](tracing.md) for details on spans, sampling behavior, and
instrumented components.
