---
type: C4 Component
title: Configuration and security
status: stable
groma:
  id: collectors-config
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/config.py
  technology: Python
  group: Collectors
description: Slow-changing organization configuration and security settings
---

`ConfigCollector` reads organization login security, SAML settings and identity providers, admins and configuration changes in one priority-4 endpoint group with a 900-second floor.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/config.py](../../../../../../src/meraki_dashboard_exporter/collectors/config.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
