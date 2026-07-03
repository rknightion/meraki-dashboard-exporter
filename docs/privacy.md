---
title: Data Privacy
description: What client/personal data the exporter can collect, where it lands, and how to disable or restrict it
tags:
  - privacy
  - gdpr
  - clients
  - pii
---

# Data Privacy

This exporter is primarily a **fleet/topology** metrics exporter: organizations, networks, devices,
ports, SSIDs, sensors. That data is not personal data. The one subsystem that *can* touch data about
identifiable people is **client tracking** (`collectors/clients.py`), which is **opt-in and disabled
by default**. This page documents exactly what it collects, where it can end up, and how to restrict
or disable it. See also [Security](security.md) for the endpoint threat model this page cross-references.

!!! note "Off by default"
    Client collection is controlled by `MERAKI_EXPORTER_CLIENTS__ENABLED` (`clients.enabled` in
    config), which defaults to `false`. With the default configuration, none of the data described
    below is collected, stored, or exposed.

## What counts as PII here

A Meraki "client" is a device (and by extension, usually a person) connected to the customer's
network. The identifiers the Dashboard API returns for a client can include its MAC address, DHCP
hostname, a user-supplied description, DNS-resolved hostname, IP address, and the SSID/VLAN it's
attached to. Depending on your environment and local law, some of these (MAC address, hostname,
resolved DNS name) may constitute personal data under GDPR or similar regimes.

## The current data contract (post-#533): ID-only numeric series + one join carrier

As of #533, **every numeric Prometheus client series carries only `client_id`** — a stable Meraki
identifier — as its client-scoped label, never mac/hostname/description/ssid. Confirmed in
`collectors/clients.py::_initialize_metrics`: `client_status`, `client_usage_sent/recv/total_bytes`,
`client_app_usage_*_bytes`, and the signal-quality gauges (`wireless_client_rssi`/`_snr`) all label
only with `org_id`, `network_id`, `client_id` (plus `type` for app-usage).

The **only** metric allowed to carry the descriptive/PII-ish fields is a single join carrier:

- **`meraki_client_info`** (`ClientMetricName.CLIENT_INFO`) — value always `1`, labelled
  `org_id`, `network_id`, `client_id`, `mac`, `description`, `hostname`, `ssid`. It exists purely so
  a PromQL query can `* on(client_id) group_left(mac, description, hostname, ssid)` the human-readable
  fields onto the ID-only numeric series when you need them. Because the label values (hostname,
  description, SSID) are mutable, the series' label set **churns and the old label combination
  expires** whenever a client's hostname/description/SSID changes — this is expected metric-expiration
  behavior, not a bug.

This means the *metrics plane* (`/metrics`) already minimises PII exposure: a scraper or Prometheus
retention store that never queries `meraki_client_info` never stores mac/hostname/description/ssid at
all, only opaque client IDs. If you don't need the human-readable join, you can drop
`meraki_client_info` at the scrape config (`metric_relabel_configs` action `drop`) to keep it out of
your TSDB/WAL entirely while keeping the ID-only numeric series.

## Where PII can actually land

Three places, only when client collection is enabled:

1. **The `meraki_client_info` Prometheus series** (above) — scraped into your Prometheus/Mimir/Cortex
   TSDB and its WAL, subject to whatever retention policy that system has. This is the main
   metrics-plane exposure and the reason to treat `meraki_client_info` as sensitive data at the
   storage layer, same as any other PII you'd put in a time series.
2. **The `/clients` HTML page.** This is a full non-Prometheus, non-labelled view: rendered in
   `templates/clients.html`, it shows description, hostname (DNS), IP address, IPv6 address, **MAC
   address**, and SSID/VLAN per client, sourced from the in-memory `ClientStore` and `DNSResolver`
   caches (not from the Prometheus registry). See [Security → endpoint exposure](security.md#endpoint-exposure--threat-model)
   for the full endpoint table — `/clients` is flagged there as the one endpoint with a firm **PII:
   Yes**.
3. **The OTel structured data-log channel**, if separately enabled (`otel.logs.enabled`, off by
   default) — see below.

Two in-memory caches back items 1–2 and are **not** exposed via `/metrics` themselves, but are the
source data for `/clients` and hold PII in process memory for as long as their TTL:

- **`ClientStore`** (`services/client_store.py`) — ID/hostname/description mappings, TTL
  `clients.cache_ttl` (`MERAKI_EXPORTER_CLIENTS__CACHE_TTL`, default 3600s / 1 hour).
- **`DNSResolver`** reverse-DNS cache (`services/dns_resolver.py`) — resolved hostnames keyed by
  client IP, TTL `clients.dns_cache_ttl` (`MERAKI_EXPORTER_CLIENTS__DNS_CACHE_TTL`, default 21600s /
  6 hours), bounded by `clients.dns_cache_max_entries` (default 100,000 entries) so memory stays
  bounded under client churn.

Neither cache persists to disk; both are cleared on process restart, and the DNS cache can be cleared
on demand via `POST /api/clients/clear-dns-cache` (itself protectable by `server.api_token`, see
below).

## OTel data logs: the other PII surface, and its own opt-in gate

Independently of Prometheus metrics, the exporter has an optional OTLP **data-log** emitter
(`otel.logs`, `core/otel_data_logs.py`, #622) for high-cardinality per-client signals (e.g. per-client
wireless packet loss) that must never become a labelled Prometheus series — see
[OpenTelemetry → data logs vs. metrics](observability/otel.md#data-logs-vs-metrics-the-boundary-rule)
for the full boundary rule. This channel is:

- **Off by default** — `otel.logs.enabled` (`MERAKI_EXPORTER_OTEL__LOGS__ENABLED`) defaults to
  `false`, and is independent of both `otel.enabled` (tracing) and the client collector's own
  `clients.enabled` gate.
- **PII-stripped by default even when enabled** — `otel.logs.include_identifiers`
  (`MERAKI_EXPORTER_OTEL__LOGS__INCLUDE_IDENTIFIERS`) defaults to `false`, which drops
  `client.mac` / `client.hostname` / `client.description` from every emitted record; only the stable
  `client.id` is included. Set it to `true` only if you specifically want the human-readable
  identifiers on that channel too, and understand they'll travel to whatever OTLP endpoint you've
  configured.

## Mitigations (by config key)

| Goal | Setting | Default | Effect |
| --- | --- | --- | --- |
| No client data at all | `clients.enabled` (`MERAKI_EXPORTER_CLIENTS__ENABLED`) | `false` | Collector is fully disabled: no client series, no `/clients` data, caches never populate. This is the default. |
| Keep client metrics but drop the PII join series at scrape time | n/a (Prometheus-side) | — | `drop` `meraki_client_info` in your scrape config's `metric_relabel_configs`; the ID-only numeric series are unaffected. |
| Restrict who can view the `/clients` PII page | `server.api_token` (`MERAKI_EXPORTER_SERVER__API_TOKEN`) | unset (open) | Requires `Authorization: Bearer <token>` on `/clients` and the other sensitive GET UIs plus the control POSTs (`/api/collectors/trigger`, `/api/clients/clear-dns-cache`). |
| Remove the `/clients` page (and other human UI) entirely | `server.ui_enabled` (`MERAKI_EXPORTER_SERVER__UI_ENABLED`) | `true` | When `false`, `/clients` (and `/`, `/status`, `/config`, `/cardinality*`) return `404`; `/metrics`/`/health`/`/ready` stay open. |
| Bound in-memory PII cache lifetime | `clients.cache_ttl`, `clients.dns_cache_ttl`, `clients.dns_cache_max_entries` | `3600`s, `21600`s, `100000` | Shorter TTLs age out stale hostname/description/DNS mappings sooner; the max-entries cap bounds worst-case memory regardless of churn. |
| Cap overall client series volume | `clients.max_clients_per_network`, `clients.max_clients_total` | `10000`, `25000` | Clients beyond the cap are dropped from metric emission (counted in `meraki_exporter_clients_over_cap`), bounding both cardinality and PII surface area under very large client populations. |
| Avoid per-client signal-quality collection | `clients.signal_quality_enabled` | `false` | RSSI/SNR are ID-only labelled already, but this endpoint is also the most expensive per-client API call; leave off unless needed. |
| Keep the structured data-log PII-stripped if that channel is used | `otel.logs.include_identifiers` | `false` | Drops `client.mac`/`client.hostname`/`client.description` from data-log records; only `client.id` is emitted. |

## Summary

The safest and default posture is **`clients.enabled=false`** — no client-scoped data of any kind is
collected. If you need client visibility, the ID-only-numeric-series-plus-`meraki_client_info`-join
design (#533) already minimises what lands in your metrics TSDB by default; the remaining exposure to
actively manage is the `/clients` HTML page (gate it with `server.api_token` and/or
`server.ui_enabled=false` if the exporter is reachable by anyone other than trusted operators) and, if
you separately opt into OTel data logs, the `include_identifiers` flag on that channel.
