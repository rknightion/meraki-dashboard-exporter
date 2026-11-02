---
type: C4 Component
title: Inventory service (services/inventory.py)
status: stable
groma:
  id: inventory
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/services/inventory.py
    - scanner: python
      file: src/meraki_dashboard_exporter/services/__init__.py
  technology: Python
  group: Shared services
description: Shared TTL cache of organizations, networks, devices and licences
---

`OrganizationInventory` is built once by the collector manager and shared by every collector. It caches full, unfiltered API responses and applies the network filter on every read, so one org-wide fetch serves filtered and unfiltered callers. `get_networks(org_id)` is the single enforcement point for the network filter, and `get_allowed_network_ids()` gives collectors an allow-list for org-wide responses (`None` means accept every row). Expiry has jitter, and availabilities and licences have their own TTLs.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/services/inventory.py](../../../../../../src/meraki_dashboard_exporter/services/inventory.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Fetches inventory | facade_for().call |
| [src/meraki_dashboard_exporter/services/inventory.py](../../../../../../src/meraki_dashboard_exporter/services/inventory.py) | [src/meraki_dashboard_exporter/core/network_filter.py](../../../../../../src/meraki_dashboard_exporter/core/network_filter.py) | Applies network filter | Python call |
