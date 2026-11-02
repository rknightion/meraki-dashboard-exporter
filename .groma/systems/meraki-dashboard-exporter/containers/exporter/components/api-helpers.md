---
type: C4 Component
title: API helpers (core/api_helpers.py)
status: stable
groma:
  id: api-helpers
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/api_helpers.py
  technology: Python
  group: Meraki API access
description: Shared fetch patterns for organizations, networks and devices
---

Higher-level helpers collectors share for common fetches. Holds two of the sanctioned direct-fetch fallbacks used when the inventory service is unavailable, each of which reapplies the network filter itself.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/api_helpers.py](../../../../../../src/meraki_dashboard_exporter/core/api_helpers.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Fetches directly | facade_for().call |
