# Collector Reference

This page summarizes the collectors that ship with the exporter.

Each collector owns one or more scheduler endpoint groups and runs its own group-clocked loop; the adaptive scheduler solves a per-group interval (floored at that group's volatility floor) from the configured request budget, so cadence is derived rather than assigned from a fixed tier. See the [Scheduler Architecture](../observability/scheduler.md) page for details.

**Total collector classes:** 25
**Auto-registered collectors:** 3

## Main Collectors (auto-registered)

| Collector | Purpose | Metrics | Notes |
|-----------|---------|---------|-------|
| `DeviceCollector` | Collector for device-level metrics. | 6 |  |
| `MTSensorAlertsCollector` | Collector for network-wide currently-alerting MT sensor counts. | 3 |  |
| `MTSensorCollector` | Collector for fast-moving sensor metrics (MT devices). | 24 |  |

## Coordinator Relationships

- **DeviceCollector** → MGCollector, MRCollector, MSCollector, MSStackCollector, MVCollector, MXCollector, MXUplinkHealthCollector, MXUplinkUsageCollector, MXHACollector, MSPowerCollector
- **MRCollector** → MRClientsCollector, MRPerformanceCollector, MRWirelessCollector, MRFirewallCollector, MRRfProfilesCollector, MRSignalQualityCollector, MRCatalystCollector, MRClientLogsCollector
- **MXCollector** → MXVpnCollector, MXFirewallCollector

## Sub-collector Catalog

### Device Sub-collectors

- `BaseDeviceCollector` — Base class for device-specific collectors.
- `MGCollector` — Collector for MG cellular gateway metrics.
- `MRCatalystCollector` — Collector for Catalyst (CW*) AP wireless-controller association info.
- `MRClientLogsCollector` — Emits per-client wireless data-log records (packet loss + signal quality).
- `MRClientsCollector` — Collector for MR wireless client connection metrics.
- `MRCollector` — Coordinator for Meraki MR (Wireless AP) device collectors.
- `MRFirewallCollector` — Collector for per-SSID L3/L7 firewall rule counts and LAN-access policy.
- `MRPerformanceCollector` — Collector for MR wireless performance metrics.
- `MRRfProfilesCollector` — Collector for per-AP RF profile assignment (config-drift) metrics.
- `MRSignalQualityCollector` — Collector for per-AP wireless signal quality (RSSI/SNR).
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

## Notes

- Collector enablement is configured in the [Configuration](../config.md) reference.
- Full metric details live in the [Metrics Reference](../metrics/metrics.md).

