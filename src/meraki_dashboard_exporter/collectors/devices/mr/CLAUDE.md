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
- **NEVER wire `liveTools`/beta MR endpoints (e.g. `createDeviceLiveToolsPing`,
  `createDeviceLiveToolsCableTest`, `createDeviceLiveToolsThroughputTest`, and similar
  `createDeviceLiveTools*`/beta wireless surfaces) into any collector on this passive scrape path**
  (`clients.py`, `performance.py`, `wireless.py`, `collector.py`). These are on-demand *action* APIs -
  each call triggers a device-side test/action (ping, cable test, throughput test, etc.), not a read of
  existing telemetry - and some sit on unstable beta surfaces. Wiring one into a scheduled collector
  would fire that action on every scheduler-gated group tick, which is both a functional bug
  (repeatedly disrupting the device with test traffic) and a rate-limit/API-abuse risk. If a future
  issue proposes exposing `liveTools` data, it must be an explicit, rate-limited, opt-in mechanism -
  never folded into the regular per-device/org/network `collect_*` sweep. (#284; a dedicated top-level
  beta-API section for this note is tracked for #278 Phase 4 - add a pointer there from the top-level
  `CLAUDE.md` once that section exists.)
</critical_notes>

<file_map>
- `clients.py` - `MRClientsCollector`: `_ap_clients` (org-wide `getOrganizationWirelessClientsOverviewByDevice`) and `_ap_connection_stats` (per-network `getNetworkWirelessDevicesConnectionStats`, assoc/auth/dhcp/dns/success over the last 30 min).
- `performance.py` - `MRPerformanceCollector`: power/PoE/link-aggregation status (`getOrganizationWirelessDevicesEthernetStatuses`), device- and network-level packet loss (`getOrganizationWirelessDevicesPacketLossByNetwork`, 5-min window), CPU load (`getOrganizationWirelessDevicesSystemCpuLoadHistory`, batched via `settings.api.batch_size` with a 0.5s inter-batch delay).
- `wireless.py` - `MRWirelessCollector`: radio broadcast/channel/width/power (`getOrganizationWirelessSsidsStatusesByDevice`) and SSID usage/client-count (`getOrganizationSummaryTopSsidsByUsage`, `quantity=50`). The usage endpoint returns one org-wide row per SSID name, so those five gauges are labelled at org+SSID level only (no network labels) — there is deliberately no SSID→network mapping / per-network fan-out.
- `signal_quality.py` - `MRSignalQualityCollector` (#324): per-AP RSSI/SNR via `getNetworkWirelessSignalQualityHistory` (per-AP fan-out, `timespan=7200/resolution=3600`, newest non-null bucket). AP selection is client-side by device `tags` (`ap_signal_quality_tags`) with an opt-out flag (`collect_ap_signal_quality`); `ManagedTaskGroup`-bounded; gated on `MR_SIGNAL_QUALITY`. Folded into `MRCollector.collect_cpu_load` (the org-wide pass that already carries the full `devices` list).
- `catalyst.py` - `MRCatalystCollector` (#326): Catalyst CW* AP → wireless-controller association info + join timestamp via org-wide `getOrganizationWirelessDevicesWirelessControllersByDevice`. Emits an info/join series + unix join-timestamp; `tags`/`details` arrays deliberately not emitted. Gated on `MR_WIRELESS_CONTROLLER` (auto-disabled when `catalyst_ap_count == 0`). Folded into `MRCollector.collect_ssid_status`.
- `client_logs.py` - `MRClientLogsCollector` (#323/#622, Phase 4C-2): per-**client** wireless DATA-LOG producers. Emits OTLP **log records** via `self.parent.data_log_emitter` (`core/otel_data_logs.py`) and owns **ZERO Prometheus metrics** (per-client detail is unbounded → must never be a labelled series). Two events, both gated on `emitter.is_event_enabled(...)` so a disabled event does **no** API call: `WIRELESS_CLIENT_PACKET_LOSS` (#323, primary — one org-wide bulk `getOrganizationWirelessDevicesPacketLossByClient` call, one record/client row) and `WIRELESS_CLIENT_SIGNAL_QUALITY` (#622, **experimental/off** — per-client `getNetworkWirelessSignalQualityHistory(clientId=...)` fan-out, one call **per active client**, `ManagedTaskGroup`-bounded; client universe enumerated **independently of packet loss** (#637) via `getNetworkClients` per allowed wireless network — filtered to `recentDeviceConnection == "Wireless"` — so a healthy zero-loss client, absent from the packet-loss response, still emits a signal-quality record). PII (`client.mac`) only when `emitter.include_identifiers`. The byClient response carries no AP serial, so `device.serial` is deliberately not emitted. Folded into `MRCollector.collect_ssid_usage` (no `device.py` edit). NOT gated by any `EndpointGroup` itself — its own `collect_client_logs()` has no `_should_run_group` check, so it runs on every `DeviceCollector` cycle (i.e. at `DeviceCollector`'s own solved cadence) rather than only when the `mr_ssid_usage` group (900s floor) is due, when enabled — see Phase-6 note in the tracker.
- `collector.py` - `MRCollector`: composes the sub-collectors above and forwards `DeviceCollector`'s per-device and org/network-level `collect_*` calls to the right one. Power mode (#325) lives in `performance.py::collect_power_mode` and is folded into `collect_ethernet_status`.
</file_map>
