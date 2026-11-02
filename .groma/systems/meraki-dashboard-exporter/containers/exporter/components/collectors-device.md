---
type: C4 Component
title: Devices
status: stable
groma:
  id: collectors-device
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/device.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/base.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/devices/__init__.py
  technology: Python
  group: Collectors
description: Common device metrics and dispatch to the device-family collectors
---

`DeviceCollector` owns common device metrics such as `meraki_device_up`, availability and memory, and calls the device-family collectors per device or org-wide. `BaseDeviceCollector` (`devices/base.py`) is their shared base. It directly owns the org-wide MX HA and uplink sub-collectors and the MS stack and power sub-collectors, and applies device up or down events from the webhook receiver. Every device series is tracked under `DeviceCollector`.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/collectors/devices/mr/collector.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mr/collector.py) | Delegates access points | Python call |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/collectors/devices/ms.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/ms.py) | Delegates switches | Python call |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/collectors/devices/mx.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mx.py) | Delegates appliances | Python call |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/collectors/devices/mt.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mt.py) | Delegates sensors | Python call |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/collectors/devices/mv.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mv.py) | Delegates cameras | Python call |
| [src/meraki_dashboard_exporter/collectors/device.py](../../../../../../src/meraki_dashboard_exporter/collectors/device.py) | [src/meraki_dashboard_exporter/collectors/devices/mg.py](../../../../../../src/meraki_dashboard_exporter/collectors/devices/mg.py) | Delegates cellular gateways | Python call |
