---
title: Integration & Dashboards
description: Connect the exporter to Prometheus and Grafana
---

# Integration & Dashboards

The exporter exposes metrics on `http://<host>:9099/metrics`. Scrape this
endpoint with Prometheus or any other OpenMetrics compatible collector.

## Prometheus example
```yaml
scrape_configs:
  - job_name: meraki
    static_configs:
      - targets: ['meraki-dashboard-exporter:9099']
```

## Grafana Alloy example
```alloy
discovery.relabel "meraki" {
  targets = [{"__address__" = "meraki-dashboard-exporter:9099"}]
}

prometheus.scrape "meraki" {
  targets    = discovery.relabel.meraki.output
  forward_to = [prometheus.remote_write.default.receiver]
  scrape_interval = "30s"
  scrape_timeout  = "25s"
}

prometheus.remote_write "default" {
  endpoint { url = "http://prometheus:9090/api/v1/write" }
}
```

The [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) ships only the exporter container; integrate the scrape job above into your existing Prometheus/Grafana stack.

!!! tip "Scrape interval"
    Align your Prometheus scrape interval with the exporter's adaptive collector cadence to avoid unnecessary load — see [Metrics Overview](metrics/overview.md) and [Scheduler Architecture](observability/scheduler.md).

## Dashboards
Pre-built Grafana dashboards (Grafana **v2 schema**, tabbed) live in the [`grafana/dashboards` directory](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/grafana/dashboards). Import them in the Grafana UI, or deploy them with the [`gcx`](https://github.com/grafana/grafana-com-cli) CLI. The set is six consolidated, multi-tab dashboards:

- `self-observability.json` – the exporter's own health: collectors, adaptive scheduler, API rate limiting, plus traces and logs tabs
- `meraki-devices.json` – all device types as tabs (MR / MS / MX / MT / MV); a tab auto-hides when the selected org has no such devices
- `meraki-organization.json` – org rollup, API usage & licensing, alerts
- `meraki-network-health.json` – connection stats, RF, data rates, SSID performance, Bluetooth
- `meraki-clients.json` – client tracking (counts, usage, DNS resolution health)
- `meraki-client-telemetry.json` – per-client data-log telemetry (signal quality / packet loss / webhook delivery)

Each dashboard uses an `org_id` template variable, so one dashboard serves every organisation you monitor, and all panels target the standard Prometheus scrape path (native metric names).

## Alerting
Use PromQL rules with metrics such as `meraki_device_up` or `meraki_exporter_collection_errors_total` to trigger alerts.

A curated set of ~15 starter alert rules — covering device down, API rate-limit
exhaustion/429 storms, collector failure & backoff, cardinality shedding,
exporter self-health/liveness, and product signals such as MT sensor alerting,
license expiry, and the `meraki_org_has_beta_api` risk gauge — ships as a
Prometheus Operator `PrometheusRule` at
[`examples/prometheus-rules.yaml`](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/examples/prometheus-rules.yaml).
Each rule's `for:` duration is derived from the [Data Freshness & Alerting
Guidance](data-freshness.md) tier table, cited inline as a comment.

If you deploy via the [Helm chart](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/charts/meraki-dashboard-exporter),
set `prometheusRule.enabled: true` (requires the Prometheus Operator CRDs) to
have the chart render the same rule set directly — see the `prometheusRule.*`
values (namespace override, additional labels, per-group toggles, and a
`webhooksEnabled` switch that picks the matching device-down alert variant).

For **Grafana Cloud / Mimir ruler** (no Prometheus Operator), the same 15 alerts plus a set
of derived recording rules are provided as ready-to-load rule-group YAML in
[`grafana/alerts/`](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/grafana/alerts)
(`alerting-rules.yaml`, `recording-rules.yaml`) — load with `mimirtool rules load`.

For more metrics see the [Metrics Reference](metrics/metrics.md).
Configuration options are documented in the [Configuration](config.md) guide.
OpenTelemetry tracing is documented in [OpenTelemetry](observability/otel.md).
