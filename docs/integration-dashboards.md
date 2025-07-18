---
title: Integration & Dashboards
description: Integrating the Meraki Dashboard Exporter with Prometheus, Grafana Alloy, and creating effective dashboards
tags:
  - prometheus
  - grafana
  - alloy
  - dashboards
  - monitoring
  - integration
---

# Integration & Dashboards

This guide covers integrating the Meraki Dashboard Exporter with monitoring systems and accessing pre-built dashboards.

## Prometheus Integration

### Basic Scraping Configuration

Add the Meraki exporter to your `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'meraki'
    static_configs:
      - targets: ['meraki-exporter:9099']
    scrape_interval: 30s    # Match exporter's fastest collection
    scrape_timeout: 25s     # Slightly less than interval
    metrics_path: '/metrics'

    # Optional: Add environment labels
    relabel_configs:
      - target_label: environment
        replacement: production
```

### Kubernetes Service Discovery

For Kubernetes deployments:

```yaml
scrape_configs:
  - job_name: 'meraki'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: ['monitoring']
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: meraki-exporter
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
```

### Docker Compose with Prometheus

Complete monitoring stack example:

```yaml
services:
  meraki-exporter:
    image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
    environment:
      - MERAKI_API_KEY=${MERAKI_API_KEY}
    ports:
      - "9099:9099"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-storage:/var/lib/grafana

volumes:
  grafana-storage:
```

## Grafana Alloy Integration

[Grafana Alloy](https://grafana.com/docs/alloy/) is the new unified agent for telemetry collection. Here's how to scrape Meraki metrics with Alloy:

### Basic Alloy Configuration

Create an `alloy.alloy` configuration file:

```alloy
// Discover Meraki exporter targets
discovery.relabel "meraki" {
  targets = [{"__address__" = "meraki-exporter:9099"}]

  rule {
    target_label = "job"
    replacement  = "meraki"
  }

  rule {
    target_label = "environment"
    replacement  = "production"
  }
}

// Scrape Meraki metrics
prometheus.scrape "meraki" {
  targets    = discovery.relabel.meraki.output
  forward_to = [prometheus.remote_write.default.receiver]

  scrape_interval = "30s"
  scrape_timeout  = "25s"
  metrics_path    = "/metrics"
}

// Forward to Prometheus or Grafana Cloud
prometheus.remote_write "default" {
  endpoint {
    url = "http://prometheus:9090/api/v1/write"

    // For Grafana Cloud, use:
    // url = "https://prometheus-us-central1.grafana.net/api/prom/push"
    // basic_auth {
    //   username = "your_grafana_cloud_user"
    //   password = "your_api_key"
    // }
  }
}
```

### Kubernetes with Alloy

Deploy Alloy in Kubernetes to auto-discover Meraki exporters:

```alloy
// Kubernetes pod discovery
discovery.kubernetes "pods" {
  role = "pod"
  namespaces {
    names = ["monitoring"]
  }
}

// Filter for Meraki exporter pods
discovery.relabel "meraki" {
  targets = discovery.kubernetes.pods.targets

  rule {
    source_labels = ["__meta_kubernetes_pod_label_app"]
    action        = "keep"
    regex         = "meraki-exporter"
  }

  rule {
    source_labels = ["__meta_kubernetes_pod_name"]
    target_label  = "pod"
  }

  rule {
    source_labels = ["__meta_kubernetes_namespace"]
    target_label  = "namespace"
  }

  rule {
    target_label = "job"
    replacement = "meraki"
  }
}

prometheus.scrape "meraki" {
  targets    = discovery.relabel.meraki.output
  forward_to = [prometheus.remote_write.grafana_cloud.receiver]

  scrape_interval = "30s"
  scrape_timeout  = "25s"
}
```

### Running Alloy

Deploy Alloy alongside your Meraki exporter:

```bash
# With Docker
docker run -d \
  --name alloy \
  -v $(pwd)/alloy.alloy:/etc/alloy/config.alloy \
  -p 12345:12345 \
  grafana/alloy:latest \
  run --config.file=/etc/alloy/config.alloy

# With Docker Compose (add to your compose file)
alloy:
  image: grafana/alloy:latest
  volumes:
    - ./alloy.alloy:/etc/alloy/config.alloy
  ports:
    - "12345:12345"
  command: ["run", "--config.file=/etc/alloy/config.alloy"]
```

## Pre-built Dashboards

### Dashboard Repository

Pre-built Grafana dashboards for the Meraki Dashboard Exporter are available in the repository:

**📂 [View Dashboards](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/dashboards)**

Available dashboards include:

- **Meraki Overview**: High-level organizational metrics and health
- **Device Monitoring**: Device status, performance, and connectivity
- **Network Health**: Wireless performance and channel utilization
- **Environmental Monitoring**: MT sensor readings and alerts
- **API & Exporter Health**: Monitoring the exporter itself

### Dashboard Installation

1. **Download dashboards** from the [dashboards folder](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/dashboards)
2. **Import into Grafana**:
   - Go to Grafana → Dashboards → Import
   - Upload the JSON file or paste the content
   - Configure your Prometheus data source
3. **Customize** labels and queries for your environment

### Quick Dashboard Import

```bash
# Download all dashboards
git clone https://github.com/rknightion/meraki-dashboard-exporter.git
cd meraki-dashboard-exporter/dashboards

# Import via Grafana API
for dashboard in *.json; do
  curl -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer YOUR_GRAFANA_TOKEN" \
    -d @"$dashboard" \
    http://your-grafana:3000/api/dashboards/db
done
```

## Basic Alerting

### Essential Alert Rules

Create these basic Prometheus alert rules for Meraki monitoring:

```yaml
groups:
- name: meraki.basic
  rules:
  - alert: MerakiExporterDown
    expr: up{job="meraki"} == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Meraki exporter is unreachable"

  - alert: MerakiDeviceOffline
    expr: meraki_device_up == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Meraki device offline"
      description: "Device {{ $labels.name }} has been offline for 5+ minutes"

  - alert: MerakiHighTemperature
    expr: meraki_mt_temperature_celsius > 35
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "High temperature detected"
      description: "Temperature sensor {{ $labels.name }} reports {{ $value }}°C"
```

### Grafana Cloud Alerts

If using Grafana Cloud with Alloy, alerts can be configured directly in the Grafana Cloud interface using the same PromQL queries.

## Data Sources Configuration

### Prometheus Data Source

Configure Prometheus as a data source in Grafana:

```yaml
# grafana/provisioning/datasources/prometheus.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

### Grafana Cloud Data Source

For Grafana Cloud users, the data source is automatically configured when using Alloy with remote_write.

## Troubleshooting

### Common Integration Issues

#### Metrics Not Appearing in Prometheus

```bash
# Check if Prometheus can reach the exporter
curl http://localhost:9090/api/v1/targets

# Test scraping manually
curl http://meraki-exporter:9099/metrics | grep meraki_device_up
```

#### Dashboards Show No Data

1. **Verify data source**: Ensure Prometheus URL is correct
2. **Check time range**: Adjust dashboard time range
3. **Validate queries**: Test queries in Prometheus directly
4. **Check labels**: Ensure job labels match dashboard queries

#### Alloy Connection Issues

```bash
# Check Alloy status
curl http://localhost:12345/-/ready

# View targets being scraped
curl http://localhost:12345/api/v0/targets
```

For more detailed troubleshooting, see the [Deployment & Operations](deployment-operations.md#troubleshooting) guide.

## Next Steps

1. **Deploy monitoring stack**: Use Docker Compose or Kubernetes examples
2. **Import dashboards**: Download from the [dashboards repository](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/dashboards)
3. **Configure alerts**: Set up basic alerting rules for your environment
4. **Customize**: Adapt dashboards and alerts to your specific needs
