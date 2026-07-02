# API Call Audit

**Date:** 2026-04-08 (initial); 2026-05-08 (refresh after inventory routing refactor)
**Purpose:** Map all Meraki API calls to identify reduction opportunities

## Summary

| Metric | Count |
|--------|-------|
| Total unique API endpoints called | 34 |
| Per-org calls | 20 |
| Per-network calls | 10 |
| Per-device calls | 2 |
| Calls via inventory cache (deduplicated) | 6 |
| Calls bypassing inventory (direct) | see "Remaining bypasses" below |
| Potential reductions identified | see Recommendations |

> Note: Most of the bypass cases originally flagged in this audit
> (`NetworkHealthCollector`, `MSCollector.collect_stp_priorities`,
> `MRWirelessCollector._build_ssid_to_network_mapping`, `RFHealthCollector`,
> and `OrganizationCollector` device-availability fallback) have since been
> routed through the shared `OrganizationInventory` service. The remaining
> known bypasses are documented in the "Remaining bypasses" section.

---

## Per-Org Calls (Efficient)

These calls fetch data for an entire organization in one request, which is the optimal pattern.

| Endpoint | Collector File | Notes |
|----------|---------------|-------|
| `getOrganizations` | `core/discovery.py`, `collectors/alerts.py`, `collectors/config.py`, `collectors/devices/mt.py`, `services/inventory.py` | Multiple collectors fetch this independently; inventory caches it |
| `getOrganization` | `core/api_helpers.py`, `collectors/alerts.py`, `collectors/config.py`, `collectors/devices/mt.py`, `services/inventory.py` | Single-org mode fallback (inventory resolves the real org name here) |
| `getOrganizationNetworks` | `core/api_helpers.py`, `collectors/device.py`, `collectors/network_health.py`, `collectors/devices/ms.py`, `collectors/devices/mr/wireless.py`, `collectors/alerts.py`, `services/inventory.py` | Heavily used; some bypass inventory cache |
| `getOrganizationDevices` | `core/api_helpers.py`, `collectors/devices/mt.py`, `collectors/network_health_collectors/rf_health.py`, `services/inventory.py` | Some bypass inventory cache |
| `getOrganizationDevicesAvailabilities` | `collectors/device.py`, `collectors/organization.py`, `services/inventory.py` | Partially cached via inventory |
| `getOrganizationDevicesOverviewByModel` | `collectors/organization.py:479` | Per-org, org-level summary |
| `getOrganizationDevicesSystemMemoryUsageHistoryByInterval` | `collectors/devices/base.py:107` | Per-org memory history |
| `getOrganizationDevicesPacketCaptureCaptures` | `collectors/organization.py:627` | Per-org |
| `getOrganizationSwitchPortsStatusesBySwitch` | `collectors/devices/ms.py:429` | Org-level; preferred over per-device |
| `getOrganizationSwitchPortsOverview` | `collectors/devices/ms.py:966` | Per-org overview |
| `getOrganizationWirelessDevicesEthernetStatuses` | `collectors/devices/mr/performance.py:455` | Per-org |
| `getOrganizationWirelessDevicesPacketLossByNetwork` | `collectors/devices/mr/performance.py:797` | Per-org, grouped by network |
| `getOrganizationWirelessDevicesSystemCpuLoadHistory` | `collectors/devices/mr/performance.py:904` | Per-org, batched by serials |
| `getOrganizationWirelessSsidsStatusesByDevice` | `collectors/devices/mr/wireless.py:198` | Per-org |
| `getOrganizationWirelessClientsOverviewByDevice` | `collectors/devices/mr/clients.py:208` | Per-org |
| `getOrganizationSummaryTopSsidsByUsage` | `collectors/devices/mr/wireless.py:365` | Per-org |
| `getOrganizationSummaryTopApplicationsCategoriesByUsage` | `collectors/organization.py:744` | Per-org |
| `getOrganizationApplianceUplinkStatuses` | `collectors/devices/mx.py:120` | Per-org |
| `getOrganizationApplianceVpnStatuses` | `collectors/devices/mx_vpn.py:129` | Per-org |
| `getOrganizationAssuranceAlerts` | `collectors/alerts.py:286` | Per-org |
| `getOrganizationApiRequestsOverview` | `collectors/organization_collectors/api_usage.py:40` | Per-org |
| `getOrganizationClientsOverview` | `collectors/organization_collectors/client_overview.py:46` | Per-org |
| `getOrganizationLicensesOverview` | `collectors/organization_collectors/license.py:50`, `services/inventory.py:784` | Partially cached via inventory |
| `getOrganizationLicenses` | `collectors/organization_collectors/license.py:71` | Per-org; only when `getOrganizationLicensesOverview` fails |
| `getOrganizationLoginSecurity` | `collectors/config.py:247`, `services/inventory.py:865` | Partially cached via inventory |
| `getOrganizationConfigurationChanges` | `collectors/config.py:346` | Per-org |

---

## Per-Network Calls (May Have Org-Wide Equivalents)

These calls iterate over all networks and make one API request per network. Some endpoints have no org-wide alternative; others could potentially be consolidated.

| Endpoint | Collector File | Org-Wide Equivalent | Notes |
|----------|---------------|-------------------|-------|
| `getNetworkClients` | `collectors/clients.py:428` | None | Network-scoped only; one call per network |
| `getNetworkClientsApplicationUsage` | `collectors/clients.py:901` | None | Network-scoped only; one call per network |
| `getNetworkWirelessSignalQualityHistory` | `collectors/clients.py:1037` | None | Per client within a network |
| `getNetworkWirelessConnectionStats` | `collectors/network_health_collectors/connection_stats.py:45` | None | Per-network wireless only |
| `getNetworkWirelessDataRateHistory` | `collectors/network_health_collectors/data_rates.py:39` | None | Per-network wireless only |
| `getNetworkWirelessFailedConnections` | `collectors/network_health_collectors/ssid_performance.py:45` | None | Per-network wireless only |
| `getNetworkWirelessDevicesConnectionStats` | `collectors/devices/mr/clients.py:140` | None | Per-network; one call covers all MR devices in network |
| `getNetworkWirelessSsids` | `collectors/devices/mr/wireless.py:315` | `getOrganizationWirelessSsidsStatusesByDevice` | Per-network; used to build SSID-to-network mapping |
| `getNetworkSwitchStp` | `collectors/devices/ms.py:775` | None | Per-network; STP is network-scoped |
| `getNetworkNetworkHealthChannelUtilization` | `collectors/network_health_collectors/rf_health.py:75` | None | Per-network wireless only |
| `getNetworkBluetoothClients` | `collectors/network_health_collectors/bluetooth.py:39` | None | Per-network |
| `getNetworkSwitchStacks` | `collectors/devices/ms_stack.py:106` | None | Per-network switch only |
| `getNetworkSensorAlertsOverviewByMetric` | `collectors/alerts.py:477` | None | Per-network sensor only |
| `getNetworkHealthAlerts` | `collectors/alerts.py:553` | None | Per-network |
| `getNetworkApplianceFirewallL3FirewallRules` | `collectors/devices/mx_firewall.py:120` | None | Per-network appliance |
| `getNetworkApplianceFirewallL7FirewallRules` | `collectors/devices/mx_firewall.py:147` | None | Per-network appliance |

---

## Per-Device Calls (Highest Reduction Potential)

These calls make one API request per device, which creates high API call volume at scale. All current per-device calls have org-level alternatives already being used or available.

| Endpoint | Collector File | Can Replace With | Estimated Savings |
|----------|---------------|-----------------|---------|
| `getDeviceSwitchPortsStatuses` | `collectors/devices/ms.py:508`, `collectors/devices/ms.py:646` | `getOrganizationSwitchPortsStatusesBySwitch` | ~N calls → 1 call (N = number of MS devices) |
| `getDeviceSwitchPortsStatusesPackets` | `collectors/devices/ms.py:852` | No org-level equivalent currently | Cannot reduce |

**Note:** `getDeviceSwitchPortsStatuses` already has a preferred org-level alternative (`getOrganizationSwitchPortsStatusesBySwitch`) implemented in `collect_port_statuses_by_switch()`. The per-device fallback at lines 508 and 646 is only used when the org-level endpoint is unavailable in the SDK. This is correct conditional behavior, not a reduction opportunity.

---

## Inventory Cache Coverage

The `OrganizationInventory` service (`services/inventory.py`) caches the following endpoints with TTL-based invalidation:

| Cached Endpoint | TTL | Collectors Using Cache |
|----------------|-----|----------------------|
| `getOrganizations` | 15 min (MEDIUM) | `alerts.py`, `config.py`, `device.py`, `organization.py`, `network_health.py` |
| `getOrganizationNetworks` | 15 min (MEDIUM) | `alerts.py`, `device.py` |
| `getOrganizationDevices` | 15 min (MEDIUM) | `device.py` |
| `getOrganizationDevicesAvailabilities` | 2 min (dynamic) | `device.py`, `organization.py` |
| `getOrganizationLicensesOverview` | 30 min (SLOW) | `organization_collectors/license.py` |
| `getOrganizationLoginSecurity` | 60 min (CONFIG) | `config.py` |

---

## Remaining bypasses

These endpoints are still called outside the shared `OrganizationInventory`
cache. The bypasses previously flagged for `NetworkHealthCollector`,
`MSCollector.collect_stp_priorities`, `MRWirelessCollector._build_ssid_to_network_mapping`,
and `RFHealthCollector` have been resolved (they now use
`self.(parent.)inventory.get_networks()` / `get_devices()` and the
configured network filter applies).

| Endpoint | Called By | Recommendation |
|----------|-----------|----------------|
| `getOrganizations` | `core/discovery.py` (startup, intentional), `collectors/devices/mt.py:_fetch_organizations()` | `MTCollector` could use the shared inventory if wired with one |
| `getOrganizationDevices` | `collectors/devices/mt.py:_fetch_sensor_devices()` | Use `inventory.get_devices(org_id)` and filter locally for `productTypes=[SENSOR]` |
| `getOrganizationDevicesAvailabilities` | `collectors/organization.py:_collect_device_availability_metrics()` (fallback path only when `self.inventory is None`) | Inventory is normally injected; the fallback path should be unreachable in production |
| `getOrganizationNetworks` | `collectors/alerts.py:_fetch_networks_direct()` (fallback only when inventory is unavailable) | Fallback applies the network filter; reachable only if inventory is missing |

### Detail: `MTCollector`

`collectors/devices/mt.py:_fetch_organizations()` and
`_fetch_sensor_devices()` call `getOrganizations` and `getOrganizationDevices`
directly. The `MTCollector` is a standalone (FAST-tier) collector and may
not currently have an inventory service injected. Wiring it through the
shared inventory would let it benefit from cache deduplication when running
alongside the other tiered collectors.

---

## Recommendations

The bulk of the original recommendations have been implemented as part of the
inventory routing refactor (`NetworkHealthCollector`, `MSCollector` STP,
`MRWirelessCollector` SSID mapping, `RFHealthCollector`, and the
`OrganizationCollector` availability path now all use the shared inventory).

### Outstanding: route `MTCollector` through the shared inventory (Low-Medium Impact)

**Files:** `collectors/devices/mt.py:_fetch_organizations()`,
`collectors/devices/mt.py:_fetch_sensor_devices()`

**Change:** Wire `MTCollector` with the shared `OrganizationInventory` and
replace the direct `getOrganizations` / `getOrganizationDevices` calls with
`inventory.get_organizations()` / `inventory.get_devices(org_id)` (filtering
locally for `productTypes=[SENSOR]`).

**Savings:** Removes 1 `getOrganizations` and 1 `getOrganizationDevices` call
per FAST-tier cycle when MT collection is enabled, and ensures the configured
`NetworkFilter` is applied consistently to sensor devices.

---

## API Call Volume Estimate Per Collection Cycle

Assuming: 1 org, 20 networks (10 wireless), 50 MS switches, 30 MR APs.

| Category | Calls (post-refactor) | Notes |
|----------|----------------------|-------|
| Per-org inventory (cached) | ~6 | Shared via `OrganizationInventory` |
| Per-org non-cached | ~20 | One-shot org-level endpoints |
| Per-network network health calls | 50 | No org-wide equivalent |
| Per-device fallback (MS ports) | 0* | Org-level path preferred |
| **Total direct API calls** | **~76** | |

\* Per-device fallback for MS port statuses is only triggered if the SDK lacks the org-level endpoint, which is expected to be rare.

The ~15% reduction projected by the original audit has largely been realised
via the inventory-routing refactor. Remaining opportunities (notably
`MTCollector`) are smaller in absolute call count but worth picking up for
consistency and to ensure the network filter applies uniformly.
