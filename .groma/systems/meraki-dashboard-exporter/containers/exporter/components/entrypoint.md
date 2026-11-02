---
type: C4 Component
title: Entry point (__main__)
status: stable
groma:
  id: entrypoint
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/__main__.py
    - scanner: python
      file: src/meraki_dashboard_exporter/__init__.py
  technology: Python
  group: Process and HTTP surface
description: Command-line start, config check and uvicorn launch
---

`main()` builds `Settings` once, prints a readable error when the API key or another setting is invalid, and supports `--check` (validate and print a redacted summary, offline by default) and `--probe` (add a live auth probe). Otherwise it calls `create_app(settings=...)` and runs it under uvicorn on the configured host and port (default port 9099).

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/__main__.py](../../../../../../src/meraki_dashboard_exporter/__main__.py) | [src/meraki_dashboard_exporter/core/config.py](../../../../../../src/meraki_dashboard_exporter/core/config.py) | Loads settings | Python call |
| [src/meraki_dashboard_exporter/__main__.py](../../../../../../src/meraki_dashboard_exporter/__main__.py) | [src/meraki_dashboard_exporter/app.py](../../../../../../src/meraki_dashboard_exporter/app.py) | Starts app | uvicorn |
