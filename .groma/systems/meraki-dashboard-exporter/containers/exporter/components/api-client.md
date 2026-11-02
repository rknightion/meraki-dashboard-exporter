---
type: C4 Component
title: Meraki API client (api/)
status: stable
groma:
  id: api-client
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/api/client.py
    - scanner: python
      file: src/meraki_dashboard_exporter/api/__init__.py
  technology: Python, Meraki Python SDK
  group: Meraki API access
description: Builds the Meraki SDK client and its executor
---

`AsyncMerakiClient` wraps the synchronous Meraki Python SDK. It reads the API key secret exactly once, builds the SDK with `wait_on_rate_limit=False` so 429 handling stays with the facade, and owns the thread-pool executor that `app.py` installs as the loop's default executor. Collectors receive its raw `.api` handle and pass bound SDK methods to the facade.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/api/client.py](../../../../../../src/meraki_dashboard_exporter/api/client.py) | [meraki-dashboard-api](../../../../../externals/meraki-dashboard-api.md) | Reads organization data | HTTPS REST, Meraki SDK |
