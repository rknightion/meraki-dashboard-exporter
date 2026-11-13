---
type: C4 Component
title: Response and domain models
status: stable
groma:
  id: models
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/domain_models.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/api_models.py
  technology: Python, Pydantic
  group: Meraki API access
description: Pydantic models for API responses and internal structures
---

Typed Pydantic models for Meraki API responses (`api_models.py`) and device-family and metric domain models (`domain_models.py`). Every API response gets a model.
