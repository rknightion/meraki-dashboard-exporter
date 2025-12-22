# Collector Reference

This page summarizes the collectors that ship with the exporter.

Collectors run on FAST/MEDIUM/SLOW tiers configured via `MERAKI_EXPORTER_UPDATE_INTERVALS__*`. See the Metrics Overview for tier definitions.

**Total collector classes:** 26
**Auto-registered collectors:** 7

## Main Collectors (auto-registered)

| Collector | Tier | Purpose | Metrics | Notes |
|-----------|------|---------|---------|-------|
| `AlertsCollector` | MEDIUM | Collector for Meraki assurance alerts. | 5 |  |
| `ClientsCollector` | MEDIUM | Collector for client-level metrics across all networks. | 21 | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `ConfigCollector` | SLOW | Collector for configuration and security settings. | 14 |  |
| `DeviceCollector` | MEDIUM | Collector for device-level metrics. | 6 |  |
| `MTSensorCollector` | FAST | Collector for fast-moving sensor metrics (MT devices). | 18 |  |
| `NetworkHealthCollector` | MEDIUM | Collector for medium-moving network health metrics. | 8 |  |
| `OrganizationCollector` | MEDIUM | Collector for organization-level metrics. | 19 |  |

## Coordinator Relationships

- **DeviceCollector** → MGCollector, MRCollector, MSCollector, MTCollector, MVCollector, MXCollector
- **MRCollector** → MRClientsCollector, MRPerformanceCollector, MRWirelessCollector
- **MTSensorCollector** → MTCollector
- **NetworkHealthCollector** → RFHealthCollector, ConnectionStatsCollector, DataRatesCollector, BluetoothCollector
- **OrganizationCollector** → APIUsageCollector, LicenseCollector, ClientOverviewCollector

## Sub-collector Catalog

### Device Sub-collectors

- `BaseDeviceCollector` — Base class for device-specific collectors.
- `MGCollector` — Collector for MG cellular gateway metrics.
- `MRClientsCollector` — Collector for MR wireless client connection metrics.
- `MRCollector` — Coordinator for Meraki MR (Wireless AP) device collectors.
- `MRPerformanceCollector` — Collector for MR wireless performance metrics.
- `MRWirelessCollector` — Collector for MR wireless radio and SSID metrics.
- `MSCollector` — Collector for Meraki MS (Switch) devices.
- `MTCollector` — Collector for Meraki MT (Sensor) devices.
- `MVCollector` — Collector for MV security camera metrics.
- `MXCollector` — Collector for MX security appliance metrics.

### Network Health Sub-collectors

- `BaseNetworkHealthCollector` — Base class for network health sub-collectors.
- `BluetoothCollector` — Collector for Bluetooth clients detected by MR devices in a network.
- `ConnectionStatsCollector` — Collector for network-wide wireless connection statistics.
- `DataRatesCollector` — Collector for network-wide wireless data rate metrics.
- `RFHealthCollector` — Collector for wireless RF health metrics including channel utilization.

### Organization Sub-collectors

- `APIUsageCollector` — Collector for organization API usage metrics.
- `BaseOrganizationCollector` — Base class for organization sub-collectors.
- `ClientOverviewCollector` — Collector for organization client overview metrics.
- `LicenseCollector` — Collector for organization license metrics.

## Notes

- Collector enablement is configured in the [Configuration](../config.md) reference.
- Full metric details live in the [Metrics Reference](../metrics/metrics.md).
