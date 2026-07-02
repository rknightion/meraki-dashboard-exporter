<system_context>
Device-specific collectors for Meraki Dashboard Exporter - Handles metrics collection for all Meraki device types (MR, MS, MX, MT, MG, MV). Each device type has unique capabilities and metrics.
</system_context>

<critical_notes>
- **Inherit from `BaseDeviceCollector`** (in `base.py`) for per-device-type collectors (subclasses implement `async collect(device)`); `DeviceCollector` (`collectors/device.py`) manually instantiates one of each in its `__init__` (`self.mg_collector`, `self.mr_collector`, `self.ms_collector`, `self.ms_stack_collector`, `self.mt_collector`, `self.mv_collector`, `self.mx_collector`, plus the MX org-wide sub-collectors `self.mx_ha_collector`, `self.mx_uplink_usage_collector`, `self.mx_uplink_health_collector`).
- **Two sub-collector shapes**: device-type collectors extend `BaseDeviceCollector` and expose `collect(device)`. Metric-domain sub-collectors that a device-type collector composes internally (`mx_firewall.py`, `mx_vpn.py`, `ms_stack.py`, and the three `mr/` submodules) do NOT extend `BaseDeviceCollector` — they take a `parent` in `__init__`, most extend `SubCollectorMixin` (`../subcollector_mixin.py`), and expose their own `collect`/`collect_for_network`/`collect_*` methods called directly by the owning coordinator (not via a uniform interface).
- **Product type filtering**: Use `product_types` parameter when fetching devices
- **Metric creation**: Use `self.parent._create_gauge()` (not direct `Gauge()` construction). **Metric setting**: prefer `self.parent._set_metric()` for automatic expiration tracking — used throughout `mr/*.py`, `mx_vpn.py`, and `mx_firewall.py`. `ms.py` and `ms_stack.py` instead call `.labels(...).set(...)` directly on the gauge, which does **not** get automatic expiration tracking.
- **Network lookups via inventory**: When a sub-collector needs the network list, use `await self.parent.inventory.get_networks(org_id)` (see `ms.py::collect_stp_priorities`). Direct `getOrganizationNetworks` calls bypass `NetworkFilter` and are forbidden.
- **Org-wide fetches must resolve `get_allowed_network_ids(org_id)` and skip rows outside it** — every collector hitting an org-wide endpoint (`base.py::collect_memory_metrics`, `mx.py`, `mx_vpn.py`, `mr/clients.py`, `mr/wireless.py`, `mr/performance.py`) does this explicitly since those SDK responses aren't pre-filtered by network.
- **Wrap fetcher responses** with `validate_response_format` from `core.error_handling`.
</critical_notes>

<file_map>
## DEVICE TYPES & FILES
- `base.py` - `BaseDeviceCollector` ABC with common device patterns; subclasses implement `async collect(device)`. Also owns `collect_memory_metrics()` - a device-type-agnostic memory collector shared across all device types via the org-level `getOrganizationDevicesSystemMemoryUsageHistoryByInterval` (5-minute window: total/used/free bytes + usage percent).
- `mr/` - MR (Wireless APs) - **nested coordinator pattern; the only device type split into its own subpackage** because it covers RF/radio, ethernet/power, packet loss, CPU, and SSID usage in one device type. See `mr/CLAUDE.md` for the sub-collector split.
- `ms.py` - `MSCollector` (MS Switches) - Port status/traffic/usage/client-count, per-port + switch-total PoE wattage, STP priority (`collect_stp_priorities`), packet counters + rates by type (total/broadcast/multicast/CRC-errors/fragments/collisions/topology-changes, 5-min window), org-wide port overview (active/inactive counts by media + link speed). No cable-diagnostics collection exists (older revisions of this doc claimed otherwise).
- `ms_stack.py` - `MSStackCollector` - Switch stack membership and per-member status/count metrics per network; PSU/fan/temperature hardware health is explicitly deferred (per its docstring) pending Meraki API investigation.
- `mx.py` - `MXCollector` (MX Security Appliances) - Coordinator owning `vpn_collector`/`firewall_collector`, and itself also collects per-appliance uplink status (`collect_uplink_statuses`, org-level `getOrganizationApplianceUplinkStatuses`; clears the gauge's prior label series each cycle so stale `status` label values don't stick around after a transition).
- `mx_firewall.py` - `MXFirewallCollector` - L3/L7 user-defined firewall rule counts (excludes the built-in default rule) and default L3 policy (allow/deny), per network. SLOW tier (900s).
- `mx_vpn.py` - `MXVpnCollector` - Site-to-site VPN peer status and performance (latency, jitter, loss) via org-level `getOrganizationApplianceVpnStatuses`; combines Meraki + third-party peers (third-party peers keyed by public IP, no `networkId`).
- `mx_ha.py` - `MXHACollector` - Per-network HA (warm spare) enablement/mode + per-device HA role, org-wide via `getOrganizationApplianceDevicesRedundancyByNetwork`. MEDIUM tier (300s). Instantiated by `DeviceCollector.__init__` as `mx_ha_collector`, not owned by `mx.py`.
- `mx_uplink_usage.py` - `MXUplinkUsageCollector` - Per-(device, uplink) rolling 5-minute sent/received byte totals, org-wide via `getOrganizationApplianceUplinksUsageByNetwork`. MEDIUM tier (300s). Instantiated by `DeviceCollector.__init__` as `mx_uplink_usage_collector`, not owned by `mx.py`.
- `mx_uplink_health.py` - `MXUplinkHealthCollector` - Latest per-(device, uplink) loss/latency sample, org-wide via `getOrganizationDevicesUplinksLossAndLatency`. MEDIUM tier (300s). Instantiated by `DeviceCollector.__init__` as `mx_uplink_health_collector`, not owned by `mx.py`.
- `mt.py` - `MTCollector` (MT Sensors) - FAST tier; can run as a `DeviceCollector` sub-collector (`MTCollector.as_subcollector`) or fully standalone (`MTCollector.as_standalone`, used by `collectors/mt_sensor.py`). Handles ~18 sensor metric types (temperature, humidity, door, water, CO2/TVOC/PM2.5, noise, battery, indoor air quality, voltage/current/power/power-factor/frequency, downstream power, remote lockout).
- `mg.py` - `MGCollector` (MG Cellular Gateways) - per-device `collect()` is a deliberate no-op (only the common `device_up`/`status_info`/uptime metrics apply there), but `collect_uplink_statuses()` (org-wide, via `getOrganizationCellularGatewayUplinkStatuses`, `NetworkFilter`-aware) is fully implemented and emits real per-uplink status/signal(RSRP/RSRQ)/roaming gauges. Not a stub.
- `mv.py` - `MVCollector` (MV Security Cameras) - fully implemented per-device `collect()` covering analytics zones, live-analytics counts, and video quality/retention settings (`getDeviceCameraAnalyticsZones`/`getDeviceCameraAnalyticsLive`/`getDeviceCameraQualityAndRetention`), MEDIUM tier. Not a stub.
</file_map>

<paved_path>
## DEVICE COLLECTOR PATTERN
```python
from ..devices.base import BaseDeviceCollector


class MyDeviceCollector(BaseDeviceCollector):
    def _initialize_metrics(self) -> None:
        self._my_metric = self.parent._create_gauge(
            MyMetricName.SOME_METRIC,
            "Description",
            labelnames=[LabelName.ORG_ID.value, LabelName.SERIAL.value],
        )

    async def collect(self, device: dict[str, Any]) -> None:
        # Called per-device by parent coordinator
        ...
```

## API INTERACTION
```python
# Always use asyncio.to_thread for Meraki SDK calls
channel_data = await asyncio.to_thread(
    self.api.wireless.getOrganizationWirelessDevicesChannelUtilization,
    org_id,
    total_pages="all",
    timespan=3600,
)
```
</paved_path>

<api_quirks>
## MERAKI API DEVICE-SPECIFIC LIMITATIONS
- **MR**: CPU metrics only via `getOrganizationWirelessDevicesSystemCpuLoadHistory` (5-min window, batched by `settings.api.batch_size` with a 0.5s delay between batches)
- **MS**: The org-level `getOrganizationSwitchPortsStatusesBySwitch` endpoint may be absent on older SDK versions - `MSCollector` probes for it once (`_org_port_status_supported`, cached) and falls back to per-device `getDeviceSwitchPortsStatuses` when unavailable. POE budget is not exposed by the API at all (would need a per-model lookup table) and is not currently populated.
- **MT**: May return both `temperature` and `rawTemperature` - only use `temperature` (`rawTemperature` is explicitly skipped)
- **MG**: Per-device `collect()` is a no-op by design; the real cellular metrics come from `mg.py::collect_uplink_statuses()`, an org-wide call (see file_map) - don't add a per-device cellular fetch expecting it to be missing.
- **MV**: `_collect_analytics_zones`/`_collect_analytics_live`/`_collect_quality_and_retention` are each independently wrapped in `@with_error_handling(continue_on_error=True, ...)`, so a camera lacking analytics/zones configuration fails one call without aborting the others for that device - no special-cased device-level fallback beyond the standard decorator behavior.
</api_quirks>

<fatal_implications>
- **NEVER mix device types** in single collector - use product_types filtering
- **NEVER assume all devices support all metrics** - handle missing data gracefully
- **NEVER skip error handling** for device-specific API calls
</fatal_implications>
