---
type: C4 Component
title: Constants (core/constants/)
status: stable
groma:
  id: constants
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/constants/__init__.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/constants/metrics_constants.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/constants/api_constants.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/constants/config_constants.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/constants/device_constants.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/constants/sensor_constants.py
  technology: Python
  group: Collection runtime
description: Metric-name enums and device, sensor and API constants
---

Domain constants re-exported from `core/constants/__init__.py`. `metrics_constants.py` holds the metric-name enums: `meraki_*` for Meraki data and `meraki_exporter_*` for the exporter's own instrumentation. Metric names come from these enums, never string literals. `config_constants.py` is legacy and only backs the regional base-URL allowlist.
