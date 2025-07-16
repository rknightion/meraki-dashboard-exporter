# Device Metrics

Device metrics provide detailed insights into the status and performance of all Meraki device types including switches (MS), access points (MR), security appliances (MX), cameras (MV), sensors (MT), and cellular gateways (MG).

## Common Device Metrics

These metrics are available for all device types:

### Device Status

#### `meraki_device_up`
- **Type**: Gauge
- **Description**: Device online status (1 = online, 0 = offline)
- **Labels**: `org_id`, `org_name`, `network_id`, `network_name`, `device_serial`, `device_name`, `device_model`
- **Update**: Medium tier (5 minutes)

Example queries:
```promql
# Count online devices by model
sum by (device_model) (meraki_device_up)

# Device availability percentage
avg by (network_name) (meraki_device_up) * 100

# Offline devices
meraki_device_up == 0
```

### Device Information

#### `meraki_device_info`
- **Type**: Info
- **Description**: Device metadata and configuration
- **Labels**: `device_serial`, `device_name`, `device_model`, `network_id`
- **Info Labels**: `mac`, `firmware`, `url`, `address`, `lat`, `lng`

## Switch Metrics (MS)

### Port Status Metrics

#### `meraki_ms_port_status`
- **Type**: Gauge
- **Description**: Port connection status (1 = connected, 0 = disconnected)
- **Labels**: `device_serial`, `device_name`, `port_id`, `enabled`
- **Update**: Medium tier (5 minutes)

#### `meraki_ms_port_traffic_bytes`
- **Type**: Gauge
- **Description**: Port traffic in bytes
- **Labels**: `device_serial`, `device_name`, `port_id`, `direction` (sent/received)
- **Update**: Medium tier (5 minutes)

#### `meraki_ms_port_errors_total`
- **Type**: Gauge
- **Description**: Port error counts
- **Labels**: `device_serial`, `device_name`, `port_id`, `error_type` (crc/collisions)
- **Update**: Medium tier (5 minutes)

Example queries:
```promql
# Ports with high error rates
rate(meraki_ms_port_errors_total[5m]) > 0

# Port utilization (assuming 1Gbps ports)
rate(meraki_ms_port_traffic_bytes[5m]) * 8 / 1e9 * 100

# Count of active ports per switch
sum by (device_name) (meraki_ms_port_status)
```

### Power over Ethernet (PoE) Metrics

#### `meraki_ms_port_poe_usage_watts`
- **Type**: Gauge
- **Description**: PoE power consumption per port in watts
- **Labels**: `device_serial`, `device_name`, `port_id`
- **Update**: Medium tier (5 minutes)

#### `meraki_switch_total_power_watts`
- **Type**: Gauge
- **Description**: Total PoE power consumption for the switch
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Medium tier (5 minutes)

!!! info "PoE Monitoring"
    PoE metrics are only available for switches with PoE capability. The total power is calculated by summing all port PoE consumption.

## Access Point Metrics (MR)

### Client Metrics

#### `meraki_mr_clients_connected`
- **Type**: Gauge
- **Description**: Number of connected wireless clients
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Medium tier (5 minutes)

### Channel Utilization

#### `meraki_ap_channel_utilization_2_4ghz_percent`
- **Type**: Gauge
- **Description**: 2.4GHz band channel utilization percentage (includes WiFi and non-WiFi interference)
- **Labels**: `network_id`, `network_name`, `device_serial`, `device_name`
- **Update**: Medium tier (5 minutes)

#### `meraki_ap_channel_utilization_5ghz_percent`
- **Type**: Gauge
- **Description**: 5GHz band channel utilization percentage
- **Labels**: `network_id`, `network_name`, `device_serial`, `device_name`
- **Update**: Medium tier (5 minutes)

### Wireless Performance

#### `meraki_network_wireless_connection_success_percent`
- **Type**: Gauge
- **Description**: Wireless connection success rate by stage
- **Labels**: `network_id`, `network_name`, `connection_step` (assoc/auth/dhcp/dns/success)
- **Update**: Medium tier (5 minutes)

#### `meraki_network_wireless_data_rate_kbps`
- **Type**: Gauge
- **Description**: Average wireless data rate
- **Labels**: `network_id`, `network_name`, `direction` (download/upload)
- **Update**: Medium tier (5 minutes)

Example queries:
```promql
# APs with high channel utilization
meraki_ap_channel_utilization_5ghz_percent > 80

# Wireless connection success rate
meraki_network_wireless_connection_success_percent{connection_step="success"}

# Client density per AP
topk(10, meraki_mr_clients_connected)
```

## Sensor Metrics (MT)

### Environmental Sensors

#### `meraki_mt_temperature_celsius`
- **Type**: Gauge
- **Description**: Temperature reading in Celsius
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

#### `meraki_mt_humidity_percent`
- **Type**: Gauge
- **Description**: Relative humidity percentage
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

#### `meraki_mt_tvoc_ppb`
- **Type**: Gauge
- **Description**: Total Volatile Organic Compounds in parts per billion
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

#### `meraki_mt_pm25_micrograms_per_m3`
- **Type**: Gauge
- **Description**: PM2.5 particulate matter concentration
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

#### `meraki_mt_noise_db`
- **Type**: Gauge
- **Description**: Ambient noise level in decibels
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

### Physical Security Sensors

#### `meraki_mt_door_status`
- **Type**: Gauge
- **Description**: Door sensor status (1 = open, 0 = closed)
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

#### `meraki_mt_water_detected`
- **Type**: Gauge
- **Description**: Water detection status (1 = water detected, 0 = dry)
- **Labels**: `device_serial`, `device_name`, `network_id`, `network_name`
- **Update**: Fast tier (60 seconds)

Example queries:
```promql
# Temperature out of range
meraki_mt_temperature_celsius > 30 or meraki_mt_temperature_celsius < 10

# Humidity alerts
meraki_mt_humidity_percent > 70 or meraki_mt_humidity_percent < 30

# Door open for extended period
meraki_mt_door_status == 1
```

## Bluetooth Metrics

#### `meraki_network_bluetooth_clients_total`
- **Type**: Gauge
- **Description**: Total Bluetooth clients detected by MR devices
- **Labels**: `network_id`, `network_name`
- **Update**: Medium tier (5 minutes)

## Example Alerting Rules

### Device Down Alert
```yaml
groups:
  - name: meraki_devices
    rules:
      - alert: MerakiDeviceDown
        expr: meraki_device_up == 0
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Meraki device offline"
          description: "{{ $labels.device_name }} ({{ $labels.device_serial }}) has been offline for 10 minutes"
```

### High Temperature Alert
```yaml
groups:
  - name: meraki_sensors
    rules:
      - alert: HighTemperature
        expr: meraki_mt_temperature_celsius > 30
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High temperature detected"
          description: "{{ $labels.device_name }} is reporting {{ $value }}°C"
```

### Port Errors Alert
```yaml
groups:
  - name: meraki_switches
    rules:
      - alert: HighPortErrors
        expr: rate(meraki_ms_port_errors_total[5m]) > 1
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "High port error rate"
          description: "Port {{ $labels.port_id }} on {{ $labels.device_name }} has {{ $value }} errors per second"
```

## Grafana Dashboard Examples

### Device Status Panel
```json
{
  "targets": [{
    "expr": "sum by (device_model) (meraki_device_up)",
    "legendFormat": "{{ device_model }}"
  }],
  "title": "Online Devices by Model",
  "type": "stat"
}
```

### Temperature Heatmap
```json
{
  "targets": [{
    "expr": "meraki_mt_temperature_celsius",
    "legendFormat": "{{ device_name }}"
  }],
  "title": "Temperature Readings",
  "type": "heatmap",
  "dataFormat": "timeseries"
}
```

### Switch Port Utilization
```json
{
  "targets": [{
    "expr": "rate(meraki_ms_port_traffic_bytes{direction=\"received\"}[5m]) * 8",
    "legendFormat": "{{ device_name }} - Port {{ port_id }}"
  }],
  "title": "Port Traffic (bits/sec)",
  "type": "timeseries"
}
```

## Performance Considerations

### Metric Cardinality
- Port metrics can create high cardinality with many switches
- Consider aggregating at the device level for large deployments
- Use recording rules for frequently-queried aggregations

### Collection Optimization
- Fast tier (sensors) runs every 60 seconds
- Medium tier (devices) runs every 5 minutes
- Adjust intervals based on your monitoring needs

### API Efficiency
- Device metrics are collected in bulk per organization
- Port statistics require individual API calls per switch
- Sensor readings use the latest readings endpoint
