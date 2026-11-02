---
type: C4 Component
title: DNS resolver (services/dns_resolver.py)
status: stable
groma:
  id: dns-resolver
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/services/dns_resolver.py
  technology: Python
  group: Shared services
description: Optional reverse DNS lookups for client hostnames
---

When reverse lookup is enabled, resolves client IPs to hostnames through the host's resolver, with a bounded queue and worker pool sized by `dns_max_concurrent_lookups`, and sequences batches so a slow older batch cannot overwrite a newer one.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/services/dns_resolver.py](../../../../../../src/meraki_dashboard_exporter/services/dns_resolver.py) | [dns](../../../../../externals/dns.md) | Looks up hostnames | reverse DNS |
