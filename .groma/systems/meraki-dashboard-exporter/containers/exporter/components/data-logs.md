---
type: C4 Component
title: Data-log emitter (core/otel_data_logs.py)
status: stable
groma:
  id: data-logs
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/otel_data_logs.py
  technology: Python, OpenTelemetry logs SDK, OTLP gRPC
  group: Self-observability
description: Opt-in OTLP log channel for per-entity product data
---

The destination for per-client, per-request or per-delivery detail that must not become a Prometheus label. Off by default and gated per event, so a disabled event costs a boolean check and no API call. It builds a private LoggerProvider and exports through OTLP gRPC; it does not capture application logs. Producers include the MR client-log collector and the organization webhook-log collector. Identifiers such as client MACs are emitted only when the operator allows them.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/otel_data_logs.py](../../../../../../src/meraki_dashboard_exporter/core/otel_data_logs.py) | [otlp-backend](../../../../../externals/otlp-backend.md) | Exports data logs | OTLP gRPC |
