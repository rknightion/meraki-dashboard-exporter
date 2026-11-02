---
type: C4 Component
title: Cardinality monitor (core/cardinality.py)
status: stable
groma:
  id: cardinality
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/cardinality.py
  technology: Python, prometheus_client
  group: Self-observability
description: Tracks series counts per metric family and serves the /cardinality pages
---

Periodically measures how many series each metric family and label holds and reports the result. Registers the top-level `/cardinality` HTML pages and the `/api/metrics/cardinality` JSON endpoint.
