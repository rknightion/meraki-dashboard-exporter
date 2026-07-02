# Collector Reference

This page summarizes the collectors that ship with the exporter.

Collectors run on FAST/MEDIUM/SLOW tiers configured via `MERAKI_EXPORTER_UPDATE_INTERVALS__*`. See the Metrics Overview for tier definitions.

**Total collector classes:** 40
**Auto-registered collectors:** 8

## Main Collectors (auto-registered)

| Collector | Tier | Purpose | Metrics | Notes |
|-----------|------|---------|---------|-------|
| `AlertsCollector` | MEDIUM | Collector for Meraki assurance alerts. | 5 |  |
| `ClientsCollector` | MEDIUM | Collector for client-level metrics across all networks. | 23 | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `ConfigCollector` | SLOW | Collector for configuration and security settings. | 16 |  |
| `DeviceCollector` | MEDIUM | Collector for device-level metrics. | 6 |  |
| `MTSensorAlertsCollector` | MEDIUM | Collector for network-wide currently-alerting MT sensor counts. | 1 |  |
| `MTSensorCollector` | FAST | Collector for fast-moving sensor metrics (MT devices). | 23 |  |
| `NetworkHealthCollector` | MEDIUM | Collector for medium-moving network health metrics. | 9 |  |
| `OrganizationCollector` | MEDIUM | Collector for organization-level metrics. | 24 |  |

## Coordinator Relationships

- **DeviceCollector** → MGCollector, MRCollector, MSCollector, MSStackCollector, MVCollector, MXCollector, MXUplinkHealthCollector, MXUplinkUsageCollector, MXHACollector, MSPowerCollector
- **MRCollector** → MRClientsCollector, MRPerformanceCollector, MRWirelessCollector
- **MXCollector** → MXVpnCollector, MXFirewallCollector
- **NetworkHealthCollector** → RFHealthCollector, ConnectionStatsCollector, DataRatesCollector, BluetoothCollector, SSIDPerformanceCollector, LatencyStatsCollector, AirMarshalCollector
- **OrganizationCollector** → APIUsageCollector, LicenseCollector, ClientOverviewCollector, FirmwareCollector, DeviceAvailabilityHistoryCollector

## Sub-collector Catalog

### Device Sub-collectors

- `BaseDeviceCollector` — Base class for device-specific collectors.
- `MGCollector` — Collector for MG cellular gateway metrics.
- `MRClientsCollector` — Collector for MR wireless client connection metrics.
- `MRCollector` — Coordinator for Meraki MR (Wireless AP) device collectors.
- `MRPerformanceCollector` — Collector for MR wireless performance metrics.
- `MRWirelessCollector` — Collector for MR wireless radio and SSID metrics.
- `MSCollector` — Collector for Meraki MS (Switch) devices.
- `MSPowerCollector` — Collector for MS rackmount switch power-supply (PSU) module status.
- `MSStackCollector` — Collector for MS switch stack health metrics.
- `MTCollector` — Collector for Meraki MT (Sensor) devices.
- `MVCollector` — Collector for MV security camera metrics.
- `MXCollector` — Collector for MX security appliance metrics.
- `MXFirewallCollector` — Collector for MX firewall rules and security policy metrics.
- `MXHACollector` — Collector for MX high-availability (warm spare) redundancy metrics.
- `MXUplinkHealthCollector` — Collector for MX per-uplink WAN loss/latency health metrics.
- `MXUplinkUsageCollector` — Collector for MX per-uplink WAN usage (sent/received bytes) metrics.
- `MXVpnCollector` — Collector for MX VPN/WAN health metrics.

### Network Health Sub-collectors

- `AirMarshalCollector` — Collector for Air Marshal rogue AP / SSID-spoofing detection counts.
- `BaseNetworkHealthCollector` — Base class for network health sub-collectors.
- `BluetoothCollector` — Collector for Bluetooth clients detected by MR devices in a network.
- `ConnectionStatsCollector` — Collector for network-wide wireless connection statistics.
- `DataRatesCollector` — Collector for network-wide wireless data rate metrics.
- `LatencyStatsCollector` — Collector for MR wireless latency statistics.
- `RFHealthCollector` — Collector for wireless RF health metrics including channel utilization.
- `SSIDPerformanceCollector` — Collector for per-SSID wireless performance metrics.

### Organization Sub-collectors

- `APIUsageCollector` — Collector for organization API usage metrics.
- `BaseOrganizationCollector` — Base class for organization sub-collectors.
- `ClientOverviewCollector` — Collector for organization client overview metrics.
- `DeviceAvailabilityHistoryCollector` — Collector for organization device availability change history metrics.
- `FirmwareCollector` — Collector for organization firmware upgrade metrics.
- `LicenseCollector` — Collector for organization license metrics.

### Other Sub-collectors

- `WebhookMetricsCollector` — Converts webhook events into Prometheus metrics.

## Notes

- Collector enablement is configured in the [Configuration](../config.md) reference.
- Full metric details live in the [Metrics Reference](../metrics/metrics.md).

