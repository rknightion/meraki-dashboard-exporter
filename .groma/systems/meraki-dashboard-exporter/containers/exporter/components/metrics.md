---
type: C4 Component
title: Metric and label factories
status: stable
groma:
  id: metrics
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/metrics.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/label_helpers.py
  technology: Python, prometheus_client
  group: Collection runtime
description: LabelName, create_labels() and the label helpers
---

`LabelName` is the enum of allowed label names; `create_labels()` validates keys and turns a `None` value into an empty string rather than dropping the key. The label helpers build org, network, device and client label sets with stable IDs only; mutable display names live on separate `*_info` join series.
