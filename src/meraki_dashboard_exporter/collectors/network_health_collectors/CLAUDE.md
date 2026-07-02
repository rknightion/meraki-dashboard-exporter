<system_context>
Network health collectors for Meraki Dashboard Exporter - Handles network-level wireless performance and health metrics: RF channel utilization, connection statistics, data rates, Bluetooth client detection, and per-SSID failed connections.
</system_context>

<critical_notes>
- **Inherit from `BaseNetworkHealthCollector`** (in `base.py`) for the shared `parent`/`api`/`settings` wiring. The base class defines **no metrics itself** — every gauge is created once in the parent `NetworkHealthCollector._initialize_metrics()` (`../network_health.py`); sub-collectors only call `self._set_metric_value("_gauge_attr_name", labels, value)` (from `SubCollectorMixin`), which delegates to the parent's attribute of that name.
- **MEDIUM update tier**: `NetworkHealthCollector` is `@register_collector(UpdateTier.MEDIUM)` (300s interval).
- **Manual registration**: all 7 sub-collectors are instantiated in `NetworkHealthCollector.__init__` (`rf_health_collector`, `connection_stats_collector`, `data_rates_collector`, `bluetooth_collector`, `ssid_performance_collector`, `latency_stats_collector`, `air_marshal_collector`) and invoked per-network from `_collect_network_health_bundle`.
- **Wireless-only filtering happens once, upstream**: `NetworkHealthCollector._collect_org_network_health` filters the org's networks down to `ProductType.WIRELESS in network["productTypes"]` *before* dispatching to any sub-collector — individual `collect()` methods do not (and don't need to) re-check `product_types`.
- **Network list via inventory (mandatory)**: `NetworkHealthCollector._fetch_networks_for_health` calls `await self.inventory.get_networks(org_id)` — never call `getOrganizationNetworks` directly.
- **`RFHealthCollector` also reads devices via inventory**: it calls `self.parent.inventory.get_devices(org_id, network_id=network_id)` to resolve AP serial → name for labels, falling back to a direct `getOrganizationDevices` call only when `inventory` is unset.
- **Wrap fetcher responses** with `validate_response_format` from `core.error_handling` (all 7 sub-collectors do this on their SDK call).
</critical_notes>

<file_map>
## NETWORK HEALTH COLLECTOR FILES
- `base.py` - `BaseNetworkHealthCollector(SubCollectorMixin)`: holds `parent: NetworkHealthCollector`, `api`, `settings`; no `_initialize_metrics` of its own
- `bluetooth.py` - `BluetoothCollector`: Bluetooth clients detected by MR devices via `getNetworkBluetoothClients`
- `connection_stats.py` - `ConnectionStatsCollector`: network-wide wireless connection stats (assoc/auth/dhcp/dns/success) via `getNetworkWirelessConnectionStats`
- `data_rates.py` - `DataRatesCollector`: network-wide wireless up/download kbps via `getNetworkWirelessDataRateHistory`
- `rf_health.py` - `RFHealthCollector`: per-AP and network-average 2.4GHz/5GHz channel utilization via `getNetworkNetworkHealthChannelUtilization`
- `ssid_performance.py` - `SSIDPerformanceCollector`: per-SSID failed connection counts by failure step (assoc/auth/dhcp/dns) via `getNetworkWirelessFailedConnections`
- `latency_stats.py` - `LatencyStatsCollector`: per-AP-device latency stats via `getNetworkWirelessDevicesLatencyStats`, plus network-wide client latency stats via `getNetworkWirelessClientsLatencyStats`. Per-client rows are never labeled directly (bounded label sets only).
- `air_marshal.py` - `AirMarshalCollector`: Air Marshal rogue AP/SSID-spoofing detection counts (rogue SSID entries seen, total BSSIDs, contained BSSIDs, wired-detection entries) via `getNetworkWirelessAirMarshal`.
</file_map>

<paved_path>
## NETWORK HEALTH COLLECTOR PATTERN
Every sub-collector implements a single `collect(self, network: dict[str, Any]) -> None` entry
point called per-network from the coordinator's bundle — there is no `_initialize_metrics()` or
per-network-ID signature at the sub-collector level:
```python
from .base import BaseNetworkHealthCollector


class MyNetworkHealthCollector(BaseNetworkHealthCollector):
    @log_api_call("getNetworkSomeEndpoint")
    async def _fetch_something(self, network_id: str) -> list[dict[str, Any]]:
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkSomeEndpoint, network_id, timespan=3600
        )
        return validate_response_format(
            response, expected_type=list, operation="getNetworkSomeEndpoint"
        )

    async def collect(self, network: dict[str, Any]) -> None:
        network_id = network["id"]
        data = await self._fetch_something(network_id)
        labels = create_network_labels(
            network, org_id=network.get("orgId", ""), org_name=network.get("orgName", "")
        )
        self._set_metric_value("_my_gauge_attr", labels, value)  # gauge lives on the parent
```
The gauge (`self._my_gauge_attr` in this example) is defined once in
`NetworkHealthCollector._initialize_metrics()`, not in the sub-collector.

## ERROR HANDLING IS NOT UNIFORM ACROSS ALL 7
The original 5 (`bluetooth.py`, `connection_stats.py`, `data_rates.py`, `rf_health.py`,
`ssid_performance.py`) wrap `collect()` in `try/except Exception as e` and inspect `str(e)` for
`"400"`, `"404"`, `"Bad Request"`, or `"rate limit"` (case-insensitive) to distinguish "API not
available for this network" (logged at `debug`, collection continues) from a real failure
(`logger.exception`). Only `BluetoothCollector` additionally sets its gauge to `0` in the
not-available case; the others simply skip setting a value for that network. The two newer
sub-collectors, `latency_stats.py` and `air_marshal.py`, do **not** follow this string-inspection
pattern at all — their fetcher methods are wrapped in `@with_error_handling(continue_on_error=True,
...)` instead, delegating categorization to the shared decorator (see `core/error_handling.py`).
</paved_path>

<api_quirks>
- **Concrete timespans in use**: Bluetooth clients `timespan=300` (5 min, `perPage=1000`,
  `total_pages="all"`); connection stats `timespan=1800` (30 min — the API's practical minimum
  for reliable data); data rate history `timespan=300` with `resolution=300` (take the
  most-recent bucket, sorted by `endTs`); SSID failed connections `timespan=3600` (1 hour).
- **`resolution` is only used by `data_rates.py`** — channel utilization
  (`getNetworkNetworkHealthChannelUtilization`) takes no `resolution`/`timespan` argument, just
  `total_pages="all"`.
- **Metric enum source is not uniform**: `_network_connection_stats`
  (`NETWORK_WIRELESS_CONNECTION_STATS`) is defined via `NetworkMetricName`, while every other
  gauge in this coordinator (AP/network utilization, data rates, Bluetooth, SSID failures) uses
  `NetworkHealthMetricName` — check both enums when hunting for a network-health metric name.
</api_quirks>

<fatal_implications>
- **NEVER assume all networks support wireless metrics** - the coordinator already filters to
  `ProductType.WIRELESS` networks before calling any sub-collector; don't re-add a redundant
  per-collector check that could silently diverge from that filter.
- **NEVER aggregate metrics across different network types** without proper labeling
- **NEVER ignore timespan constraints** for network health endpoints (see `api_quirks` above)
- **NEVER call `getOrganizationNetworks` or `getOrganizationDevices` directly** - use
  `self.inventory.get_networks(org_id)` / `self.parent.inventory.get_devices(org_id, ...)` so
  `NetworkFilter` is enforced
</fatal_implications>
