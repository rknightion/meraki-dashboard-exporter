# Organization Metrics

Organization-level metrics provide insights into your entire Meraki infrastructure, including API usage, licensing, device inventory, and client statistics.

## Available Metrics

### Organization Information

#### `meraki_org_info`
- **Type**: Info
- **Description**: Organization metadata
- **Labels**: `org_id`, `org_name`
- **Info Labels**: `url`, `api_enabled`

### API Metrics

#### `meraki_org_api_requests_total`
- **Type**: Gauge
- **Description**: Total API requests made by the organization (24-hour window)
- **Labels**: `org_id`, `org_name`
- **Update**: Medium tier (5 minutes)

!!! info "API Usage Monitoring"
    This metric helps track API consumption against your rate limits. Meraki enforces rate limits per organization.

### Network Metrics

#### `meraki_org_networks_total`
- **Type**: Gauge
- **Description**: Total number of networks in the organization
- **Labels**: `org_id`, `org_name`
- **Update**: Medium tier (5 minutes)

### Device Metrics

#### `meraki_org_devices_total`
- **Type**: Gauge
- **Description**: Total number of devices by type
- **Labels**: `org_id`, `org_name`, `device_type`
- **Update**: Medium tier (5 minutes)
- **Device Types**: `MS` (switches), `MR` (wireless), `MX` (security), `MV` (cameras), `MT` (sensors), `MG` (cellular)

Example:
```promql
# Total switches in organization
meraki_org_devices_total{device_type="MS"}

# All devices across all organizations
sum by (org_name) (meraki_org_devices_total)
```

#### `meraki_org_devices_by_model_total`
- **Type**: Gauge
- **Description**: Device count by specific model
- **Labels**: `org_id`, `org_name`, `model`
- **Update**: Medium tier (5 minutes)

Example:
```promql
# Count of specific switch model
meraki_org_devices_by_model_total{model="MS120-8LP"}

# Top 10 device models
topk(10, sum by (model) (meraki_org_devices_by_model_total))
```

### License Metrics

#### `meraki_org_licenses_total`
- **Type**: Gauge
- **Description**: License count by type and status
- **Labels**: `org_id`, `org_name`, `license_type`, `status`
- **Update**: Medium tier (5 minutes)
- **License Types**: `ENT` (Enterprise), `MR` (Wireless), `MS` (Switch), `MX` (Security), etc.
- **Status**: `active`, `expired`, `expiring`

#### `meraki_org_licenses_expiring`
- **Type**: Gauge
- **Description**: Number of licenses expiring within 30 days
- **Labels**: `org_id`, `org_name`, `license_type`
- **Update**: Medium tier (5 minutes)

!!! warning "License Monitoring"
    Set up alerts for expiring licenses to avoid service disruption:
    ```promql
    meraki_org_licenses_expiring > 0
    ```

### Client Metrics

#### `meraki_org_clients_total`
- **Type**: Gauge
- **Description**: Total number of active clients (5-minute window from last complete interval)
- **Labels**: `org_id`, `org_name`
- **Update**: Medium tier (5 minutes)

!!! info "5-Minute Window Behavior"
    This metric represents the last complete 5-minute interval. For example, if collected at 11:04, it shows clients from 10:55-11:00.

### Usage Metrics

All usage metrics represent data transfer in the last complete 5-minute window:

#### `meraki_org_usage_total_kb`
- **Type**: Gauge
- **Description**: Total data usage in KB for the 5-minute window
- **Labels**: `org_id`, `org_name`
- **Update**: Medium tier (5 minutes)

#### `meraki_org_usage_downstream_kb`
- **Type**: Gauge
- **Description**: Downstream (download) data usage in KB
- **Labels**: `org_id`, `org_name`
- **Update**: Medium tier (5 minutes)

#### `meraki_org_usage_upstream_kb`
- **Type**: Gauge
- **Description**: Upstream (upload) data usage in KB
- **Labels**: `org_id`, `org_name`
- **Update**: Medium tier (5 minutes)

!!! tip "Calculating Rates"
    To calculate bandwidth rates from KB values:
    ```promql
    # Downstream rate in Mbps
    (rate(meraki_org_usage_downstream_kb[5m]) * 8) / 1000
    ```

### Configuration Change Tracking

#### `meraki_org_configuration_changes_total`
- **Type**: Gauge
- **Description**: Total number of configuration changes in the last 24 hours
- **Labels**: `org_id`, `org_name`
- **Update**: Slow tier (15 minutes)

## Example Queries

### Organization Overview
```promql
# Total devices per organization
sum by (org_name) (meraki_org_devices_total)

# Organizations with most networks
topk(5, meraki_org_networks_total)

# License utilization by type
meraki_org_licenses_total{status="active"}
  / ignoring(status) group_left
    sum by (org_id, org_name, license_type) (meraki_org_licenses_total)
```

### Client and Usage Analysis
```promql
# Client density (clients per device)
meraki_org_clients_total / sum by (org_id) (meraki_org_devices_total{device_type="MR"})

# Upload/download ratio
meraki_org_usage_upstream_kb / meraki_org_usage_downstream_kb

# Total bandwidth in Mbps (5-minute average)
(meraki_org_usage_total_kb * 8) / (5 * 60 * 1000)
```

### Configuration Changes
```promql
# Organizations with recent changes
meraki_org_configuration_changes_total > 0

# Change rate per hour
meraki_org_configuration_changes_total / 24
```

## Alerting Examples

### License Expiration Alert
```yaml
groups:
  - name: meraki_licenses
    rules:
      - alert: MerakiLicenseExpiring
        expr: meraki_org_licenses_expiring > 0
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Meraki licenses expiring soon"
          description: "{{ $labels.org_name }} has {{ $value }} {{ $labels.license_type }} licenses expiring within 30 days"
```

### High Configuration Change Rate
```yaml
groups:
  - name: meraki_config
    rules:
      - alert: HighConfigurationChangeRate
        expr: meraki_org_configuration_changes_total > 100
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "High configuration change rate"
          description: "{{ $labels.org_name }} has {{ $value }} configuration changes in the last 24 hours"
```

### API Usage Alert
```yaml
groups:
  - name: meraki_api
    rules:
      - alert: HighAPIUsage
        expr: rate(meraki_org_api_requests_total[1h]) > 1000
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "High API usage rate"
          description: "{{ $labels.org_name }} is making {{ $value }} API requests per hour"
```

## Grafana Dashboard Panels

### License Status Panel
```json
{
  "targets": [{
    "expr": "meraki_org_licenses_total",
    "legendFormat": "{{ license_type }} - {{ status }}"
  }],
  "title": "License Status by Type",
  "type": "piechart"
}
```

### Client Count Time Series
```json
{
  "targets": [{
    "expr": "meraki_org_clients_total",
    "legendFormat": "{{ org_name }}"
  }],
  "title": "Active Clients Over Time",
  "type": "timeseries"
}
```

### Bandwidth Usage
```json
{
  "targets": [
    {
      "expr": "(rate(meraki_org_usage_downstream_kb[5m]) * 8) / 1000",
      "legendFormat": "Download"
    },
    {
      "expr": "(rate(meraki_org_usage_upstream_kb[5m]) * 8) / 1000",
      "legendFormat": "Upload"
    }
  ],
  "title": "Bandwidth Usage (Mbps)",
  "type": "timeseries",
  "fieldConfig": {
    "defaults": {
      "unit": "Mbits"
    }
  }
}
```

## Troubleshooting

### Missing Metrics

If organization metrics are missing:

1. **Check API Key Permissions**: Ensure your API key has organization-wide read access
2. **Verify Organization ID**: If using `MERAKI_EXPORTER_ORG_ID`, ensure it's correct
3. **Check Logs**: Look for API errors in DEBUG logs
4. **API Availability**: Some APIs may not be available for all organization types

### Incorrect Client Counts

Client count considerations:
- Represents the last complete 5-minute interval
- Only includes active clients (associated and passing traffic)
- May differ from real-time dashboard due to timing

### Usage Data Interpretation

- Usage is measured in KB for the 5-minute window
- To convert to rate: `(KB * 8) / (5 * 60)` = Kbps
- Data is from the last complete interval (e.g., 11:04 shows 10:55-11:00)
