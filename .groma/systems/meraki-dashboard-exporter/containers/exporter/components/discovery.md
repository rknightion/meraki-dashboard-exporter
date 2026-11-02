---
type: C4 Component
title: Discovery (core/discovery.py)
status: stable
groma:
  id: discovery
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/discovery.py
  technology: Python
  group: Collection runtime
description: Resolves the organization scope and logs the environment at startup
---

Resolves which organizations to collect and runs a one-time discovery pass that logs the environment the API key can see. It is the one deliberately unfiltered network fetch, outside the network filter.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/discovery.py](../../../../../../src/meraki_dashboard_exporter/core/discovery.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Discovers organizations | facade_for().call |
