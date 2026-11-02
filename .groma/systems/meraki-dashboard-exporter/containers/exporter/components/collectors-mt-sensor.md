---
type: C4 Component
title: MT sensors
status: stable
groma:
  id: collectors-mt-sensor
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/mt_sensor.py
  technology: Python
  group: Collectors
description: Fast-tier environmental sensor readings
---

`MTSensorCollector` collects MT sensor readings on their own high-priority endpoint group, using the MT device-family collector in its standalone form.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/mt_sensor.py](../../../../../../src/meraki_dashboard_exporter/collectors/mt_sensor.py) | [src/meraki_dashboard_exporter/collectors/devices/mt.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mt.py) | Reuses MT collector | MTCollector.as_standalone |
