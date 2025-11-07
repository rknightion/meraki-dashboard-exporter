# Meraki Dashboard Exporter
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter?ref=badge_shield)


A Prometheus exporter for Cisco Meraki Dashboard API metrics with OpenTelemetry support.

## Features

### Core Capabilities
- **Complete device coverage**: Collects metrics from all Meraki device types (MS, MR, MV, MT, MX, MG)
- **Organization-level metrics**: API usage, licenses, device counts, network health alerts
- **Device-specific metrics**: Status, performance, sensor readings, port statistics
- **Webhook receiver**: Real-time event processing from Meraki Dashboard alerts
- **Client tracking**: Optional DNS-enhanced client identification and monitoring

### Performance & Reliability
- **High-performance collection**: Parallel organization processing with bounded concurrency
- **Shared inventory caching**: 30-50% reduction in API calls through intelligent caching
- **Automatic metric expiration**: Prevents stale metrics for offline/removed devices
- **Circuit breaker protection**: Graceful handling of API failures and rate limits
- **Enhanced retry logic**: Exponential backoff with configurable retry strategies

### Observability
- **Dual metric export**: Prometheus `/metrics` endpoint + automatic OpenTelemetry export
- **Distributed tracing**: Full request tracing with OpenTelemetry instrumentation
- **Structured logging**: JSON output with trace correlation and contextual information
- **Cardinality monitoring**: Built-in tracking and alerting for metric growth
- **Health monitoring**: Collector health metrics with success rates and failure tracking

### Deployment
- Docker support with health checks and multi-stage builds
- Configurable collection intervals (fast/medium/slow tiers)
- Environment-based configuration with validation
- Regional API endpoint support

## Quick Start

### Using Docker (Recommended)

1. Copy `.env.example` to `.env` and add your Meraki API key:
   ```bash
   cp .env.example .env
   # Edit .env and set: MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here
   ```

2. Run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

3. Access metrics at http://localhost:9099/metrics

### Building from Source

If you need to build the Docker image from source:

```bash
# Build the image
docker build -t meraki-dashboard-exporter .

# Run the container
docker run -d \
  -e MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here \
  -p 9099:9099 \
  meraki-dashboard-exporter
```

## OpenTelemetry Support

The exporter provides comprehensive OpenTelemetry support when enabled:

**Metrics**: All Prometheus metrics are automatically mirrored to OTEL
- Use existing Prometheus dashboards while sending to OTEL backends
- No code changes needed - new metrics are automatically exported

**Tracing**: Distributed tracing for all operations
- Every Meraki API call is traced with timing and metadata
- Automatic instrumentation of HTTP, threading, and logging
- Configurable sampling rates for production use
- Correlation with logs via trace IDs
- **Automatic RED metrics** from spans (Rate, Errors, Duration)

**Logs**: Structured logging with trace correlation
- Automatic trace context injection (trace_id, span_id)
- All logs include trace context when within a span
- Structured log fields preserved for easy parsing
- Compatible with log aggregation systems

**Benefits**:
- Full observability with metrics, traces, and logs
- Debug slow API calls and identify bottlenecks
- Track request flow across the entire system
- Compatible with Jaeger, Tempo, Datadog, New Relic, etc.

### Enabling OpenTelemetry

Set these environment variables:

```bash
# Enable OTEL export
export MERAKI_EXPORTER_OTEL__ENABLED=true

# Set the OTEL collector endpoint
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional: Configure export interval (default: 60 seconds)
export MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL=30

# Optional: Add resource attributes
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"environment":"production","region":"us-east"}'

# Optional: Configure trace sampling rate (default: 0.1 = 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

### Docker Compose Example

```yaml
services:
  meraki-exporter:
    image: meraki-dashboard-exporter
    environment:
      - MERAKI_EXPORTER_MERAKI__API_KEY=${MERAKI_EXPORTER_MERAKI__API_KEY}
      - MERAKI_EXPORTER_OTEL__ENABLED=true
      - MERAKI_EXPORTER_OTEL__ENDPOINT=http://otel-collector:4317
    ports:
      - "9099:9099"

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"  # OTLP gRPC receiver
```

See [OTEL.md](OTEL.md) for detailed OpenTelemetry configuration and [TRACING.md](TRACING.md) for distributed tracing documentation.

## Webhook Support

The exporter can receive real-time webhook events from Meraki Dashboard, providing immediate notification of alerts, configuration changes, and other events.

### Enabling Webhooks

```bash
# Enable webhook receiver
export MERAKI_EXPORTER_WEBHOOKS__ENABLED=true

# Set shared secret for validation (recommended)
export MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET=your_secret_here

# Optional: Require secret validation (default: true)
export MERAKI_EXPORTER_WEBHOOKS__REQUIRE_SECRET=true

# Optional: Maximum payload size in bytes (default: 1MB)
export MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE=1048576
```

### Configuring Meraki Dashboard

1. Navigate to **Network-wide > Configure > Alerts**
2. Add a webhook receiver pointing to: `http://your-exporter:9099/api/webhooks/meraki`
3. Set the shared secret to match your configuration
4. Select which alert types to send

### Webhook Metrics

- `meraki_webhook_events_received_total`: Total webhook events received by org and alert type
- `meraki_webhook_events_processed_total`: Successfully processed webhook events
- `meraki_webhook_events_failed_total`: Failed webhook event processing
- `meraki_webhook_processing_duration_seconds`: Time spent processing webhook events
- `meraki_webhook_validation_failures_total`: Validation failures by error type

## Configuration

All configuration is done via environment variables. See `.env.example` for all available options.

### Key Settings

#### Required
- `MERAKI_EXPORTER_MERAKI__API_KEY`: Your Meraki Dashboard API key

#### Optional
- `MERAKI_EXPORTER_MERAKI__ORG_ID`: Specific org ID to monitor (monitors all orgs if not set)
- `MERAKI_EXPORTER_LOGGING__LEVEL`: Logging level (default: INFO)
- `MERAKI_EXPORTER_MERAKI__API_BASE_URL`: API base URL for regional endpoints (default: https://api.meraki.com/api/v1)
- `MERAKI_EXPORTER_API__TIMEOUT`: API request timeout in seconds (default: 30)
- `MERAKI_EXPORTER_API__MAX_RETRIES`: Maximum API request retries (default: 4)

### Update Intervals
- `MERAKI_EXPORTER_UPDATE_INTERVALS__FAST`: Fast tier interval in seconds (default: 60, range: 30-300)
- `MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM`: Medium tier interval in seconds (default: 300, range: 300-1800)
- `MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW`: Slow tier interval in seconds (default: 900, range: 600-3600)

### Regional API Endpoints

For users in specific regions, use the appropriate API base URL:

- **Global/Default**: `https://api.meraki.com/api/v1`
- **Canada**: `https://api.meraki.ca/api/v1`
- **China**: `https://api.meraki.cn/api/v1`
- **India**: `https://api.meraki.in/api/v1`
- **US Federal**: `https://api.gov-meraki.com/api/v1`

Example:
```bash
export MERAKI_EXPORTER_MERAKI__API_BASE_URL="https://api.meraki.ca/api/v1"  # For Canada region
```

## Metrics

### Organization Metrics
- `meraki_org_api_requests_total`: Total API requests
- `meraki_org_networks_total`: Number of networks
- `meraki_org_devices_total`: Number of devices by type
- `meraki_org_licenses_total`: License counts by type and status
- `meraki_org_clients_total`: Total active clients (5-minute window)
- `meraki_org_usage_total_kb`: Total data usage in KB (5-minute window)
- `meraki_org_usage_downstream_kb`: Downstream data usage in KB (5-minute window)
- `meraki_org_usage_upstream_kb`: Upstream data usage in KB (5-minute window)

### Device Metrics
- `meraki_device_up`: Device online status
- `meraki_device_uptime_seconds`: Device uptime

### Switch (MS) Metrics
**Port Status & Traffic:**
- `meraki_ms_port_status`: Port connection status with speed and duplex
- `meraki_ms_port_traffic_bytes`: Port traffic rate in bytes/sec (rx/tx)
- `meraki_ms_port_usage_bytes`: Total data usage over 1-hour window
- `meraki_ms_port_client_count`: Number of connected clients per port

**Port Error Metrics (5-minute window):**
- `meraki_ms_port_packets_crcerrors`: CRC align error packets (count + rate)
- `meraki_ms_port_packets_fragments`: Fragment packets (count + rate)
- `meraki_ms_port_packets_collisions`: Collision packets (count + rate)
- `meraki_ms_port_packets_topologychanges`: STP topology changes (count + rate)
- `meraki_ms_port_packets_broadcast`: Broadcast packets (count + rate)
- `meraki_ms_port_packets_multicast`: Multicast packets (count + rate)
- `meraki_ms_port_packets_total`: Total packets (count + rate)

**PoE Metrics:**
- `meraki_ms_poe_port_power_watts`: Per-port PoE power consumption
- `meraki_ms_poe_total_power_watts`: Total switch PoE consumption
- `meraki_ms_poe_network_total_watts`: Network-wide PoE consumption
- `meraki_ms_power_usage_watts`: Switch power usage

**STP Metrics:**
- `meraki_ms_stp_priority`: Spanning Tree Protocol priority per switch

### Access Point (MR) Metrics
- `meraki_mr_clients_connected`: Connected client count
- `meraki_ap_channel_utilization_*`: Channel utilization metrics
- `meraki_network_bluetooth_clients_total`: Bluetooth clients detected by MR devices

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

### Configuration Metrics
- `meraki_org_login_security_*`: Various login security settings (see config collector for full list)
- `meraki_org_configuration_changes_total`: Total configuration changes in the last 24 hours

### Observability Metrics (Auto-generated)
When OpenTelemetry tracing is enabled, these metrics are automatically generated from spans:
- `meraki_span_requests_total`: Request rate by operation, collector, endpoint, and status
- `meraki_span_duration_seconds`: Request duration histogram by operation
- `meraki_span_errors_total`: Error rate by operation, collector, endpoint, and error type
- `meraki_sli_*`: Service Level Indicator metrics for availability, latency, and error rates

### Collector Infrastructure Metrics
**Performance Monitoring:**
- `meraki_parallel_collections_active`: Active parallel collections per collector/tier
- `meraki_collection_errors_total`: Collection errors by collector/tier/error_type
- `meraki_collector_duration_seconds`: Time taken for each collection run
- `meraki_collector_last_success_timestamp`: Last successful collection timestamp

**Inventory Cache:**
- `meraki_inventory_cache_hits_total`: Cache hit count for org/device/network lookups
- `meraki_inventory_cache_misses_total`: Cache miss count requiring API calls
- `meraki_inventory_cache_size`: Current number of cached items

**Metric Expiration:**
- `meraki_metric_expirations_total`: Metrics expired due to device removal/offline status
- `meraki_metric_expiration_errors_total`: Errors during metric expiration processing

### Cardinality Monitoring
The exporter includes built-in cardinality monitoring to help track metric growth:
- `meraki_metric_cardinality_total`: Total unique label combinations per metric
- `meraki_label_cardinality_total`: Cardinality per label per metric
- `meraki_cardinality_warnings_total`: Warnings when metrics exceed thresholds
- `meraki_total_series`: Total time series count across all metrics

Access cardinality report at: `/cardinality`

### Circuit Breaker Metrics
The exporter includes circuit breaker metrics for monitoring reliability:
- `meraki_circuit_breaker_state`: Current state of circuit breakers (closed/open/half_open)
- `meraki_circuit_breaker_failures_total`: Total failures handled by circuit breakers
- `meraki_circuit_breaker_success_total`: Successful calls through circuit breakers
- `meraki_circuit_breaker_rejections_total`: Calls rejected by open circuit breakers
- `meraki_circuit_breaker_state_changes_total`: State transitions tracked by from/to state

## Performance

The exporter is optimized for large Meraki deployments:

- **Parallel Organization Processing**: Collects from multiple organizations concurrently with bounded concurrency
- **Shared Inventory Caching**: Reduces API calls by 30-50% through intelligent caching (5-30 minute TTLs)
- **Automatic Metric Expiration**: Prevents stale metrics by tracking and expiring metrics for offline/removed devices
- **Tiered Collection Intervals**: Different update frequencies based on data volatility (60s/300s/900s)
- **Configurable Batch Sizes**: Optimized batch sizes for device, network, and client operations (20-30 per batch)
- **Enhanced API Client**: Exponential backoff, retry logic, and circuit breaker protection

**Typical Performance** (single organization, 100+ devices):
- Initial collection: ~30-60 seconds
- Subsequent collections: ~10-20 seconds (with caching)
- API calls per collection cycle: ~50-100 (vs 150-200 without caching)

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
