---
type: C4 Component
title: MT sensor alerts
status: stable
groma:
  id: collectors-mt-alerts
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/mt_alerts.py
  technology: Python
  group: Collectors
description: Count of currently alerting MT sensors per network and metric
---

`MTSensorAlertsCollector` reads the per-network current sensor-alert overview, so it goes through the inventory to enforce the network filter, together with alert profiles and sensor relationships.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/mt_alerts.py](../../../../../../src/meraki_dashboard_exporter/collectors/mt_alerts.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
