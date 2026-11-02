---
type: C4 Component
title: MR wireless
status: stable
groma:
  id: devices-mr
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/collector.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/__init__.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/catalyst.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/client_logs.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/clients.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/firewall.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/performance.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/rf_profiles.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/signal_quality.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mr/wireless.py
  technology: Python
  group: Device families
description: 'MR access points: clients, ethernet, packet loss, CPU, radios, SSIDs'
---

A thin `MRCollector` coordinator with one submodule per domain: clients, performance (ethernet, power, packet loss, CPU), wireless (radios, SSID status and org-level SSID usage), SSID firewall, RF profiles, signal quality, Catalyst wireless controllers and per-client data logs. Submodules write straight to the device collector's gauges. Live-tools and beta action endpoints are never wired into this path.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/devices/mr/client_logs.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mr/client_logs.py) | [src/meraki_dashboard_exporter/core/otel_data_logs.py](../../../../../../src/meraki_dashboard_exporter/core/otel_data_logs.py) | Emits client data logs | DataLogEmitter |
