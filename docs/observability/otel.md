---
title: OpenTelemetry
description: Mirroring Prometheus metrics and emitting traces via OTLP
tags:
  - opentelemetry
  - observability
---

# OpenTelemetry

The exporter can mirror all Prometheus metrics to an OpenTelemetry (OTEL) collector and emit traces for API calls and HTTP requests. Prometheus remains the primary scrape target; OTEL is an optional secondary export.

## Enable OTEL

```bash
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional
export MERAKI_EXPORTER_OTEL__SERVICE_NAME=meraki-dashboard-exporter
export MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL=60
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"environment":"production"}'
```

- **Endpoint**: OTLP gRPC (`http://host:4317`). OTLP/HTTP is not currently supported.
- **Resource attributes**: JSON string of key/value pairs.

## Metric Mirroring

The exporter uses a Prometheus-to-OTEL bridge that:
- Mirrors every Prometheus metric in the registry at the configured export interval
- Preserves labels as OTEL attributes
- Exports counters and gauges directly
- Exports histograms as an **average gauge** (OTEL histogram export is not used yet)

## Tracing and Logs

When OTEL is enabled, tracing is also initialized. See [Tracing](tracing.md) for details.

Logs remain logfmt and are not exported to OTEL by default, but they include trace context fields (`trace_id`, `span_id`, `trace_flags`) when a span is active.

## Docker Compose Example

```yaml
services:
  meraki-exporter:
    image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
    environment:
      - MERAKI_EXPORTER_MERAKI__API_KEY=your_key
      - MERAKI_EXPORTER_OTEL__ENABLED=true
      - MERAKI_EXPORTER_OTEL__ENDPOINT=http://otel-collector:4317
    ports:
      - "9099:9099"

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
```

## Troubleshooting

- Confirm `/metrics` is populated first — OTEL mirrors Prometheus.
- Check logs for OTEL bridge initialization or connection errors.
- Verify the collector is listening on the OTLP gRPC endpoint.

## Performance Notes

- Export runs in a background task at `MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL`.
- Large metric cardinality increases OTEL export size; use `/cardinality` to review.
