---
type: C4 Component
title: Webhook receiver
status: stable
groma:
  id: webhook-receiver
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/webhook_handler.py
    - scanner: python
      file: src/meraki_dashboard_exporter/models/webhook.py
    - scanner: python
      file: src/meraki_dashboard_exporter/models/__init__.py
  technology: Python, Pydantic
  group: Process and HTTP surface
description: Validates Meraki webhook deliveries and applies device state
---

Off by default. When enabled, startup refuses to run without a shared secret unless the operator explicitly opts in to insecure mode. `WebhookHandler` validates the shared secret with a constant-time compare, drops stale and replayed deliveries, records bounded outcome metrics (alert types and org IDs are bounded before they become labels), and can apply a device up or down event straight to the device collector's gauges. Payloads are parsed into the Pydantic models in `models/webhook.py`.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/webhook_handler.py](../../../../../../src/meraki_dashboard_exporter/core/webhook_handler.py) | [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | Applies device state | DeviceStateApplier protocol |
