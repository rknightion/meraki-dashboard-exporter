---
type: C4 Component
title: Tracing (core/otel_tracing.py)
status: stable
groma:
  id: tracing
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/otel_tracing.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/exemplars.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/span_metrics.py
  technology: Python, OpenTelemetry SDK, OTLP gRPC
  group: Self-observability
description: OpenTelemetry tracing for self-observability
---

Sets up the tracer provider and OTLP gRPC span exporter when OpenTelemetry is enabled, and supplies the resource and credential helpers the other OTLP channels reuse. `exemplars.py` links metric samples to traces. `span_metrics.py` is a deprecated stub kept after span metrics were removed.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/otel_tracing.py](../../../../../../src/meraki_dashboard_exporter/core/otel_tracing.py) | [otlp-backend](../../../../../externals/otlp-backend.md) | Exports traces | OTLP gRPC |
