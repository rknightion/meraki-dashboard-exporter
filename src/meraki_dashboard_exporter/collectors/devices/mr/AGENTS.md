# MR (wireless AP) collectors

`collector.py` holds `MRCollector`, a thin coordinator; every other module owns one metric domain.
This is the only device type split into a subpackage, because MR spans client connection and auth
stats, ethernet/power/PoE/link-aggregation, packet loss, CPU load, radio config and SSID usage.

## The parent chain is not what it looks like

`MRCollector.__init__` passes its OWN `parent` (the top-level `DeviceCollector`) straight through to
each submodule - `MRClientsCollector(parent)`, not `MRClientsCollector(self)`. So every submodule
calls `self.parent._create_gauge()` and `self.parent._set_metric()` directly against
`DeviceCollector`, with `MRCollector` never in the call chain.

`mx.py` does the opposite: `MXCollector` passes `self`, and its sub-collectors delegate through
`MXCollector`'s own `_create_gauge`/`_set_metric`. Do not carry an assumption from one to the other.

Only `MRCollector` extends `BaseDeviceCollector`. Every submodule is a plain class with
`parent`/`api`/`settings` attributes and a hand-rolled `_initialize_metrics()`, and none mixes in
`SubCollectorMixin`.

## Gauge re-exports

`MRCollector.__init__` re-exposes every submodule gauge as its own attribute (for example
`self._ap_clients = self.clients._ap_clients`) for call sites that still reach
`mr_collector._some_metric` directly. Adding a gauge that anything outside its submodule reads means
adding the matching re-export line in `collector.py`.

## Per-device path is nearly empty

`MRCollector.collect(device)`, called once per device by `DeviceCollector`, only delegates to
`clients.collect()`, which is a deliberate no-op. Ethernet, packet loss, CPU, SSID status and SSID
usage are all collected org- or network-wide through separate `collect_*` methods that
`DeviceCollector` calls on `MRCollector` directly.

## Newer domains ride an existing org-wide pass

None of the later submodules has its own `DeviceCollector` call site. Each is folded into an
existing `MRCollector` method and gates itself on its own endpoint group, so adding a domain here
means folding it into a pass that already carries `org_id`/`org_name` rather than editing
`../../device.py`.

- `signal_quality.collect_signal_quality` inside `collect_cpu_load`, gated on `MR_SIGNAL_QUALITY`.
  AP selection is client-side by device tag (`collectors.ap_signal_quality_tags`; empty means every
  wireless AP), and `collectors.collect_ap_signal_quality` turns the domain off entirely.
- `catalyst.collect_wireless_controllers` inside `collect_ssid_status`, gated on
  `MR_WIRELESS_CONTROLLER`, whose `enabled_fn` disables the group when `catalyst_ap_count == 0`.
  The response's `tags` and `details` arrays are deliberately not emitted.
- `client_logs.collect_client_logs` inside `collect_ssid_usage`.
- `performance.collect_power_mode` inside `collect_ethernet_status`.

## CPU load is the only batched fan-out

CPU comes only from `getOrganizationWirelessDevicesSystemCpuLoadHistory`, in batches of
`settings.api.batch_size` serials (`perPage=20` is the SDK maximum) with a 0.5s sleep between
batches. Removing that sleep or widening the batch trades directly against the rate-limit budget.

## Never wire liveTools or beta endpoints into this path

`createDeviceLiveToolsPing`, `createDeviceLiveToolsCableTest`, `createDeviceLiveToolsThroughputTest`
and every other `createDeviceLiveTools*` or beta wireless surface are on-demand *action* APIs: each
call triggers a device-side test, not a read of existing telemetry, and some sit on unstable beta
surfaces. Wiring one into a scheduled collector fires that action on every group tick - repeatedly
disrupting the device with test traffic, and an API-abuse risk. Exposing liveTools data at all would
have to be an explicit, rate-limited, opt-in mechanism, never folded into the regular `collect_*`
sweep.

## Stale-value retention in performance.py

`MRPerformanceCollector._set_packet_metric_value` caches the last non-zero value for any metric whose
name contains `total` but not `percent`, and reuses it when the API returns `None` or `0` for the
same label set, so total-packet-count gauges do not drop to zero on a transient empty response.
Percent and loss metrics are never cached this way. A "stuck" total is this guard, not a dead
collector.

## SSID usage is org-scoped only

`getOrganizationSummaryTopSsidsByUsage` returns one org-wide row per SSID name, so the SSID usage
gauges in `wireless.py` are labelled at org plus SSID level only. There is deliberately no
SSID-to-network mapping and no per-network fan-out.

## client_logs.py emits logs, never metrics

`MRClientLogsCollector` is a per-client data-log producer. It owns zero Prometheus metrics, because
per-client detail is unbounded, and emits OTLP log records through `self.parent.data_log_emitter`
(`core/otel_data_logs.py`), which may be `None`. The two events are `WIRELESS_CLIENT_PACKET_LOSS`
(one org-wide bulk `getOrganizationWirelessDevicesPacketLossByClient` call, one record per client
row) and `WIRELESS_CLIENT_SIGNAL_QUALITY` (experimental and off by default: one
`getNetworkWirelessSignalQualityHistory` call per active client, with the client universe
enumerated from `getNetworkClients` independently of packet loss, so a healthy zero-loss client
still emits a record). Both are gated on `emitter.is_event_enabled(...)` so a disabled event makes
no API call at all. Client MAC is emitted
only when `emitter.include_identifiers`. The packet-loss-by-client response carries no AP serial, so
`device.serial` is deliberately not emitted.

It declares no `EndpointGroup` and has no `_should_run_group` check, so when enabled it runs on every
`DeviceCollector` cycle rather than at the cadence of the group whose method it is folded into.
