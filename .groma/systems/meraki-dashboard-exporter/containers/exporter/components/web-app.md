---
type: C4 Component
title: HTTP app (app.py)
status: stable
groma:
  id: web-app
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/app.py
  technology: Python, FastAPI, Jinja2
  group: Process and HTTP surface
description: 'FastAPI app: lifecycle, background loops and every HTTP route'
---

`ExporterApp` owns startup and shutdown: it builds the API client, collector manager, metric-expiration manager, cardinality monitor, tracing, data-log emitter, OTLP metrics bridge and webhook handler, then runs the collector loops, the scheduler re-solve loop and the cardinality and resource-sampling loops. Routes: `/metrics`, `/health`, `/ready` (503 until every collector owning an enabled priority 1-3 endpoint group has succeeded once), `/status` (HTML, or JSON with `?format=json`), `/clients`, `/config` (redacted), the webhook receiver, and the control endpoints, which fail closed unless a bearer API token is configured. `create_app()` memoizes one global app instance.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/logging.py](../../../../../../src/meraki_dashboard_exporter/core/logging.py) | Sets up logging | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/otel_tracing.py](../../../../../../src/meraki_dashboard_exporter/core/otel_tracing.py) | Configures tracing | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/otel_data_logs.py](../../../../../../src/meraki_dashboard_exporter/core/otel_data_logs.py) | Creates data-log emitter | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/otel_metrics.py](../../../../../../src/meraki_dashboard_exporter/core/otel_metrics.py) | Starts metrics bridge | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/build_info.py](../../../../../../src/meraki_dashboard_exporter/core/build_info.py) | Registers build info | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/api/client.py](../../../../../../src/meraki_dashboard_exporter/api/client.py) | Builds API client | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/metric_expiration.py](../../../../../../src/meraki_dashboard_exporter/core/metric_expiration.py) | Runs expiry loop | asyncio task |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | Runs collectors | asyncio tasks |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/discovery.py](../../../../../../src/meraki_dashboard_exporter/core/discovery.py) | Runs discovery | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/cardinality.py](../../../../../../src/meraki_dashboard_exporter/core/cardinality.py) | Monitors cardinality | asyncio task |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/core/webhook_handler.py](../../../../../../src/meraki_dashboard_exporter/core/webhook_handler.py) | Handles webhooks | Python call |
| [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | [src/meraki_dashboard_exporter/services/status.py](../../../../../../src/meraki_dashboard_exporter/services/status.py) | Builds status snapshot | Python call |
