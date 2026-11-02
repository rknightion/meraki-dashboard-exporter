---
type: C4 Component
title: Metric expiration (core/metric_expiration.py)
status: stable
groma:
  id: metric-expiration
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/metric_expiration.py
  technology: Python, prometheus_client
  group: Collection runtime
description: Removes series for devices and networks that stop reporting
---

Tracks every series set through `_set_metric()` with a TTL derived from its endpoint group's solved interval, and a cleanup loop removes stale label sets so offline and removed devices do not linger. Also enforces the per-family series budget (`cardinality.max_series_per_family`): the default action warns and keeps emitting, and only the `drop` action sheds series.
