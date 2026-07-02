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
    Align your Prometheus scrape interval with the exporter’s update tiers to avoid unnecessary load (see [Metrics Overview](metrics/overview.md)).

## Dashboards
Pre-built Grafana dashboards live in the [dashboards directory](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/dashboards). Import them to get instant visibility into your organisation. Bundled dashboards include:

- `organization-overview.json` – org-wide rollup
- `network-overview.json` – network inventory and status
- `network-health-performance.json` – network health, RF, and performance
- `mr-access-points.json` – MR (wireless) APs
- `ms-switches.json` – MS switches
- `mx-security-appliances.json` – MX appliances and uplinks
- `mt-sensors.json` – MT environmental sensors
- `mv-security-cameras.json` – MV cameras
- `mg-cellular-gateways.json` – MG cellular gateways
- `client-overview.json` – client tracking
- `assurance-alerts.json` – alerts and assurance
- `api-usage-licensing.json` – API usage and licensing
- `exporter-monitoring.json` – self-monitoring of the exporter

## Alerting
Use PromQL rules with metrics such as `meraki_device_up` or `meraki_exporter_collection_errors_total` to trigger alerts.

For more metrics see the [Metrics Reference](metrics/metrics.md).
Configuration options are documented in the [Configuration](config.md) guide.
OpenTelemetry tracing is documented in [OpenTelemetry](observability/otel.md).
