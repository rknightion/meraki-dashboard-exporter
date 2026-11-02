---
type: C4 Component
title: Build info
status: stable
groma:
  id: build-info
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/build_info.py
      symbol: register_build_info
    - scanner: python
      file: src/meraki_dashboard_exporter/__version__.py
  technology: Python, prometheus_client
  group: Self-observability
description: Version, commit and the meraki_exporter_build_info metric
---

`__version__.py` resolves the package version and build commit; `build_info.py` registers the constant `meraki_exporter_build_info` gauge labelled with them, so a scrape can be pinned to an exact build.
