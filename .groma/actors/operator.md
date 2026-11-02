---
type: C4 Actor
title: Operator
status: stable
groma:
  id: operator
---

Deploys and configures the exporter (`MERAKI_EXPORTER_` environment variables, including the Meraki API key), reads the status, clients and cardinality pages, and uses the token-protected control API.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [operator](operator.md) | [src/meraki_dashboard_exporter/__main__.py](../../src/meraki_dashboard_exporter/__main__.py) | Runs and configures | CLI, environment variables |
| [operator](operator.md) | [src/meraki_dashboard_exporter/app.py](../../src/meraki_dashboard_exporter/app.py) | Views status and controls | HTTP, bearer token |
