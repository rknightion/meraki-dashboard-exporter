# Prometheus Integration

This guide covers how to integrate the Meraki Dashboard Exporter with Prometheus for metrics collection and alerting.

## Basic Configuration

### Prometheus Scrape Configuration

Add the Meraki exporter to your `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'meraki'
    static_configs:
      - targets: ['meraki-exporter:9099']
    scrape_interval: 30s    # Match exporter's fastest collection
    scrape_timeout: 25s     # Slightly less than interval
    metrics_path: '/metrics'

    # Optional: Add custom labels
    relabel_configs:
      - target_label: environment
        replacement: production
      - target_label: region
        replacement: us-east
```

### Service Discovery

#### Kubernetes Service Discovery

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
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
```

#### Docker Swarm Service Discovery

```yaml
scrape_configs:
  - job_name: 'meraki'
    dockerswarm_sd_configs:
      - host: unix:///var/run/docker.sock
        role: services
    relabel_configs:
      - source_labels: [__meta_dockerswarm_service_name]
        regex: meraki-exporter
        action: keep
```

## Advanced Configuration

### Metric Relabeling

Optimize metric storage and query performance:

```yaml
scrape_configs:
  - job_name: 'meraki'
    static_configs:
      - targets: ['meraki-exporter:9099']

    metric_relabel_configs:
      # Drop high-cardinality port metrics if not needed
      - source_labels: [__name__]
        regex: 'meraki_ms_port_.*'
        action: drop

      # Drop specific device serials for privacy
      - source_labels: [device_serial]
        regex: 'Q2XX-SENSITIVE.*'
        action: drop

      # Simplify device model labels
      - source_labels: [device_model]
        regex: '(M[RSXVTG])[0-9].*'
        target_label: device_type

      # Add custom org label
      - source_labels: [org_name]
        regex: '(.*) - Production'
        target_label: org_group
        replacement: 'production'
```

### Federation Setup

For large deployments, use Prometheus federation:

```yaml
# Global Prometheus configuration
scrape_configs:
  - job_name: 'federate'
    scrape_interval: 30s
    honor_labels: true
    metrics_path: '/federate'
    params:
      'match[]':
        # Federate organization-level metrics
        - '{__name__=~"meraki_org_.*"}'
        # Federate alert metrics
        - '{__name__=~"meraki_alerts_.*"}'
        # Federate summary metrics
        - '{__name__=~"meraki:.*"}'  # Recording rules
    static_configs:
      - targets:
        - 'prometheus-region1:9090'
        - 'prometheus-region2:9090'
```

## Storage Optimization

### Retention Configuration

```yaml
# prometheus.yml or command-line flags
storage:
  tsdb:
    retention.time: 30d           # Keep data for 30 days
    retention.size: 100GB         # Maximum storage size
    wal.compression: true         # Enable WAL compression
```

### Downsampling with Recording Rules

Create recording rules to downsample high-frequency metrics:

```yaml
groups:
  - name: meraki_downsampling
    interval: 5m
    rules:
      # 5-minute averages
      - record: meraki:device_availability:5m
        expr: avg_over_time(meraki_device_up[5m])

      # Hourly aggregations
      - record: meraki:client_count:1h
        expr: avg_over_time(meraki_org_clients_total[1h])

      # Daily maximums
      - record: meraki:max_temperature:1d
        expr: max_over_time(meraki_mt_temperature_celsius[1d])
```

## Alerting Rules

### Critical Infrastructure Alerts

Create `alerts/meraki_critical.yml`:

```yaml
groups:
  - name: meraki_critical
    interval: 30s
    rules:
      - alert: MerakiExporterDown
        expr: up{job="meraki"} == 0
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Meraki exporter is down"
          description: "The Meraki Dashboard Exporter has been down for more than 5 minutes."
          runbook_url: "https://wiki.example.com/runbooks/meraki-exporter-down"

      - alert: MerakiMultipleDevicesDown
        expr: count(meraki_device_up == 0) > 5
        for: 10m
        labels:
          severity: critical
          team: network-ops
        annotations:
          summary: "Multiple Meraki devices are offline"
          description: "{{ $value }} Meraki devices have been offline for more than 10 minutes."
          dashboard_url: "https://grafana.example.com/d/meraki-devices"

      - alert: MerakiSiteDown
        expr: |
          (
            count by (network_name) (meraki_device_up{network_name!=""} == 0)
            /
            count by (network_name) (meraki_device_up{network_name!=""})
          ) > 0.5
        for: 5m
        labels:
          severity: critical
          team: network-ops
        annotations:
          summary: "Meraki site {{ $labels.network_name }} is down"
          description: "More than 50% of devices at {{ $labels.network_name }} are offline."
```

### Performance Alerts

Create `alerts/meraki_performance.yml`:

```yaml
groups:
  - name: meraki_performance
    interval: 60s
    rules:
      - alert: MerakiHighChannelUtilization
        expr: meraki_ap_channel_utilization_5ghz_percent > 80
        for: 15m
        labels:
          severity: warning
          team: network-ops
        annotations:
          summary: "High WiFi channel utilization"
          description: "5GHz channel utilization on {{ $labels.device_name }} is {{ $value }}%"

      - alert: MerakiWirelessConnectionFailures
        expr: meraki_network_wireless_connection_success_percent{connection_step="success"} < 90
        for: 20m
        labels:
          severity: warning
          team: network-ops
        annotations:
          summary: "Low wireless connection success rate"
          description: "Connection success rate for {{ $labels.network_name }} is {{ $value }}%"

      - alert: MerakiHighPortErrors
        expr: rate(meraki_ms_port_errors_total[5m]) > 100
        for: 10m
        labels:
          severity: warning
          team: network-ops
        annotations:
          summary: "High switch port error rate"
          description: "Port {{ $labels.port_id }} on {{ $labels.device_name }} has high error rate"
```

### Environmental Alerts

Create `alerts/meraki_environmental.yml`:

```yaml
groups:
  - name: meraki_environmental
    interval: 30s
    rules:
      - alert: MerakiHighTemperature
        expr: meraki_mt_temperature_celsius > 30
        for: 10m
        labels:
          severity: warning
          team: facilities
        annotations:
          summary: "High temperature detected"
          description: "Temperature at {{ $labels.device_name }} is {{ $value }}°C"

      - alert: MerakiWaterDetected
        expr: meraki_mt_water_detected == 1
        for: 1m
        labels:
          severity: critical
          team: facilities
        annotations:
          summary: "Water detected"
          description: "Water sensor {{ $labels.device_name }} has detected water presence"

      - alert: MerakiDoorOpenTooLong
        expr: meraki_mt_door_status == 1
        for: 30m
        labels:
          severity: warning
          team: security
        annotations:
          summary: "Door left open"
          description: "Door {{ $labels.device_name }} has been open for more than 30 minutes"
```

## Query Examples

### Useful PromQL Queries

```promql
# Device availability by type (percentage)
100 * (
  sum by (device_model) (meraki_device_up)
  /
  count by (device_model) (meraki_device_up)
)

# Top 10 devices by client count
topk(10, meraki_mr_clients_connected)

# Average temperature by location
avg by (network_name) (meraki_mt_temperature_celsius)

# Bandwidth usage in Mbps
sum by (org_name) (
  rate(meraki_org_usage_total_kb[5m]) * 8 / 1000
)

# License utilization
100 * (
  meraki_org_licenses_total{status="active"}
  /
  sum by (org_id, license_type) (meraki_org_licenses_total)
)

# WiFi connection success trend
100 - (100 *
  rate(meraki_network_wireless_connection_success_percent{connection_step!="success"}[1h])
)

# Alert count by severity
sum by (severity) (meraki_alerts_active)

# API usage rate
rate(meraki_collector_api_calls_total[5m])
```

### Debugging Queries

```promql
# Check last successful collection time
time() - meraki_collector_last_success_timestamp_seconds

# Collection duration by collector
histogram_quantile(0.95,
  rate(meraki_collector_duration_seconds_bucket[5m])
)

# Error rate by collector
rate(meraki_collector_errors_total[5m])

# Metric freshness (staleness check)
(time() - timestamp(meraki_device_up)) > 600
```

## Grafana Variables

Create useful variables for dashboards:

```promql
# Organization selector
label_values(meraki_org_info, org_name)

# Network selector (filtered by org)
label_values(meraki_device_up{org_name="$org"}, network_name)

# Device type selector
label_values(meraki_device_up, device_model)

# Alert severity selector
label_values(meraki_alerts_active, severity)
```

## Best Practices

### 1. Scrape Configuration

- Set scrape interval ≥ 30s (matches exporter's fastest tier)
- Use appropriate timeout (interval - 5s)
- Enable compression for remote write

### 2. Label Management

- Keep labels consistent across metrics
- Avoid high-cardinality labels in aggregations
- Use label_replace() for label transformations

### 3. Query Optimization

- Use recording rules for expensive queries
- Leverage PromQL functions efficiently
- Avoid regex matches on large datasets

### 4. Alert Design

- Set appropriate evaluation intervals
- Use `for` clauses to prevent flapping
- Include meaningful descriptions and runbook links

### 5. Storage Planning

- Plan retention based on compliance needs
- Use remote storage for long-term retention
- Monitor storage growth trends

## Troubleshooting

### Missing Metrics

```promql
# Check if exporter is being scraped
up{job="meraki"}

# Check scrape duration
prometheus_target_scrape_duration_seconds{job="meraki"}

# Check for scrape errors
prometheus_target_scrape_samples_scraped{job="meraki"} == 0
```

### Slow Queries

```promql
# Identify slow queries
topk(10, prometheus_engine_query_duration_seconds)

# Check query samples
prometheus_engine_query_samples_per_second
```

### High Cardinality

```promql
# Count series by metric
count by (__name__)({job="meraki"})

# Find high cardinality metrics
topk(20, count by (__name__)({job="meraki"}))
```
