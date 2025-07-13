# Meraki Dashboard Exporter
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter?ref=badge_shield)


A Prometheus exporter for Cisco Meraki Dashboard API metrics with OpenTelemetry support.

## Features

- Collects metrics from all Meraki device types (MS, MR, MV, MT, MX, MG)
- Organization-level metrics (API usage, licenses, device counts)
- Device-specific metrics (status, performance, sensor readings)
- Async collection for improved performance
- OpenTelemetry support for metrics and logs
- Structured logging with JSON output
- Docker support with health checks
- Configurable collection intervals

## Quick Start

### Using Docker

1. Copy `.env.example` to `.env` and add your Meraki API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your MERAKI_API_KEY
   ```

2. Run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

3. Access metrics at http://localhost:9099/metrics

### Using Python

1. Install dependencies:
   ```bash
   uv pip install -e .
   ```

2. Set environment variables:
   ```bash
   export MERAKI_API_KEY=your_api_key_here
   ```

3. Run the exporter:
   ```bash
   python -m meraki_dashboard_exporter
   ```

## Configuration

All configuration is done via environment variables. See `.env.example` for all available options.

Key settings:
- `MERAKI_API_KEY`: Your Meraki Dashboard API key (required)
- `MERAKI_EXPORTER_ORG_ID`: Specific org ID to monitor (optional)
- `MERAKI_EXPORTER_LOG_LEVEL`: Logging level (default: INFO)

## Metrics

### Organization Metrics
- `meraki_org_api_requests_total`: Total API requests
- `meraki_org_networks_total`: Number of networks
- `meraki_org_devices_total`: Number of devices by type
- `meraki_org_licenses_total`: License counts by type and status

### Device Metrics
- `meraki_device_up`: Device online status
- `meraki_device_uptime_seconds`: Device uptime

### Switch (MS) Metrics
- `meraki_ms_port_status`: Port connection status
- `meraki_ms_port_traffic_bytes`: Port traffic counters
- `meraki_ms_port_errors_total`: Port error counters

### Access Point (MR) Metrics
- `meraki_mr_clients_connected`: Connected client count
- `meraki_ap_channel_utilization_*`: Channel utilization metrics

### Sensor (MT) Metrics
- `meraki_mt_temperature_celsius`: Temperature readings
- `meraki_mt_humidity_percent`: Humidity readings
- `meraki_mt_door_status`: Door sensor status
- `meraki_mt_water_detected`: Water detection status
- And more...

### Alert Metrics
- `meraki_alerts_active`: Number of active alerts by type, category, severity, and device type
- `meraki_alerts_total_by_severity`: Total alerts grouped by severity level
- `meraki_alerts_total_by_network`: Total alerts per network

## Development

### Running Tests
```bash
uv run pytest
```

### Linting and Type Checking
```bash
uv run ruff check .
uv run mypy .
```

## License

MIT


[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter.svg?type=large)](https://app.fossa.com/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter?ref=badge_large)
