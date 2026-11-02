---
type: C4 Component
title: Endpoint scheduler (core/scheduler.py)
status: stable
groma:
  id: scheduler
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/scheduler.py
  technology: Python
  group: Collection runtime
description: Solves each endpoint group's interval from org shape and API budget
---

There are no fixed polling tiers. Each collector declares endpoint groups (name, priority, floor and cost function); the solver derives an interval per group from the organizations' shape and the effective API budget, stretching lower-priority groups when demand exceeds it. Priorities are 1 up-ness and alerts, 2 sensors, 3 performance and health, 4 configuration and inventory. `EndpointScheduler` then answers whether a group is due and exports the solved intervals as metrics.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/scheduler.py](../../../../../../src/meraki_dashboard_exporter/core/scheduler.py) | [src/meraki_dashboard_exporter/core/rate_limiter.py](../../../../../../src/meraki_dashboard_exporter/core/rate_limiter.py) | Reads effective budget | Python call |
