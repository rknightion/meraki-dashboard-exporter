<system_context>
MR (Wireless AP) device collector - the only device type broken into its own subpackage instead of a
single module. `collector.py` is a thin coordinator; `clients.py`, `performance.py`, and `wireless.py`
each own one metric domain.
</system_context>

<critical_notes>
- **Why split**: MR covers more independent metric domains than any other single device type - client
  connection/auth stats, ethernet/power/PoE/link-aggregation status, device- and network-level packet
  loss, CPU load, radio config, and SSID usage. One file per domain keeps each collector reviewable.
- **`MRCollector.__init__` passes its OWN `parent` (the top-level `DeviceCollector`) straight through to
  each sub-collector** - `self.clients = MRClientsCollector(parent)`, not `MRClientsCollector(self)`. So
  `MRClientsCollector`/`MRPerformanceCollector`/`MRWirelessCollector` call `self.parent._create_gauge()`
  / `self.parent._set_metric()` directly against `DeviceCollector`, with `MRCollector` itself never in
  the call chain. This is the opposite of `mx.py`, where `MXCollector` passes `self` to `MXVpnCollector`/
  `MXFirewallCollector` and those sub-collectors delegate through `MXCollector`'s own
  `_create_gauge`/`_set_metric` (which forward to `DeviceCollector`). Don't assume the two patterns match
  when editing either.
- **None of the three submodules extend `BaseDeviceCollector` or `SubCollectorMixin`** - they're plain
  classes with `parent`/`api`/`settings` attributes and hand-rolled `_initialize_metrics()`. Only
  `MRCollector` itself (the coordinator) extends `BaseDeviceCollector`.
- **`MRCollector` re-exposes every sub-collector gauge as its own attribute** in `__init__` (e.g.
  `self._ap_clients = self.clients._ap_clients`) purely for backward compatibility with call sites that
  still reach for `mr_collector._some_metric` directly. When adding a new gauge to a submodule, add the
  matching re-export line in `collector.py` if anything outside the submodule needs to reach it.
- **Per-device vs org/network-level split**: `MRCollector.collect(device)` (called once per device by
  `DeviceCollector`) only delegates to `clients.collect()`, which is a no-op today - client counts and
  connection stats are collected in bulk instead. Ethernet, packet loss, CPU, SSID status, and SSID usage
  are all collected org- or network-wide via separate `collect_*` methods that `DeviceCollector` calls
  directly on `MRCollector`, not through the per-device path.
- **`MRPerformanceCollector` retains stale packet-count values**: `_set_packet_metric_value` caches the
  last non-zero value for any metric whose name contains `total` (but not `percent`) and reuses it when
  the API returns `None`/`0` for that same label set - avoids total-packet-count gauges dropping to zero
  on a transient empty response. Percent/loss metrics are never cached this way.
</critical_notes>

<file_map>
- `clients.py` - `MRClientsCollector`: `_ap_clients` (org-wide `getOrganizationWirelessClientsOverviewByDevice`) and `_ap_connection_stats` (per-network `getNetworkWirelessDevicesConnectionStats`, assoc/auth/dhcp/dns/success over the last 30 min).
- `performance.py` - `MRPerformanceCollector`: power/PoE/link-aggregation status (`getOrganizationWirelessDevicesEthernetStatuses`), device- and network-level packet loss (`getOrganizationWirelessDevicesPacketLossByNetwork`, 5-min window), CPU load (`getOrganizationWirelessDevicesSystemCpuLoadHistory`, batched via `settings.api.batch_size` with a 0.5s inter-batch delay).
- `wireless.py` - `MRWirelessCollector`: radio broadcast/channel/width/power (`getOrganizationWirelessSsidsStatusesByDevice`) and SSID usage/client-count (`getOrganizationSummaryTopSsidsByUsage`, `quantity=50`). The usage endpoint returns one org-wide row per SSID name, so those five gauges are labelled at org+SSID level only (no network labels) — there is deliberately no SSID→network mapping / per-network fan-out.
- `collector.py` - `MRCollector`: composes the three collectors above and forwards `DeviceCollector`'s per-device and org/network-level `collect_*` calls to the right one.
</file_map>
