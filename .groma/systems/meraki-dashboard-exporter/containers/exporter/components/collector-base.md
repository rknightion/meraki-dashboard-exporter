---
type: C4 Component
title: Collector base (core/collector.py)
status: stable
groma:
  id: collector-base
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/collector.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/subcollector_mixin.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/__init__.py
  technology: Python
  group: Collection runtime
description: 'MetricCollector: the contract every collector implements'
---

Collectors implement `_initialize_metrics()` and `_collect_impl()`; `collect()` wraps them with tracing and duration, error and success metrics and must not be overridden. The base class creates gauges, counters and histograms from the metric-name enums, sets values through `_set_metric()` so the expiration manager tracks them, and gates each endpoint group through the scheduler. `SubCollectorMixin` gives sub-collectors the same delegation to their parent.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/collector.py](../../../../../../src/meraki_dashboard_exporter/core/collector.py) | [src/meraki_dashboard_exporter/core/scheduler.py](../../../../../../src/meraki_dashboard_exporter/core/scheduler.py) | Gates endpoint groups | Python call |
| [src/meraki_dashboard_exporter/core/collector.py](../../../../../../src/meraki_dashboard_exporter/core/collector.py) | [src/meraki_dashboard_exporter/core/metric_expiration.py](../../../../../../src/meraki_dashboard_exporter/core/metric_expiration.py) | Tracks series | Python call |
