---
type: C4 Component
title: Collector manager (collectors/manager.py)
status: stable
groma:
  id: collector-manager
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/manager.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/registry.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/__init__.py
  technology: Python
  group: Collection runtime
description: Registers, admits and runs the collectors
---

`CollectorManager` imports every top-level collector module, which triggers `@register_collector`, and instantiates the classes named in `collectors.active_collectors` with the shared API handle, inventory, expiration manager, rate limiter, scheduler, org-health tracker and data-log emitter. A collector module missing from that import block never registers. It validates startup configuration and the network filter, bounds each run with `collector_timeout`, admits at most a computed number of collectors at once, and reports readiness and scheduling diagnostics.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/alerts.py](../../../../../../src/meraki_dashboard_exporter/collectors/alerts.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/clients.py](../../../../../../src/meraki_dashboard_exporter/collectors/clients.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/config.py](../../../../../../src/meraki_dashboard_exporter/collectors/config.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/insight.py](../../../../../../src/meraki_dashboard_exporter/collectors/insight.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/mt_alerts.py](../../../../../../src/meraki_dashboard_exporter/collectors/mt_alerts.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/mt_sensor.py](../../../../../../src/meraki_dashboard_exporter/collectors/mt_sensor.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/network_health.py](../../../../../../src/meraki_dashboard_exporter/collectors/network_health.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/collectors/organization.py](../../../../../../src/meraki_dashboard_exporter/collectors/organization.py) | Registers collector | @register_collector import |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/services/inventory.py](../../../../../../src/meraki_dashboard_exporter/services/inventory.py) | Builds shared inventory | Python call |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/core/scheduler.py](../../../../../../src/meraki_dashboard_exporter/core/scheduler.py) | Resolves intervals | Python call |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/core/rate_limiter.py](../../../../../../src/meraki_dashboard_exporter/core/rate_limiter.py) | Builds rate limiter | Python call |
| [src/meraki_dashboard_exporter/collectors/manager.py](../../../../../../src/meraki_dashboard_exporter/collectors/manager.py) | [src/meraki_dashboard_exporter/core/org_health.py](../../../../../../src/meraki_dashboard_exporter/core/org_health.py) | Shares org health | Python call |
