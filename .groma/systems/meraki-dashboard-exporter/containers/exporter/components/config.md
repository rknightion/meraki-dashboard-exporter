---
type: C4 Component
title: Configuration (core/config*.py)
status: stable
groma:
  id: config
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/config.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/config_models.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/config_sources.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/config_logger.py
  technology: Python, pydantic-settings
  group: Process and HTTP surface
description: Settings loaded from MERAKI_EXPORTER_ environment variables
---

`Settings` is a pydantic-settings model with nested groups (`meraki`, `api`, `scheduler`, `collectors`, `clients`, `server`, `webhooks`, `otel`, `network_filter`, `cardinality`, `logging` and more) read from `MERAKI_EXPORTER_` environment variables, with `__` for nesting and a `.env` file. A custom source supports the `<VAR>_FILE` convention for mounted secrets. The API key is a `SecretStr` and is never logged, and the API base URL must be a known regional Meraki origin unless a custom origin is explicitly allowed. `config_logger.py` writes the startup summary.
