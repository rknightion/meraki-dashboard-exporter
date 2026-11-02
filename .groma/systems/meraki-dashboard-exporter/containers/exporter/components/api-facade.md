---
type: C4 Component
title: API facade (core/api_facade.py)
status: stable
groma:
  id: api-facade
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/api_facade.py
  technology: Python
  group: Meraki API access
description: The only path from async code into the synchronous SDK
---

`facade_for(owner).call(operation, fn, ...)` acquires the per-org rate limiter, runs the SDK call on the default executor, bounds the whole logical fetch (all pages included) by a per-fetch deadline, meters attempts, and owns 429 retries: it honours a capped `Retry-After`, otherwise uses jittered exponential backoff. Calling `asyncio.to_thread()` or `run_in_executor()` on an SDK method elsewhere is forbidden.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | [src/meraki_dashboard_exporter/core/rate_limiter.py](../../../../../../src/meraki_dashboard_exporter/core/rate_limiter.py) | Acquires tokens | Python call |
| [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | [src/meraki_dashboard_exporter/api/client.py](../../../../../../src/meraki_dashboard_exporter/api/client.py) | Runs SDK calls | bound SDK methods on the client executor |
