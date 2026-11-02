---
type: C4 Component
title: Clients
status: stable
groma:
  id: collectors-clients
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/collectors/clients.py
  technology: Python
  group: Collectors
description: Opt-in client metrics, client store and application usage
---

`ClientsCollector` is off unless client collection is enabled. It reads network clients, client application usage and, optionally, wireless signal quality, emits bounded ID-only numeric series with a `meraki_client_info` join (grandfathered under the cardinality rule), fills the client store, and resolves hostnames through the DNS resolver when enabled.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [src/meraki_dashboard_exporter/collectors/clients.py](../../../../../../src/meraki_dashboard_exporter/collectors/clients.py) | [src/meraki_dashboard_exporter/core/api_facade.py](../../../../../../src/meraki_dashboard_exporter/core/api_facade.py) | Calls Meraki API | facade_for().call |
| [src/meraki_dashboard_exporter/collectors/clients.py](../../../../../../src/meraki_dashboard_exporter/collectors/clients.py) | [src/meraki_dashboard_exporter/services/client_store.py](../../../../../../src/meraki_dashboard_exporter/services/client_store.py) | Stores clients | Python call |
| [src/meraki_dashboard_exporter/collectors/clients.py](../../../../../../src/meraki_dashboard_exporter/collectors/clients.py) | [src/meraki_dashboard_exporter/services/dns_resolver.py](../../../../../../src/meraki_dashboard_exporter/services/dns_resolver.py) | Resolves hostnames | Python call |
