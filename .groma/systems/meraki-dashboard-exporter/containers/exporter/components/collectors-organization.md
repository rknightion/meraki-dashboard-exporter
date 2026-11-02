---
type: C4 Component
title: Organization
status: stable
groma:
  id: collectors-organization
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/__init__.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/base.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/api_usage.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/client_overview.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/device_availability_history.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/early_access.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/firmware.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/license.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/top_usage.py
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/organization_collectors/webhooks.py
  technology: Python
  group: Collectors
description: Organization-level inventory, licensing, usage and firmware metrics
---

`OrganizationCollector` collects network and device totals, device counts by model, availability, packet captures and application usage itself, and delegates to sub-collectors under `organization_collectors/`: API usage, client overview, device availability history, early access, firmware, licensing, top usage and webhook delivery logs. The availability-history window follows its endpoint group's solved interval.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/organization.py](../../../../../../src/meraki_dashboard_exporter/collectors/organization.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
| [src/meraki_dashboard_exporter/collectors/organization_collectors/webhooks.py](../../../../../../src/meraki_dashboard_exporter/collectors/organization_collectors/webhooks.py) | [src/meraki_dashboard_exporter/core/otel_data_logs.py](../../../../../../src/meraki_dashboard_exporter/core/otel_data_logs.py) | Emits delivery logs | DataLogEmitter |
