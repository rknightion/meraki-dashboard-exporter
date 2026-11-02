---
type: C4 Component
title: Network health
status: stable
groma:
  id: collectors-network-health
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/__init__.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/base.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/air_marshal.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/bluetooth.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/connection_stats.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/data_rates.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/latency_stats.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/mesh.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/rf_health.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/network_health_collectors/ssid_performance.py
  technology: Python
  group: Collectors
description: Wireless network health across eight sub-collector domains
---

`NetworkHealthCollector` narrows each organization to wireless networks once and dispatches to its sub-collectors under `network_health_collectors/`: Air Marshal, Bluetooth, connection stats, data rates, latency, mesh, RF health (org-wide channel utilization) and SSID performance. Gauges are created on the coordinator and set by the sub-collectors. On an unavailable or rate-limited fetch it emits nothing rather than a misleading zero.
