---
type: C4 Component
title: MT sensors (device family)
status: stable
groma:
  id: devices-mt
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mt.py
  technology: Python
  group: Device families
description: MT sensor readings and gateway connections
---

`MTCollector` reads the latest sensor readings and sensor-gateway connections. It has two constructors: as a sub-collector under the device collector and standalone for the MT sensor collector, so a change here lands in both.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/devices/mt.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mt.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
