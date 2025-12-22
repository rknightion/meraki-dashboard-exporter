# Meraki Dashboard Exporter
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter?ref=badge_shield)


A Prometheus exporter for Cisco Meraki Dashboard API metrics with OpenTelemetry support.

## Features

### Core Capabilities
- **Complete device coverage**: Collects metrics from all Meraki device types (MS, MR, MV, MT, MX, MG)
- **Organization-level metrics**: API usage, licenses, device counts, network health alerts
- **Device-specific metrics**: Status, performance, sensor readings, port statistics
- **Webhook receiver**: Real-time event processing from Meraki Dashboard alerts
- **Client tracking**: Optional DNS-enhanced client identification and monitoring (disabled by default)
- **Cardinality monitoring**: Built-in `/cardinality` UI and `/api/metrics/cardinality` JSON API

### Performance & Reliability
- **High-performance collection**: Parallel organization processing with bounded concurrency
- **Shared inventory caching**: Reduces duplicate org/network/device lookups with tier-aware TTLs
- **Automatic metric expiration**: Prevents stale metrics for offline/removed devices
- **Retry-aware API client**: Exponential backoff on rate limits with per-endpoint latency metrics

### Observability
- **Dual metric export**: Prometheus `/metrics` endpoint + automatic OpenTelemetry export
- **Distributed tracing**: Full request tracing with OpenTelemetry instrumentation
- **Structured logging**: logfmt output with trace correlation and contextual information
- **Cardinality monitoring**: Built-in tracking and warning metrics for metric growth
- **Health monitoring**: Collector health metrics with success rates, failure streaks, and last success timestamps

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
   docker compose up -d
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

See [docs/observability/otel.md](docs/observability/otel.md) for detailed OpenTelemetry configuration and [docs/observability/tracing.md](docs/observability/tracing.md) for distributed tracing documentation.

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
- `MERAKI_EXPORTER_API__MAX_RETRIES`: Maximum API request retries (default: 3)
- `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT`: Max parallel collector/org work (default: 5)
- `MERAKI_EXPORTER_API__BATCH_SIZE`: Default batch size for API operations (default: 20)
- `MERAKI_EXPORTER_CLIENTS__ENABLED`: Enable client collector and DNS resolution (default: false)
- `MERAKI_EXPORTER_WEBHOOKS__ENABLED`: Enable Meraki webhook receiver (default: false)

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

- **Organization & license metrics**: API usage, device/network counts, licenses, configuration, and alerts
- **Device metrics**: Availability, status info, switch port health (including per-second error rates), AP performance, camera/sensor readings, and gateway connectivity
- **Network health metrics**: RF/channel utilization, connection stats, Bluetooth sightings, and data rates
- **Client metrics (optional)**: Per-client status and usage when `MERAKI_EXPORTER_CLIENTS__ENABLED=true`
- **Webhook metrics (optional)**: Event counts, validation failures, and processing duration for `POST /api/webhooks/meraki`
- **Infrastructure metrics**: Collector duration/error counts, parallel collection activity, API latency/counters, inventory cache hits/misses/size, and metric expiration tracking
- **Cardinality monitoring**: `/cardinality` HTML report and `/api/metrics/cardinality` JSON API for top-k series growth

See the generated [metrics reference](https://m7kni.io/meraki-dashboard-exporter/metrics/metrics/) for the authoritative metric list (kept in sync via `uv run python scripts/generate_metrics_docs.py`).

## Performance

- **Bounded concurrency**: ManagedTaskGroup keeps parallel collectors/orgs within `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT`
- **Tiered scheduling**: FAST/MEDIUM/SLOW tiers align with data volatility (60s/300s/900s by default)
- **Inventory caching**: Organization/network/device lookups cached per tier with TTL to reduce duplicate API calls
- **Batch controls**: Tunable batch sizes and delays (`MERAKI_EXPORTER_API__*BATCH_SIZE`, `MERAKI_EXPORTER_API__BATCH_DELAY`)
- **Metric lifecycle**: Automatic expiration cleans up stale series when devices disappear or go offline

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
