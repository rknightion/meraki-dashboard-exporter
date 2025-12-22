---
title: OpenTelemetry
description: Mirroring Prometheus metrics and emitting traces via OTLP
tags:
  - opentelemetry
  - observability
---

# OpenTelemetry

The exporter can emit traces and mirror selected Prometheus metrics to an
OpenTelemetry (OTEL) collector. Metrics are always produced in the Prometheus
registry; export to `/metrics` and OTEL is routed independently.

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
- **Required**: `ENABLED=true` requires `ENDPOINT`; startup will fail without it.
- **Resource attributes**: JSON string of key/value pairs.
- **Metrics export**: OTEL metrics are opt-in; enable at least one
  `EXPORT_*_TO_OTEL` flag to send metrics to the collector.

## Export routing

Metrics are grouped by prefix:

- `meraki_*`: Meraki data metrics
- `meraki_exporter_*`: exporter/internal metrics

Non-meraki metrics (for example `python_*`, `process_*`) always remain on
`/metrics` and are not exported to OTEL.

Routing flags:

- `MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_PROMETHEUS`
- `MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_PROMETHEUS`
- `MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_OTEL`
- `MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_OTEL`

Prometheus export flags apply regardless of OTEL being enabled. OTEL export only
runs when `MERAKI_EXPORTER_OTEL__ENABLED=true` and an endpoint is configured.

### Examples

```bash
# OTEL metrics + Prometheus (mirror meraki_* and exporter metrics)
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317
export MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_OTEL=true
export MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_OTEL=true

# OTEL-only meraki/exporter metrics (non-meraki metrics still stay on /metrics)
export MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_PROMETHEUS=false
export MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_PROMETHEUS=false
```

## Metric Mirroring

The exporter uses a Prometheus-to-OTEL bridge that:
- Mirrors selected metrics from the registry based on the export routing flags
- Preserves labels as OTEL attributes
- Exports counters and gauges directly
- Exports histograms as an **average gauge** (OTEL histogram export is not used yet)

## Tracing

Tracing is configured separately. See [Tracing](tracing.md) for details.

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

- Confirm OTEL export flags are enabled for the metrics you expect.
- `/metrics` can be filtered by the Prometheus export flags.
- Check logs for OTEL bridge initialization or connection errors.
- Verify the collector is listening on the OTLP gRPC endpoint.

## Performance Notes

- Export runs in a background task at `MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL`.
- Large metric cardinality increases OTEL export size; use `/cardinality` to review.
