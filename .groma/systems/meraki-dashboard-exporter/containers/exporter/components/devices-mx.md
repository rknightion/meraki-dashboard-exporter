---
type: C4 Component
title: MX appliances
status: stable
groma:
  id: devices-mx
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mx.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mx_firewall.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mx_ha.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mx_uplink_health.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mx_uplink_usage.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/mx_vpn.py
  technology: Python
  group: Device families
description: Security appliance performance, firewall, VPN, HA and uplinks
---

`MXCollector` reads appliance performance and composes the firewall and security-policy and VPN sub-collectors (VPN merges Meraki and third-party peers). The HA (warm spare), uplink health and uplink usage sub-collectors live here by family but are owned by the device collector, not `MXCollector`.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/devices/mx.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mx.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
