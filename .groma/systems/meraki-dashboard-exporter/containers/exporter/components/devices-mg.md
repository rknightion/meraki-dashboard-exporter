---
type: C4 Component
title: MG cellular gateways
status: stable
groma:
  id: devices-mg
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mg.py
  technology: Python
  group: Device families
description: Cellular uplink status, bands, towers, eSIMs and HA
---

`MGCollector`'s per-device `collect()` is a deliberate no-op; cellular metrics come from org-wide uplink status, band, tower and eSIM endpoints.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/devices/mg.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mg.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
