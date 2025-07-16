# Configuration

The Meraki Dashboard Exporter is configured entirely through environment variables. This guide covers all available configuration options.

## Required Configuration

### API Key

The only required configuration is your Meraki API key:

```bash
MERAKI_API_KEY=your_api_key_here
```

!!! warning "API Key Security"
    Never commit your API key to version control. Use environment variables or secrets management.

## Configuration Options

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_API_KEY` | *Required* | Your Meraki Dashboard API key |
| `MERAKI_EXPORTER_ORG_ID` | *None* | Specific organization ID to monitor (monitors all orgs if not set) |
| `MERAKI_EXPORTER_PORT` | `9099` | Port for the metrics endpoint |
| `MERAKI_EXPORTER_HOST` | `0.0.0.0` | Host to bind the metrics server |

### API Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_EXPORTER_API_BASE_URL` | `https://api.meraki.com/api/v1` | API base URL for regional endpoints |
| `MERAKI_EXPORTER_API_TIMEOUT` | `30` | API request timeout in seconds |
| `MERAKI_EXPORTER_API_MAX_RETRIES` | `4` | Maximum number of API retry attempts |

#### Regional API Endpoints

For users in specific regions, configure the appropriate API base URL:

- **Global/Default**: `https://api.meraki.com/api/v1`
- **Canada**: `https://api.meraki.ca/api/v1`
- **China**: `https://api.meraki.cn/api/v1`
- **India**: `https://api.meraki.in/api/v1`
- **US Federal**: `https://api.gov-meraki.com/api/v1`

Example:
```bash
export MERAKI_EXPORTER_API_BASE_URL="https://api.meraki.ca/api/v1"
```

### Update Intervals

The exporter uses a three-tier update system to optimize API usage:

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `MERAKI_EXPORTER_FAST_UPDATE_INTERVAL` | `60` | 30-300 | Fast tier (sensor data) |
| `MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL` | `300` | 300-1800 | Medium tier (device/org metrics) |
| `MERAKI_EXPORTER_SLOW_UPDATE_INTERVAL` | `900` | 600-3600 | Slow tier (configuration) |

!!! info "Update Tiers"
    - **Fast**: Real-time data like sensor readings
    - **Medium**: Standard metrics aligned with Meraki's 5-minute data blocks
    - **Slow**: Configuration and slowly changing data

### Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_EXPORTER_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MERAKI_EXPORTER_LOG_FORMAT` | `json` | Log format: `json` or `console` |

### OpenTelemetry Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_EXPORTER_OTEL_ENABLED` | `false` | Enable OpenTelemetry export |
| `MERAKI_EXPORTER_OTEL_ENDPOINT` | *None* | OTLP endpoint (e.g., `http://localhost:4317`) |
| `MERAKI_EXPORTER_OTEL_SERVICE_NAME` | `meraki-dashboard-exporter` | Service name for telemetry |
| `MERAKI_EXPORTER_OTEL_HEADERS` | *None* | Headers for OTLP endpoint (format: `key=value,key2=value2`) |
| `MERAKI_EXPORTER_OTEL_INSECURE` | `true` | Use insecure connection for OTLP |

## Configuration Examples

### Basic Configuration

```bash
# .env file
MERAKI_API_KEY=your_api_key_here
MERAKI_EXPORTER_LOG_LEVEL=INFO
```

### Single Organization Monitoring

```bash
# Monitor a specific organization
MERAKI_API_KEY=your_api_key_here
MERAKI_EXPORTER_ORG_ID=123456
MERAKI_EXPORTER_LOG_LEVEL=INFO
```

### High-Frequency Sensor Monitoring

```bash
# Faster sensor updates for critical environments
MERAKI_API_KEY=your_api_key_here
MERAKI_EXPORTER_FAST_UPDATE_INTERVAL=30
MERAKI_EXPORTER_LOG_LEVEL=INFO
```

### OpenTelemetry Integration

```bash
# Send metrics to OTLP collector
MERAKI_API_KEY=your_api_key_here
MERAKI_EXPORTER_OTEL_ENABLED=true
MERAKI_EXPORTER_OTEL_ENDPOINT=http://otel-collector:4317
MERAKI_EXPORTER_OTEL_SERVICE_NAME=meraki-prod
```

### Debug Configuration

```bash
# Verbose logging for troubleshooting
MERAKI_API_KEY=your_api_key_here
MERAKI_EXPORTER_LOG_LEVEL=DEBUG
MERAKI_EXPORTER_LOG_FORMAT=console
```

## Docker Compose Example

```yaml
services:
  meraki-exporter:
    image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
    environment:
      # Core settings
      - MERAKI_API_KEY=${MERAKI_API_KEY}
      - MERAKI_EXPORTER_ORG_ID=${ORG_ID:-}

      # API settings
      - MERAKI_EXPORTER_API_TIMEOUT=60
      - MERAKI_EXPORTER_API_MAX_RETRIES=5

      # Update intervals
      - MERAKI_EXPORTER_FAST_UPDATE_INTERVAL=60
      - MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL=300
      - MERAKI_EXPORTER_SLOW_UPDATE_INTERVAL=900

      # Logging
      - MERAKI_EXPORTER_LOG_LEVEL=INFO

      # OpenTelemetry
      - MERAKI_EXPORTER_OTEL_ENABLED=true
      - MERAKI_EXPORTER_OTEL_ENDPOINT=http://otel-collector:4317
```

## Environment File Template

Create a `.env` file from the template:

```bash
# Required
MERAKI_API_KEY=

# Optional: Organization
MERAKI_EXPORTER_ORG_ID=

# Optional: API Configuration
MERAKI_EXPORTER_API_BASE_URL=https://api.meraki.com/api/v1
MERAKI_EXPORTER_API_TIMEOUT=30
MERAKI_EXPORTER_API_MAX_RETRIES=4

# Optional: Update Intervals
MERAKI_EXPORTER_FAST_UPDATE_INTERVAL=60
MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL=300
MERAKI_EXPORTER_SLOW_UPDATE_INTERVAL=900

# Optional: Logging
MERAKI_EXPORTER_LOG_LEVEL=INFO
MERAKI_EXPORTER_LOG_FORMAT=json

# Optional: OpenTelemetry
MERAKI_EXPORTER_OTEL_ENABLED=false
MERAKI_EXPORTER_OTEL_ENDPOINT=
MERAKI_EXPORTER_OTEL_SERVICE_NAME=meraki-dashboard-exporter
```

## Best Practices

1. **Use Environment Files**: Keep configuration in `.env` files (don't commit them)
2. **Start with Defaults**: The default intervals are optimized for most use cases
3. **Monitor API Usage**: Use DEBUG logging initially to understand API call patterns
4. **Regional Endpoints**: Use the closest regional endpoint for better performance
5. **Secrets Management**: In production, use proper secrets management (Kubernetes secrets, AWS Secrets Manager, etc.)

## Next Steps

- Follow the [Quick Start guide](quickstart.md) to begin collecting metrics
- Learn about [available metrics](../metrics/overview.md)
- Set up [Prometheus integration](../integration/prometheus.md)
