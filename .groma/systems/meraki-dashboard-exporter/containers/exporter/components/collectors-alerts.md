---
type: C4 Component
title: Alerts
status: stable
groma:
  id: collectors-alerts
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/alerts.py
  technology: Python
  group: Collectors
description: Assurance alerts and sensor alert overviews
---

`AlertsCollector` reads organization assurance alerts and per-network sensor alert overviews. Holds one of the two sanctioned direct network fetches for when the inventory is unavailable, which reapplies the network filter.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/alerts.py](../../../../../../src/meraki_dashboard_exporter/collectors/alerts.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
