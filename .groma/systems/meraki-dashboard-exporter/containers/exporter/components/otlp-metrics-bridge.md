---
type: C4 Component
title: OTLP metrics bridge (core/otel_metrics.py)
status: stable
groma:
  id: otlp-metrics-bridge
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/otel_metrics.py
  technology: Python, OpenTelemetry SDK, OTLP gRPC
  group: Self-observability
description: Opt-in periodic push of the Prometheus registry over OTLP
---

Off by default. When enabled it reads the live Prometheus registry on a timer, translates each metric family into the OTLP metrics data model by hand and exports it over OTLP gRPC. It creates no OTel instruments and does not change `/metrics` beyond its own four self-observability series; the Prometheus registry stays the source of truth.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/otel_metrics.py](../../../../../../src/meraki_dashboard_exporter/core/otel_metrics.py) | [otlp-backend](../../../../../externals/otlp-backend.md) | Pushes metric snapshots | OTLP gRPC |
