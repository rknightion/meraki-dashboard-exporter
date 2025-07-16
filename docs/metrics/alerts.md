# Alert Metrics

The Meraki Dashboard Exporter collects and exposes Meraki Assurance alerts as Prometheus metrics, enabling you to monitor and alert on issues detected by Meraki's intelligent monitoring system.

## Overview

Meraki Assurance continuously monitors your network for issues and anomalies. The exporter transforms these alerts into metrics that can be used for:

- Real-time alerting in Prometheus/Alertmanager
- Historical analysis of network issues
- Correlation with other metrics
- SLA and reliability reporting

## Available Metrics

### Active Alerts by Category

#### `meraki_alerts_active`
- **Type**: Gauge
- **Description**: Number of active (non-dismissed, non-resolved) alerts
- **Labels**:
  - `org_id`, `org_name` - Organization identifiers
  - `type` - Alert type (e.g., `connectivity`, `configuration`)
  - `category` - Category type (e.g., `network`, `device`, `client`)
  - `severity` - Alert severity (`critical`, `warning`, `informational`)
  - `device_type` - Device type if applicable (e.g., `MR`, `MS`, `MX`)
  - `network_id`, `network_name` - Network identifiers
- **Update**: Medium tier (5 minutes)

### Summary Metrics

#### `meraki_alerts_total_by_severity`
- **Type**: Gauge
- **Description**: Total active alerts grouped by severity level
- **Labels**: `org_id`, `org_name`, `severity`
- **Update**: Medium tier (5 minutes)

#### `meraki_alerts_total_by_network`
- **Type**: Gauge
- **Description**: Total active alerts per network
- **Labels**: `org_id`, `org_name`, `network_id`, `network_name`
- **Update**: Medium tier (5 minutes)

## Alert Types and Categories

### Alert Types
Common alert types include:
- `connectivity` - Network connectivity issues
- `configuration` - Configuration problems
- `performance` - Performance degradation
- `security` - Security-related alerts
- `compliance` - Compliance violations

### Categories
- `network` - Network-wide issues
- `device` - Device-specific problems
- `client` - Client connectivity issues
- `application` - Application performance

### Severity Levels
- `critical` - Immediate attention required
- `warning` - Should be investigated
- `informational` - For awareness only

## Example Queries

### Alert Overview
```promql
# Total active alerts by severity
sum by (severity) (meraki_alerts_total_by_severity)

# Networks with most alerts
topk(5, meraki_alerts_total_by_network)

# Critical alerts by type
meraki_alerts_active{severity="critical"}
```

### Specific Alert Monitoring
```promql
# Connectivity issues on access points
meraki_alerts_active{type="connectivity", device_type="MR"}

# Configuration alerts in production network
meraki_alerts_active{category="configuration", network_name="Production"}

# Any critical alerts
meraki_alerts_active{severity="critical"} > 0
```

### Alert Trends
```promql
# Alert rate over time
rate(meraki_alerts_active[5m])

# Networks with increasing alerts
delta(meraki_alerts_total_by_network[1h]) > 0
```

## Alerting Rules

### Critical Alert Detection
```yaml
groups:
  - name: meraki_assurance
    rules:
      - alert: MerakiCriticalAlert
        expr: meraki_alerts_active{severity="critical"} > 0
        for: 5m
        labels:
          severity: critical
          team: network
        annotations:
          summary: "Critical Meraki alert detected"
          description: "{{ $labels.network_name }} has {{ $value }} critical {{ $labels.type }} alerts"
```

### High Alert Count
```yaml
- alert: MerakiHighAlertCount
  expr: sum by (network_name) (meraki_alerts_total_by_network) > 10
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "High number of Meraki alerts"
    description: "{{ $labels.network_name }} has {{ $value }} active alerts"
```

### Persistent Connectivity Issues
```yaml
- alert: MerakiPersistentConnectivity
  expr: meraki_alerts_active{type="connectivity"} > 0
  for: 30m
  labels:
    severity: warning
  annotations:
    summary: "Persistent connectivity issues"
    description: "{{ $labels.network_name }} has ongoing connectivity issues on {{ $labels.device_type }} devices"
```

## Grafana Dashboard Panels

### Alert Summary Table
```json
{
  "targets": [{
    "expr": "meraki_alerts_active",
    "format": "table",
    "instant": true
  }],
  "title": "Active Alerts",
  "type": "table",
  "transformations": [{
    "id": "organize",
    "options": {
      "excludeByName": {
        "Time": true,
        "__name__": true
      },
      "renameByName": {
        "network_name": "Network",
        "type": "Type",
        "severity": "Severity",
        "Value": "Count"
      }
    }
  }]
}
```

### Alert Severity Distribution
```json
{
  "targets": [{
    "expr": "sum by (severity) (meraki_alerts_total_by_severity)",
    "legendFormat": "{{ severity }}"
  }],
  "title": "Alerts by Severity",
  "type": "piechart",
  "pieType": "donut"
}
```

### Alert Timeline
```json
{
  "targets": [{
    "expr": "meraki_alerts_total_by_network",
    "legendFormat": "{{ network_name }}"
  }],
  "title": "Alert Count by Network",
  "type": "timeseries",
  "options": {
    "legend": {
      "calcs": ["lastNotNull", "max"],
      "displayMode": "table"
    }
  }
}
```

### Alert Heatmap
```json
{
  "targets": [{
    "expr": "meraki_alerts_active",
    "legendFormat": "{{ network_name }} - {{ type }}"
  }],
  "title": "Alert Distribution",
  "type": "heatmap",
  "dataFormat": "timeseries"
}
```

## Integration with Alertmanager

Example Alertmanager configuration for routing Meraki alerts:

```yaml
route:
  group_by: ['alertname', 'network_name', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        alertname: MerakiCriticalAlert
      receiver: 'pagerduty-critical'
      continue: true

    - match:
        severity: warning
      receiver: 'slack-warnings'

    - match_re:
        network_name: 'Production.*'
      receiver: 'email-production'

receivers:
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'YOUR_SERVICE_KEY'
        description: 'Meraki Critical Alert: {{ .GroupLabels.network_name }}'

  - name: 'slack-warnings'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK'
        channel: '#network-alerts'
        title: 'Meraki Alert'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

## Best Practices

### 1. Alert Fatigue Prevention
- Set appropriate thresholds
- Use time-based conditions (for: 5m)
- Group related alerts
- Implement proper severity levels

### 2. Correlation
Combine alert metrics with other metrics for better insights:
```promql
# Correlate alerts with device status
meraki_alerts_active{device_type="MR"}
  and on(network_id)
  (count by (network_id) (meraki_device_up{device_model=~"MR.*"} == 0) > 0)
```

### 3. SLA Reporting
Track alert-free time for SLA calculations:
```promql
# Hours without critical alerts (per day)
(1 - (sum_over_time(meraki_alerts_active{severity="critical"}[1d]) > bool 0)) * 24
```

### 4. Noise Reduction
- Focus on actionable alerts
- Use severity levels appropriately
- Consider business hours for non-critical alerts
- Implement alert suppression during maintenance

## Troubleshooting

### Missing Alerts

If alerts aren't appearing:

1. **Check API Access**: Ensure your API key has read access to assurance data
2. **Verify Organization**: Some organizations may not have assurance features enabled
3. **Review Logs**: Check DEBUG logs for API responses
4. **Alert State**: Only active (non-dismissed) alerts are collected

### High Cardinality

To manage metric cardinality with many alerts:

1. Use the summary metrics (`meraki_alerts_total_by_severity`)
2. Aggregate by network or severity in queries
3. Consider increasing the collection interval
4. Use recording rules for common aggregations

### API Limitations

- The assurance alerts API may not be available for all organizations
- Returns only active alerts (not historical)
- Limited to alerts from the Meraki Assurance system
