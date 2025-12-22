# Collectors Overview

This page summarizes how collectors run and how they are organized after the refactor.

## Execution Model
- **Update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) by default (configurable).
- **Parallelism**: `CollectorManager` runs each tier with `ManagedTaskGroup`, bounded by `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` and `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`.
- **Shared inventory**: `OrganizationInventory` caches organizations, networks, and devices per tier to reduce duplicate API calls.
- **Metric lifecycle**: `MetricExpirationManager` tracks metrics set via `_set_metric()` and expires stale series automatically.
- **Health & cardinality**: Collector duration/errors, failure streaks, and cardinality reports are exported for visibility.

## Main Collectors (auto-registered)

| Collector | Tier | Purpose | Notes |
|-----------|------|---------|-------|
| `AlertsCollector` | MEDIUM | Assurance alerts plus network health alerts | Always on |
| `ClientsCollector` | MEDIUM | Client status/usage and DNS cache stats | Requires `MERAKI_EXPORTER_CLIENTS__ENABLED=true` |
| `ConfigCollector` | SLOW | Organization security and configuration settings | |
| `DeviceCollector` | MEDIUM | Device availability + delegates to device-type collectors | Uses inventory + batch processing |
| `MTSensorCollector` | FAST | MT sensor readings (environmental/door/water) | |
| `NetworkHealthCollector` | MEDIUM | Wireless health and RF/channel quality | Uses sub-collectors |
| `OrganizationCollector` | MEDIUM | Org-level usage, licensing, API counters, and summaries | |

## Sub-Collectors

**Device collector sub-collectors**
- `MSCollector` – Switch ports, PoE, port errors/rates, STP priority
- `MRCollector` – Wireless coordinator (clients, performance, SSID usage)
  - `MRClientsCollector`, `MRPerformanceCollector`, `MRWirelessCollector`
- `MXCollector` – Appliance status and uplink information
- `MVCollector` – Camera health
- `MGCollector` – Cellular gateway connectivity
- `MTCollector` – Sensor metrics used by the device coordinator

**Network health sub-collectors**
- `BluetoothCollector` – Bluetooth client sightings
- `ConnectionStatsCollector` – Wireless connection statistics
- `DataRatesCollector` – Network-wide data rates
- `RFHealthCollector` – Channel utilization and RF health

**Organization sub-collectors**
- `APIUsageCollector` – API request usage and rate limits
- `LicenseCollector` – License counts and expiry windows
- `ClientOverviewCollector` – Organization-wide client counts/usage

## Tips for Working with Collectors
- Prefer cached inventory lookups (`self.inventory.get_organizations/networks/devices`) before hitting the API directly.
- Use `ManagedTaskGroup` for bounded parallelism rather than raw `asyncio.gather`.
- Always use MetricName/LabelName enums when defining metrics.
- Use `_set_metric()` (or `_set_metric_value()` in sub-collectors) to ensure metric expiration tracking.
- Validate API responses with `validate_response_format` or Pydantic models, and wrap calls with `with_error_handling`.

For the complete generated reference, see [Collector Reference](reference.md).
