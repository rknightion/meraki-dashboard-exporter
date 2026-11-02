---
type: C4 Component
title: Insight
status: stable
groma:
  id: collectors-insight
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/insight.py
  technology: Python
  group: Collectors
description: Opt-in Meraki Insight application health
---

`InsightCollector` is off by default. It reads Insight monitored applications and, behind a second setting, per-network application health, and treats an unlicensed organization as not available rather than a failure.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/insight.py](../../../../../../src/meraki_dashboard_exporter/collectors/insight.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
