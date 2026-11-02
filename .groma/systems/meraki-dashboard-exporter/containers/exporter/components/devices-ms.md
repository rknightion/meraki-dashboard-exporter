---
type: C4 Component
title: MS switches
status: stable
groma:
  id: devices-ms
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/ms.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/ms_power.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/ms_stack.py
  technology: Python
  group: Device families
description: Switch ports, power supplies and stacks
---

`MSCollector` reads port status, usage and packet statistics, link aggregation, STP and DHCP security, preferring the org-level port-status endpoint and falling back to per-device calls where the SDK lacks it. `ms_power.py` and `ms_stack.py` cover power-supply status and stack health and are instantiated by the device collector.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/devices/ms.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/ms.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
