---
title: Integration & Dashboards
description: Connect the exporter to Prometheus and Grafana
---

# Integration & Dashboards

The exporter exposes metrics on `http://<host>:9099/metrics`. Scrape this endpoint with Prometheus or any other OpenMetrics compatible collector.

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

Prometheus and Grafana configuration examples are available in the [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml).

## Dashboards
Pre-built Grafana dashboards can be found in the [dashboards directory](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/dashboards). Import them to get instant visibility into your organisation.

## Alerting
Use PromQL rules with metrics such as `meraki_device_up` or `meraki_collector_errors_total` to trigger alerts.

For more metrics see the [Metrics Reference](metrics/metrics.md).
Configuration options are documented in the [Configuration](config.md) guide.
