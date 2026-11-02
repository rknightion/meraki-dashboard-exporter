---
type: C4 Component
title: Status snapshot (services/status.py)
status: stable
groma:
  id: status
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/services/status.py
  technology: Python
  group: Process and HTTP surface
description: Data model behind the /status page and its JSON form
---

Dataclasses describing system health, collector state, API health, webhook state and data freshness, built from one snapshot of the collector manager, metric-expiration manager, org-health tracker and data-log emitter. `/status` renders it as HTML; `?format=json` returns `StatusSnapshot.to_dict()`. Also builds the redacted effective-configuration view for `/config`.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/services/status.py](../../../../../../src/meraki_dashboard_exporter/services/status.py) | [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | Reads collector state | Python call |
