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
(`core/otel_data_logs.py`), which may be `None`. Both events are gated on
`emitter.is_event_enabled(...)` so a disabled event makes no API call at all. Client MAC is emitted
only when `emitter.include_identifiers`. The packet-loss-by-client response carries no AP serial, so
`device.serial` is deliberately not emitted.

It declares no `EndpointGroup` and has no `_should_run_group` check, so when enabled it runs on every
`DeviceCollector` cycle rather than at the cadence of the group whose method it is folded into.
