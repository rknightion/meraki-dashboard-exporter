---
title: OpenTelemetry
description: OpenTelemetry tracing and optional structured data-log configuration for the exporter
tags:
  - opentelemetry
  - tracing
  - logs
  - observability
---

# OpenTelemetry

The exporter uses OpenTelemetry for three independent, optional planes:

- **Traces** — self-observability spans for collection runs and API calls. This is instrumentation
  *about* the exporter, not a mirror of its data.
- **Structured data logs** — an optional OTLP **log** channel carrying high-cardinality, per-entity
  product data (e.g. per-client wireless packet loss) that must never become a labelled Prometheus
  series. See [Data logs vs. metrics](#data-logs-vs-metrics-the-boundary-rule) below.
- **OTLP metrics bridge** — an optional, opt-in periodic push of the existing Prometheus registry
  to an OTLP metrics endpoint, for operators who want push delivery (e.g. no scraper reaches this
  exporter, or metrics must ride the same collector pipeline as traces/logs). See
  [OTLP metrics export](#otlp-metrics-export) below.

Prometheus `/metrics` remains the **sole, default, and supported** metrics surface for this
exporter. Enabling the OTLP metrics bridge does not change `/metrics` output in any way, and
disabling it (the default) leaves the exporter's metrics behaviour exactly as before this feature
existed — the bridge only *pushes a copy* of what the registry already exposes, it never re-emits
metrics through a parallel OTel instrument pipeline. Tracing remains spans only, and data logs
remain log records only.

## Enable OTEL Tracing

```bash
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional
export MERAKI_EXPORTER_OTEL__SERVICE_NAME=meraki-dashboard-exporter
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"environment":"production"}'
```

- **Endpoint**: OTLP gRPC (`http://host:4317`). By default the exporter connects
  with `insecure=True` (plaintext, non-TLS). Set
  `MERAKI_EXPORTER_OTEL__INSECURE=false` to use TLS (system trust store) when
  talking to a collector endpoint that terminates TLS directly — no sidecar is
  required for that case.
- **Required**: `ENABLED=true` requires `ENDPOINT`; startup will fail without it.
- **Resource attributes**: JSON string of key/value pairs. The
  `environment` key is promoted to the `deployment.environment` resource
  attribute (defaults to `production`).

## Tracing Configuration

Tracing is enabled whenever OTEL is enabled (with a valid endpoint). You can
configure sampling:

```bash
# Optional sampling (default: 0.1 = 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

`SAMPLING_RATE` is a normal pydantic settings field on `OTelSettings`
(`sampling_rate`, range `0.0`-`1.0`, default `0.1`), so it is validated and
documented the same as any other setting under the `MERAKI_EXPORTER_OTEL__`
prefix.

See [Tracing](tracing.md) for details on spans, sampling behavior, and
instrumented components.

## TLS / mTLS for OTLP channels

`ca_cert_path`, `client_cert_path`, and `client_key_path` on `OTelSettings` are shared,
**paths-only** certificate configuration used by all three OTLP gRPC channels — traces, data
logs, and metrics:

```bash
export MERAKI_EXPORTER_OTEL__CA_CERT_PATH=/etc/otel/ca.pem
export MERAKI_EXPORTER_OTEL__CLIENT_CERT_PATH=/etc/otel/client.pem
export MERAKI_EXPORTER_OTEL__CLIENT_KEY_PATH=/etc/otel/client-key.pem
```

- **Paths only, never inline PEM.** Inline certificate material in an env var is exactly the kind
  of secret that ends up leaking into env dumps, `/status`, or log output — mount certs as files
  (the normal pattern for both Kubernetes and Docker) and point these settings at the mounted
  paths.
- **`client_cert_path` and `client_key_path` must be set together or not at all** (mTLS needs both
  the certificate and its key) — setting only one fails validation at startup.
- **Certs are only used on a channel whose resolved `insecure` is `false`.** If every enabled OTLP
  channel resolves to `insecure=true`, configuring any cert path is a startup validation error
  (it would silently do nothing, which is worse than failing loudly).
- **One trust domain for v1.** These fields are shared by all channels — there is no per-channel
  cert override. If you need different CAs per channel (e.g. traces to one collector, metrics to
  another with a different CA), that is a future extension, not supported today.
- **How the resolved `insecure` value works, per channel:** `otel.insecure` is the base value used
  by tracing; `otel.logs.insecure` and `otel.metrics.insecure` each independently inherit it when
  left `null`/unset, or override it explicitly. The same inheritance pattern applies to
  `endpoint` (see the data logs and OTLP metrics sections below).

## Data logs vs. metrics: the boundary rule

Per-entity signals whose population is unbounded or churny — a client ID/MAC, a per-delivery
webhook attempt, any row that fans out per-request rather than per-inventory-item — must never
become a labelled Prometheus series (see the cardinality rules in the root `CLAUDE.md`). Instead
they are emitted as structured OTLP **log** records through a dedicated `DataLogEmitter`
(`core/otel_data_logs.py`):

- **Metrics** carry bounded, fleet-shaped aggregates: label sets drawn from stable inventory
  (org / network / device serial / SSID number / port / band) or top-N sets bounded by
  construction.
- **Data logs** carry per-entity detail where the entity population is unbounded or churny
  (client ID/MAC, per-event, per-connection rows).
- New per-client (or otherwise unbounded per-entity) signals route to the data-log emitter, not to
  a new labelled metric. The existing opt-in `meraki_client_*`/`meraki_clients_*` surface
  (`collectors/clients.py`) is grandfathered under the ID-only + `meraki_client_info` join
  contract (#533) — it predates this doctrine and is not migrated by it.

This channel is completely independent of tracing: an operator can enable data logs without
tracing, or vice versa. It is also independent of the app's own stdout logging — the emitter
builds its own private `LoggerProvider` and never touches structlog/stdout output.

### Enable data logs

```bash
export MERAKI_EXPORTER_OTEL__LOGS__ENABLED=true

# Optional (defaults shown / inherited)
export MERAKI_EXPORTER_OTEL__LOGS__ENDPOINT=http://localhost:4317   # inherits otel.endpoint if unset
export MERAKI_EXPORTER_OTEL__LOGS__INSECURE=true                    # inherits otel.insecure if unset
export MERAKI_EXPORTER_OTEL__LOGS__INCLUDE_IDENTIFIERS=false        # PII opt-in, see below
export MERAKI_EXPORTER_OTEL__LOGS__EVENTS='["meraki.wireless.client.packet_loss"]'  # allowlist, default = all
```

| Setting | Env var | Default | Notes |
|---|---|---|---|
| `enabled` | `MERAKI_EXPORTER_OTEL__LOGS__ENABLED` | `false` | Independent of `otel.enabled` (tracing). Off by default. |
| `endpoint` | `MERAKI_EXPORTER_OTEL__LOGS__ENDPOINT` | `null` (inherits `otel.endpoint`) | OTLP gRPC endpoint for data logs. An endpoint must resolve (own or inherited) when `logs.enabled` is `true`, or startup fails. |
| `insecure` | `MERAKI_EXPORTER_OTEL__LOGS__INSECURE` | `null` (inherits `otel.insecure`) | Plaintext vs TLS transport for the data-log OTLP channel. |
| `include_identifiers` | `MERAKI_EXPORTER_OTEL__LOGS__INCLUDE_IDENTIFIERS` | `false` | PII opt-in. When `false`, identifier attributes (`client.mac`, `client.hostname`, `client.description`) are dropped from every record; only the stable `client.id` is emitted. Set `true` to include human-readable identifiers. |
| `events` | `MERAKI_EXPORTER_OTEL__LOGS__EVENTS` | `null` (all built-in events enabled) | JSON array allowlist of built-in event names (see `DataLogEvent` in `core/otel_data_logs.py`) to enable selectively, e.g. `["meraki.wireless.client.packet_loss"]`. |

Producers gate the underlying API fetch behind `is_event_enabled(...)` before making any Meraki
API call, so a disabled or non-allowlisted event costs zero rate-limit budget — not just zero
Prometheus cardinality.

### Built-in events and their API cost

The events are **not** equal in cost. The default (`events=null`) enables **all** of them,
which includes the expensive per-client fan-out — scope `events` to the cheap ones if you don't
want that.

| Event (`event.name`) | Emits | API cost when enabled |
|---|---|---|
| `meraki.wireless.client.packet_loss` | one record per wireless client per cycle (up/down/total loss %) | **Low** — a single org-wide bulk call (`getOrganizationWirelessDevicesPacketLossByClient`). |
| `meraki.org.webhook.delivery` | one record per outbound webhook delivery attempt | **Low** — reuses the webhook-logs fetch the aggregate metric already makes (no extra call). |
| `meraki.wireless.client.signal_quality` | one record per wireless client per cycle (RSSI/SNR) | **High — experimental.** One `getNetworkWirelessSignalQualityHistory` call **per client**, not a bulk endpoint. Interval-gated and bounded by `MERAKI_EXPORTER_API__CLIENT_SIGNAL_QUALITY_MAX_CLIENTS` (default 200) / `MERAKI_EXPORTER_API__CLIENT_SIGNAL_QUALITY_INTERVAL`, but still linear in client count. |

To ship the cheap events without the per-client fan-out:

```bash
export MERAKI_EXPORTER_OTEL__LOGS__EVENTS='["meraki.wireless.client.packet_loss","meraki.org.webhook.delivery"]'
```

Note this data-log event is independent of the `MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED`
metric path — that flag drives the ID-only `wireless_client_rssi`/`snr` **Prometheus** series;
the `signal_quality` data-log event above is its own per-client fan-out and fires whenever the
event is enabled. Enabling both runs the fan-out twice.

### Record shape

Each record carries a bounded, dot-namespaced attribute set: an `event.name` (the `DataLogEvent`
value, e.g. `meraki.wireless.client.packet_loss`), inventory context (`org.id`, `network.id`,
`network.name`, `device.serial` when applicable), the entity's stable `client.id` (always
present — not treated as PII), a `data.window_seconds` field describing the aggregation window,
and per-signal numeric payload attributes. Severity is always `INFO` — this is data, not an
alert. Identifier attributes (`client.mac`, `client.hostname`, `client.description`) are present
only when `include_identifiers=true`.

### Volume and cost caveat

Data logs are **per-entity, not per-metric-series** — a network with 10,000 active clients at a
5-minute cadence produces roughly 10,000 log records per interval per enabled event. This is
appropriate for a log/trace backend with volume-based retention (Loki, Elastic, any OTLP log
sink) but is a materially different cost profile from Prometheus scraping. Built-in producers run
on their host collector's own endpoint-group cadence (see [Scheduler
Architecture](scheduler.md)) — e.g. the MR per-client packet-loss/signal-quality producers ride
the `mr_ssid_usage` group (900s floor) and the webhook-delivery producer rides `org_webhook_logs`
(300s floor) — specifically to bound this; enabling more events or a shorter effective cadence
multiplies volume linearly. Size your backend's ingest/retention accordingly before enabling this
in a large environment.

### Self-observability

The emitter tracks its own health via two bounded Prometheus counters (not part of the data-log
channel itself — these are ordinary `meraki_exporter_*` self-observability metrics):

- `meraki_exporter_data_log_records_emitted_total{event=...}` — records successfully handed to the
  OTLP log pipeline.
- `meraki_exporter_data_log_records_dropped_total{event=...}` — records dropped before entering
  the pipeline (the `emit` call itself raised). Best-effort: batch-queue overflow drops inside the
  OTel SDK are logged by the SDK, not counted here.

Both are labelled only by the bounded `event` name (the fixed `DataLogEvent` enum), so they carry
no per-entity cardinality.

### Schema stability

The data-log record schema (event names and their attribute keys) is **experimental** and
explicitly excluded from the [Metric Stability & Deprecation Policy](../stability.md) — that
policy covers the Prometheus `/metrics` surface only. Event names and attributes may change
across any release, including patch releases, until the schema is proven out and promoted to a
documented contract.

## OTLP metrics export

The OTLP metrics bridge periodically takes a snapshot of the same Prometheus `CollectorRegistry`
that backs `/metrics` and pushes it over OTLP gRPC to a metrics collector endpoint. It is a pure
**push mirror** of the scrape surface — no separate OTel instrument pipeline exists, no collector
re-emits metrics through it, and nothing about `/metrics` changes whether this is enabled or not.
Use it when you want push delivery (no scraper reachable, or you want metrics riding the same
OTLP collector pipeline as traces/data logs) rather than as a replacement for scraping.

**This plane is experimental** and explicitly excluded from the
[Metric Stability & Deprecation Policy](../stability.md), which covers the Prometheus `/metrics`
surface only — the bridge's translation behaviour and its own self-observability metric names may
still change, including in a patch release, ahead of the Phase-6 live-collector verification
tracked in the v1-readiness follow-up work.

### Enable the OTLP metrics bridge

```bash
export MERAKI_EXPORTER_OTEL__METRICS__ENABLED=true

# Optional (defaults shown / inherited)
export MERAKI_EXPORTER_OTEL__METRICS__ENDPOINT=http://localhost:4317   # inherits otel.endpoint if unset
export MERAKI_EXPORTER_OTEL__METRICS__INSECURE=true                    # inherits otel.insecure if unset
export MERAKI_EXPORTER_OTEL__METRICS__EXPORT_INTERVAL_SECONDS=60
export MERAKI_EXPORTER_OTEL__METRICS__INCLUDE=all
export MERAKI_EXPORTER_OTEL__METRICS__TEMPORALITY=cumulative
```

| Setting | Env var | Default | Notes |
|---|---|---|---|
| `enabled` | `MERAKI_EXPORTER_OTEL__METRICS__ENABLED` | `false` | Independent of `otel.enabled` (tracing) and `otel.logs.enabled`. Off by default; `/metrics` scrape is unchanged either way. |
| `endpoint` | `MERAKI_EXPORTER_OTEL__METRICS__ENDPOINT` | `null` (inherits `otel.endpoint`) | OTLP gRPC endpoint for metrics. An endpoint must resolve (own or inherited) when `metrics.enabled` is `true`, or startup fails. |
| `insecure` | `MERAKI_EXPORTER_OTEL__METRICS__INSECURE` | `null` (inherits `otel.insecure`) | Plaintext vs TLS transport for the metrics OTLP channel. See [TLS / mTLS for OTLP channels](#tls-mtls-for-otlp-channels) above. |
| `export_interval_seconds` | `MERAKI_EXPORTER_OTEL__METRICS__EXPORT_INTERVAL_SECONDS` | `60` | Seconds between registry snapshots pushed via OTLP. Range 10–3600. |
| `include` | `MERAKI_EXPORTER_OTEL__METRICS__INCLUDE` | `all` | Which telemetry plane to push, split on the metric-name prefix: `product` = `meraki_*` excluding `meraki_exporter_*`; `self` = everything else (`meraki_exporter_*` plus the process/python runtime families); `all` = both. Defaults to `all` so an OTLP-only deployment (no scraper at all) doesn't silently lose exporter self-observability — `product` is the documented knob for cost-sensitive users who already collect self-obs elsewhere. |
| `temporality` | `MERAKI_EXPORTER_OTEL__METRICS__TEMPORALITY` | `cumulative` | Only `cumulative` is supported in v1, matching `prometheus_client`'s cumulative-since-start counter semantics and typical backend expectations. Delta temporality is out of scope until a concrete backend need arises. |

The heartbeat gauge described below is **always included in every push regardless of `include`**
— it is the one deliberate routing exemption, so an `include=product` deployment still gets bridge
liveness.

### Scrape vs. OTLP: differences to know

Pushing a copy of the registry over OTLP is not byte-identical to scraping `/metrics`. These are
the known, deliberate differences:

| Area | Scrape (`/metrics`) | OTLP push | Why |
|---|---|---|---|
| Liveness / `up` | Prometheus's own `up{job=...}` from the scrape itself | No `up` series is faked. Instead a self-obs gauge `meraki_exporter_otlp_metrics_last_success_timestamp_seconds` (unix timestamp of the last successful export) is pushed on every export, in every `include` mode. | Faking `up` would collide with backend scrape semantics that assume it comes from the scrape loop itself, not from pushed data. Alert on staleness instead: `time() - meraki_exporter_otlp_metrics_last_success_timestamp_seconds > 3 * export_interval_seconds`, plus `absent(meraki_exporter_otlp_metrics_last_success_timestamp_seconds)` to catch a total outage (the metric itself never arriving). |
| `job` / `instance` identity | Set by the Prometheus scrape config | Derived from the same OTel resource (`service.name` → `job`, `service.instance.id` → `instance`, remaining resource attributes → `target_info`) used by traces and data logs, so dashboard label selectors can target either path with the same values. `service.instance.id` falls back to the `HOSTNAME` env var or the literal `"unknown"` — running multiple instances without `HOSTNAME` set will collide on `instance` (this is pre-existing OTel-resource behaviour, not specific to the metrics bridge). | Reuses the single shared resource-builder so all three OTLP channels stay identity-consistent. |
| Metric/series names | Prometheus text-exposition names exactly as scraped (`_total`, `_bucket`/`_sum`/`_count`, `_info`, etc.) | Byte-identical to the scrape name: counters keep their `_total` suffix, info series keep `_info`, and the OTLP `Metric.unit` field is always left empty (our names already embed units like `_bytes`/`_seconds`, so a populated `unit` field risks a backend appending a second unit suffix). | The bridge hand-builds the OTLP metric name from the same family/sample name the scrape endpoint would render — no separate normalization step to drift out of sync. |
| Temporality | N/A (Prometheus counters are cumulative-since-process-start by definition) | `Sum`/`Histogram` are always tagged `AggregationTemporality.CUMULATIVE` | Matches `prometheus_client` semantics; see the `temporality` setting above. |
| Series lifetime / staleness | A series that `MetricExpirationManager` expires simply stops appearing in the next scrape; Prometheus's own staleness handling marks it stale after the configured lookback. | An expired series likewise stops appearing in the next push, but push-based backends (e.g. Grafana Cloud/Mimir) apply their own ingest-side staleness window (commonly ~5 minutes) before marking it stale — so an expired series can visibly linger longer on the OTLP path than on the scrape path. When a counter is later recreated, its fresh `prometheus_client`-issued `_created` timestamp becomes the pushed point's new OTLP start time, so backends see a clean counter reset rather than a value going backwards. | The bridge has no extra state beyond the live registry snapshot each interval; it relies on `_created` to signal resets. |
| `_created` series | Present in Prometheus text exposition for every counter/histogram | Never pushed as its own series — `_created` samples are consumed only as each data point's OTLP start time. | `_created` is a Prometheus exposition-format artifact, not real data; the push path has fewer series than the scrape path for this reason alone. |

**Cost note:** `include=all` (the default) pushes both the product-metrics plane and the exporter's
own self-observability plane every interval. On a large fleet this is a real data-point-per-minute
cost on a push-based backend; switch to `include=product` if you already collect exporter
self-observability another way (e.g. you also scrape `/metrics`) and only need product data pushed.
