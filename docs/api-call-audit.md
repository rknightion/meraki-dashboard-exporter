# API Call Audit

**Date:** 2026-04-08
**Purpose:** Map all Meraki API calls to identify reduction opportunities

## Summary

| Metric | Count |
|--------|-------|
| Total unique API endpoints called | 34 |
| Per-org calls | 20 |
| Per-network calls | 10 |
| Per-device calls | 2 |
| Calls via inventory cache (deduplicated) | 6 |
| Calls bypassing inventory (direct) | 10 |
| Potential reductions identified | 7 |

---

## Per-Org Calls (Efficient)

These calls fetch data for an entire organization in one request, which is the optimal pattern.

| Endpoint | Collector File | Notes |
|----------|---------------|-------|
| `getOrganizations` | `core/discovery.py`, `collectors/alerts.py`, `collectors/config.py`, `collectors/devices/mt.py`, `services/inventory.py` | Multiple collectors fetch this independently; inventory caches it |
| `getOrganization` | `core/api_helpers.py`, `collectors/alerts.py`, `collectors/config.py`, `collectors/devices/mt.py` | Single-org mode fallback |
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

## Overlapping Calls (Duplicate Fetches)

These endpoints are called by multiple collectors independently, creating redundant API traffic:

| Endpoint | Called By (direct/bypassing inventory) | Recommendation |
|----------|----------------------------------------|----------------|
| `getOrganizationNetworks` | `network_health.py:346`, `devices/ms.py:749`, `devices/mr/wireless.py:300` | Route through inventory cache |
| `getOrganizationDevices` | `devices/mt.py:218`, `network_health_collectors/rf_health.py:46` | Route through inventory cache |
| `getOrganizationDevicesAvailabilities` | `organization.py:558` (fallback when `self.inventory` is None) | Ensure inventory is always provided |
| `getOrganizations` | `core/discovery.py:46`, `devices/mt.py:175` | Route through inventory cache |

### Detail: `getOrganizationNetworks` bypass in `NetworkHealthCollector`

`collectors/network_health.py:_fetch_networks_for_health()` (line 345) calls `getOrganizationNetworks` directly via `asyncio.to_thread` rather than using `self.inventory.get_networks()`. The inventory service is available (`self.inventory.get_organizations()` is used on line 261), so this is an unnecessary bypass.

### Detail: `getOrganizationNetworks` bypass in `MSCollector.collect_stp_priorities()`

`collectors/devices/ms.py:collect_stp_priorities()` (line 749) calls `getOrganizationNetworks` directly. The `MSCollector` is a sub-collector of `DeviceCollector`, which has an inventory service. Networks could be passed in from the parent or fetched via inventory.

### Detail: `getOrganizationNetworks` bypass in `MRWirelessCollector._build_ssid_to_network_mapping()`

`collectors/devices/mr/wireless.py:_build_ssid_to_network_mapping()` (line 300) calls `getOrganizationNetworks` directly. This builds a mapping used for SSID usage metrics and could use cached network data.

### Detail: `getOrganizationDevices` in `RFHealthCollector`

`collectors/network_health_collectors/rf_health.py:_fetch_organization_devices()` (line 46) calls `getOrganizationDevices` with `networkIds=[network_id]` filter. This is called once per network during collection. While the filter means full device data could not simply be reused, the base device list from inventory filtered locally would eliminate these calls entirely (one inventory fetch vs. N network-filtered fetches).

### Detail: `getOrganizationDevices` in `MTCollector`

`collectors/devices/mt.py:_fetch_sensor_devices()` (line 218) calls `getOrganizationDevices` with `productTypes=[SENSOR]` filter directly, bypassing the inventory service which already caches unfiltered device lists.

---

## Recommendations

Ordered by estimated impact (highest first):

### 1. Route `NetworkHealthCollector` network fetches through inventory (High Impact)

**File:** `collectors/network_health.py:_fetch_networks_for_health()` (line 330-353)

**Change:** Replace the direct `asyncio.to_thread(self.api.organizations.getOrganizationNetworks, ...)` call with `await self.inventory.get_networks(org_id)`. The inventory is already available and used for organization fetches in the same file.

**Savings:** Eliminates 1 API call per organization per MEDIUM collection cycle (300s). With N orgs this saves N calls every 300 seconds, plus the inventory TTL means subsequent calls within 15 minutes are free.

### 2. Route `MSCollector.collect_stp_priorities()` through inventory (Medium Impact)

**File:** `collectors/devices/ms.py:collect_stp_priorities()` (line 748-752)

**Change:** Accept pre-fetched networks as a parameter (already partially supported via `device_lookup` pattern), or use `self.parent.inventory.get_networks(org_id)` if available.

**Savings:** Eliminates 1 API call per organization per MEDIUM cycle for STP collection.

### 3. Route `MRWirelessCollector._build_ssid_to_network_mapping()` through inventory (Medium Impact)

**File:** `collectors/devices/mr/wireless.py:_build_ssid_to_network_mapping()` (line 299-302)

**Change:** Accept networks as a parameter passed from `DeviceCollector` (which already fetches them), or use inventory if accessible via `self.parent`.

**Savings:** Eliminates 1 API call per organization when collecting SSID usage metrics.

### 4. Replace per-network `getOrganizationDevices` in `RFHealthCollector` with inventory + local filter (Medium Impact)

**File:** `collectors/network_health_collectors/rf_health.py:_fetch_organization_devices()` (line 45-57)

**Change:** Pass the already-cached device list from `NetworkHealthCollector` into each `RFHealthCollector.collect()` call, filtered locally by `network_id`. This avoids one `getOrganizationDevices` API call per wireless network per MEDIUM cycle.

**Savings:** With W wireless networks per org, saves W API calls per collection cycle.

### 5. Route `MTCollector` device fetches through inventory (Low-Medium Impact)

**File:** `collectors/devices/mt.py:_fetch_sensor_devices()` (line 217-222)

**Change:** If `DeviceCollector` passes its inventory to sub-collectors, `MTCollector` could use `inventory.get_devices(org_id)` and filter locally for `productTypes=[SENSOR]` rather than fetching from API with a filter.

**Savings:** Eliminates 1 API call per organization per collection cycle for sensor devices; local filter is negligible cost.

### 6. Avoid duplicate `getOrganizationDevicesAvailabilities` in `OrganizationCollector` (Low Impact)

**File:** `collectors/organization.py:_collect_device_availability_metrics()` (line 557-561)

**Change:** The fallback `asyncio.to_thread(self.api.organizations.getOrganizationDevicesAvailabilities, ...)` at line 558 is only hit when `self.inventory` is None. Ensure `OrganizationCollector` always receives an inventory service (same pattern as `DeviceCollector`).

**Savings:** Prevents a rare but unnecessary direct API call.

### 7. Cache `getOrganizationDevices` for `MTCollector._fetch_organizations()` (Low Impact)

**File:** `collectors/devices/mt.py:_fetch_organizations()` (line 175)

**Change:** Use the inventory cache's `get_organizations()` instead of calling `getOrganizations` directly. The `MTCollector` is a standalone collector and may not currently have access to the shared inventory service; adding that dependency would allow it to benefit from the shared cache.

**Savings:** Avoids redundant `getOrganizations` calls if multiple collectors run in the same cycle.

---

## API Call Volume Estimate Per Collection Cycle

Assuming: 1 org, 20 networks (10 wireless), 50 MS switches, 30 MR APs.

| Category | Calls (current) | Calls (after recommendations) | Reduction |
|----------|----------------|-------------------------------|-----------|
| Per-org inventory (cached after first fetch) | ~6 | ~6 | 0% |
| Per-org non-cached | ~20 | ~20 | 0% |
| Per-network (network health: getOrgNetworks bypass) | +1 | 0 | -1 |
| Per-network (MS STP: getOrgNetworks bypass) | +1 | 0 | -1 |
| Per-network (MR SSID: getOrgNetworks bypass) | +1 | 0 | -1 |
| Per-network RF health device fetch | +10 | 0 | -10 |
| Per-network network health calls | 50 | 50 | 0% |
| Per-device fallback (MS ports) | 0* | 0* | 0% |
| **Total direct API calls** | **~89** | **~76** | **~15%** |

\* Per-device fallback for MS port statuses is only triggered if the SDK lacks the org-level endpoint, which is expected to be rare.

**Estimated total API call reduction: 13-16 calls per collection cycle (~15%)**

This is more conservative than the 30-50% target stated in the task description, because the exporter already does an excellent job of using org-level endpoints. The remaining reductions are mostly about routing existing fetches through the inventory cache rather than bypassing it.
