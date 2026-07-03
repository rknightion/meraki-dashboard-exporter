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

The exporter uses OpenTelemetry for two independent, optional planes:

- **Traces** — self-observability spans for collection runs and API calls. This is instrumentation
  *about* the exporter, not a mirror of its data.
- **Structured data logs** — an optional OTLP **log** channel carrying high-cardinality, per-entity
  product data (e.g. per-client wireless packet loss) that must never become a labelled Prometheus
  series. See [Data logs vs. metrics](#data-logs-vs-metrics-the-boundary-rule) below.

Prometheus `/metrics` remains the **sole metrics surface** for this exporter. Neither plane above
exports Prometheus metrics through OTEL — tracing is spans only, and data logs are log records
only. (A future OTLP *metrics* bridge is tracked separately and, if it ever lands, will be
documented as its own opt-in plane.)

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
sink) but is a materially different cost profile from Prometheus scraping. Built-in producers
default to the SLOW update tier specifically to bound this; enabling more events or lowering the
effective cadence multiplies volume linearly. Size your backend's ingest/retention accordingly
before enabling this in a large environment.

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
