---
type: C4 Component
title: MV cameras
status: stable
groma:
  id: devices-mv
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mv.py
  technology: Python
  group: Device families
description: Camera analytics, quality and retention, Sense and onboarding
---

`MVCollector` reads camera analytics, quality and retention settings, MV Sense configuration and onboarding status. Some response contracts are deliberately lenient and marked unverified.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/devices/mv.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mv.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
