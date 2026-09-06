# Network health collectors

Eight network-level wireless domains under one `NetworkHealthCollector` coordinator
(`../network_health.py`). `base.py` supplies the shared `parent`/`api`/`settings` wiring and defines
no metrics of its own.

## Never emit a value on an unavailable or rate-limited fetch

Skipping emission is deliberate (F-015): a transient 429 or a temporarily-unavailable endpoint must
not manufacture a confident "0 clients" reading that a presence or asset-tracking alert reads as a
real drop to zero. Let the series keep its prior value and expire naturally. Do not "fix" a
sub-collector by having it write a zero on the error path.

## Wireless-only filtering happens once, upstream

`NetworkHealthCollector._collect_org_network_health` narrows the org's networks to those with
`ProductType.WIRELESS` before dispatching to any sub-collector. Individual `collect()` methods do not
re-check product types, and adding a redundant per-collector check gives you a second filter that can
silently diverge from the first.

## RFHealthCollector is the shape exception

Seven sub-collectors implement `async collect(self, network)` and are called per-network from the
bundle. `RFHealthCollector` implements `collect_org(org_id, org_name, networks)` instead, because its
channel-utilization fetch is org-wide. It also resolves serial-to-model labels from
`self.parent.inventory.get_devices(org_id)` and returns an empty mapping when `inventory` is `None` -
there is no direct-API fallback.

## Error handling is not uniform

Six sub-collectors (`bluetooth`, `connection_stats`, `data_rates`, `rf_health`, `ssid_performance`,
`mesh`) catch broadly and inspect `str(e)` for `"400"`, `"404"`, `"Bad Request"` or `"rate limit"`
(case-insensitive) to separate "endpoint not available for this network" (logged at `debug`,
collection continues) from a real failure (`logger.exception`). `latency_stats` and `air_marshal`
instead wrap their fetchers in `@with_error_handling(continue_on_error=True, ...)` and let the shared
decorator categorise. Match the file you are in rather than unifying the two as a drive-by.

## Fixed request parameters

- Bluetooth clients: `timespan=300`, `perPage=1000`, `total_pages="all"`.
- Connection stats: `timespan=1800`. Shorter windows are unreliable on this endpoint.
- Data rate history: `timespan=300` with `resolution=300`; read the most recent bucket after sorting
  by `endTs`.
- SSID failed connections: `timespan=3600`.
- Channel utilization (`getOrganizationWirelessDevicesChannelUtilizationByDevice` and
  `...ByNetwork`): `timespan=600`, `interval=600`, `perPage=1000`, `total_pages="all"`. The parameter
  is `interval`, not `resolution`.

## Two metric-name enums

`_network_connection_stats` comes from `NetworkMetricName`; every other gauge on this coordinator
comes from `NetworkHealthMetricName`. Check both when hunting for a network-health metric name.
