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

- **Endpoint**: OTLP gRPC (`http://host:4317`). By default the exporter connects
  with `insecure=True` (plaintext, non-TLS). Set
  `MERAKI_EXPORTER_OTEL__INSECURE=false` to use TLS (system trust store) when
  talking to a collector endpoint that terminates TLS directly — no sidecar is
  required for that case.
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

`SAMPLING_RATE` is a normal pydantic settings field on `OTelSettings`
(`sampling_rate`, range `0.0`-`1.0`, default `0.1`), so it is validated and
documented the same as any other setting under the `MERAKI_EXPORTER_OTEL__`
prefix.

See [Tracing](tracing.md) for details on spans, sampling behavior, and
instrumented components.
