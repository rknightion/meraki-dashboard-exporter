# Meraki Dashboard Exporter
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Frknightion%2Fmeraki-dashboard-exporter?ref=badge_shield)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/rknightion/meraki-dashboard-exporter/badge)](https://scorecard.dev/viewer/?uri=github.com/rknightion/meraki-dashboard-exporter)

> [!WARNING]
> I no longer have access to a Meraki network with anything other than MT, MR & MS devices. Changes affecting other device types (MX, MG, MV) are best-effort and driven from publicly available API documentation and SDK references rather than tested against live hardware.
> If you are willing to work with myself to boost support for other device types or add coverage please reach out! See the [Support Matrix](docs/support-matrix.md) for exactly what is collected per product line.

A Prometheus exporter for Cisco Meraki Dashboard API metrics with OpenTelemetry tracing support.

## Features

### Core Capabilities
- **Complete device coverage**: Collects metrics from all Meraki device types (MS, MR, MV, MT, MX, MG)
- **Organization-level metrics**: API usage, licenses, device counts, network health alerts
- **Device-specific metrics**: Status, performance, sensor readings, port statistics
- **Webhook receiver**: Real-time event processing from Meraki Dashboard alerts
- **Client tracking**: Optional DNS-enhanced client identification and monitoring (disabled by default)
- **Network filtering**: Restrict scraping to specific networks by name glob, ID, or tag (inactive by default)
- **Status dashboard**: Built-in `/status` health UI alongside `/cardinality` UI and `/api/metrics/cardinality` JSON API

### Performance & Reliability
- **High-performance collection**: Parallel organization processing with bounded concurrency
- **Shared inventory caching**: Reduces duplicate org/network/device lookups with tier-aware TTLs
- **Automatic metric expiration**: Prevents stale metrics for offline/removed devices
- **Retry-aware API client**: Exponential backoff on rate limits with per-endpoint latency metrics

### Observability
- **Prometheus metrics**: `/metrics` endpoint for scraping
- **Distributed tracing**: Full request tracing with OpenTelemetry instrumentation
- **Structured logging**: logfmt output with trace correlation and contextual information
- **Cardinality monitoring**: Built-in tracking and warning metrics for metric growth
- **Health monitoring**: `/health` and `/ready` probes plus a `/status` HTML dashboard summarising collector success rates, failure streaks, and last success timestamps

### Deployment
- Docker support with health checks and multi-stage builds
- Adaptive, budget-aware collection scheduling (per-endpoint-group solved intervals, no fixed tiers)
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

> [!NOTE]
> A locally-built image reports its version as `0.0.0+dev` (and commit `unknown`)
> on `/status`, the web UI, and `meraki_exporter_build_info`. Real version/commit
> values are baked in only by CI-published images (via the `APP_VERSION` /
> `GIT_COMMIT` build-args); pass `--build-arg APP_VERSION=<v> --build-arg GIT_COMMIT=<sha>`
> to `docker build` if you want them on a local build.
>
> The bundled `docker-compose.yml` healthcheck polls `/health`, which includes a
> dead-man switch: it returns 503 (marking the container unhealthy) if no
> collector has completed a successful run within the staleness threshold, so a
> wedged exporter is restarted rather than left serving stale metrics.

### Using Helm (Kubernetes)

A Helm chart is published to the GHCR OCI registry alongside every release, from
[`charts/meraki-dashboard-exporter`](charts/meraki-dashboard-exporter):

```bash
helm install meraki-dashboard-exporter \
  oci://ghcr.io/rknightion/charts/meraki-dashboard-exporter \
  --version <exporter-version> \
  --set meraki.apiKey=your_api_key_here
```

Replace `<exporter-version>` with a [released version](https://github.com/rknightion/meraki-dashboard-exporter/releases)
(chart versions track exporter releases, e.g. `0.31.0`), or use an `existingSecret` instead of
`meraki.apiKey` for production. See
[`values.yaml`](charts/meraki-dashboard-exporter/values.yaml) for all configurable settings and
[the chart's `CLAUDE.md`](charts/meraki-dashboard-exporter/CLAUDE.md) for implementation notes. An
edge chart tracking `main` is also published on every push, versioned `0.0.0-main.*`.

## OpenTelemetry Tracing

The exporter provides OpenTelemetry tracing when enabled:

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
- Prometheus metrics with traces and logs for correlation
- Debug slow API calls and identify bottlenecks
- Track request flow across the entire system
- Compatible with Jaeger, Tempo, Datadog, New Relic, etc.

### Enabling OpenTelemetry

Set these environment variables:

```bash
# Enable OTEL tracing
export MERAKI_EXPORTER_OTEL__ENABLED=true

# Set the OTEL collector endpoint
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

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

The exporter can receive webhook events from Meraki Dashboard. Webhooks accelerate **device-down**
detection only: a `device_down`/`gateway_down` event fast-flips `meraki_device_up=0` ahead of the
next poll. Device recovery/UP and every other metric remain polled at `DeviceCollector`'s own
solved cadence (~300s by default) — there is no whole-device "back online" webhook event to drive
a fast recovery path. See [docs/data-freshness.md](docs/data-freshness.md) for the full staleness
picture and recommended alert `for:` durations.

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
- `MERAKI_EXPORTER_API__VALIDATE_KWARGS`: Enable Meraki SDK kwarg validation warnings (default: false; recommended for dev/CI)
- `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`: Per-run collector timeout budget in seconds (default: 240)
- `MERAKI_EXPORTER_CLIENTS__ENABLED`: Enable client collector and DNS resolution (default: false)
- `MERAKI_EXPORTER_WEBHOOKS__ENABLED`: Enable Meraki webhook receiver (default: false)
- `MERAKI_EXPORTER_SERVER__API_TOKEN`: Optional bearer token guarding the two state-changing control POSTs (`/api/collectors/trigger`, `/api/clients/clear-dns-cache`). When unset (default) those POSTs are unauthenticated and all GET endpoints (`/metrics`, `/status`, `/health`, ...) are always unauthenticated — bind the exporter to a trusted network. See [security.md](docs/security.md#endpoint-authentication).
- Beta / early-access API: the exporter never calls Meraki's beta endpoints and has no opt-in flag (they are unversioned and would undermine the v1 stability promise). It instead surfaces the risk — `meraki_org_has_beta_api` (`1`/`0` per org) plus a WARN log fire when an org is on the beta Dashboard spec, which can silently break assumed-stable collection. Alert on `meraki_org_has_beta_api == 1`. See [security.md](docs/security.md#beta--early-access-api-surface).

### Adaptive Scheduler

There is no fixed FAST/MEDIUM/SLOW tier system. Every API fetch is grouped into an endpoint
group with its own volatility floor, and an adaptive, budget-aware scheduler solves each
group's actual polling interval from organization size and the configured API budget,
automatically stretching lower-priority groups when demand would exceed it. See
[Scheduler Architecture](docs/observability/scheduler.md) for the full mechanism.

- `MERAKI_EXPORTER_SCHEDULER__MODE`: `adaptive` (default) or `fixed` (floors/pins only, no stretching)
- `MERAKI_EXPORTER_SCHEDULER__TARGET_UTILIZATION`: Fraction of the effective budget the solver plans to (default: 0.7)
- `MERAKI_EXPORTER_SCHEDULER__MAX_STRETCH_FACTOR`: Per-group interval cap as a multiple of its floor (default: 4.0)
- `MERAKI_EXPORTER_SCHEDULER__MAX_INTERVAL_SECONDS`: Absolute per-group interval cap (default: 3600)
- `MERAKI_EXPORTER_SCHEDULER__RESOLVE_INTERVAL_SECONDS`: How often the solver recomputes from org shape (default: 900)
- `MERAKI_EXPORTER_SCHEDULER__FAILURE_RETRY_SECONDS`: Minimum spacing between retries of a failing group (default: 300)
- `MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES`: Per-group interval pins as a JSON object, e.g. `{"nh_connection_stats": 900}`
- `MERAKI_EXPORTER_COLLECTORS__MAX_CONCURRENT_COLLECTORS`: Max collectors whose group-clocked loops may run concurrently (default: 5)

### Network Filter

Restrict the exporter to a subset of networks. All fields are optional comma-separated lists; if every field is empty, every network in every configured organisation is scraped (the default).

```bash
# Include only networks whose name matches a glob (case-sensitive)
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_NAMES=prod-*,staging-*

# Or by exact network ID
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_IDS=L_123,L_456

# Or by network tag (any match wins)
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_TAGS=production,critical

# Exclude rules (applied AFTER includes)
MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_NAMES=*-test
MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_IDS=L_999999
MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_TAGS=lab
```

**Semantics.** If any `INCLUDE_*` field is set, a network must match at least one include rule (across name OR id OR tag) to be considered. Then any matching `EXCLUDE_*` rule drops it. Empty resolution at startup fails fast.

**Devices** in excluded networks are not scraped either. **Organization-level** metrics (license counts, API usage) are unaffected.

**Observability.** Live filter state is published as `meraki_network_filter_match{org_id,network_id}` (value 1 if included, 0 if excluded), `meraki_network_filter_resolved{org_id}`, and `meraki_network_filter_total{org_id}` so dashboards and alerts can verify filter scope.

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

## HTTP Endpoints

The exporter exposes `/metrics`, health/readiness probes (`/health`, `/ready`), a
`/status` dashboard, the client and cardinality UIs, and a few control/webhook
POSTs. See the generated [HTTP Endpoints reference](https://m7kni.io/meraki-dashboard-exporter/reference/endpoints/)
for the authoritative list (method, path, and which config flag gates each one),
kept in sync via `uv run python scripts/generate_endpoints_docs.py`.

## Metrics

- **Organization & license metrics**: API usage, device/network counts, licenses, configuration, and alerts
- **Device metrics**: Availability, status info, switch port health (including per-second error rates), AP performance, camera/sensor readings, and gateway connectivity
- **Network health metrics**: RF/channel utilization, connection stats, Bluetooth sightings, and data rates
- **Client metrics (optional)**: Per-client status and usage when `MERAKI_EXPORTER_CLIENTS__ENABLED=true`
- **Webhook metrics (optional)**: Event counts, validation failures, and processing duration for `POST /api/webhooks/meraki`
- **Infrastructure metrics**: Collector duration/error counts, parallel collection activity, API latency/counters, inventory cache hits/misses/size, and metric expiration tracking
- **Cardinality monitoring**: `/cardinality` HTML report and `/api/metrics/cardinality` JSON API for top-k series growth

See the generated [metrics reference](https://m7kni.io/meraki-dashboard-exporter/metrics/metrics/) for the authoritative metric list (kept in sync via `uv run python scripts/generate_metrics_docs.py`).

Metric-name, label, and unit compatibility is governed by the [Metric Stability & Deprecation Policy](docs/stability.md), which defines the Stable vs Experimental tiers, the 1.0 promise, and the post-1.0 rename process.

## Performance

- **Bounded concurrency**: ManagedTaskGroup keeps parallel collectors/orgs within `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT`; `MERAKI_EXPORTER_COLLECTORS__MAX_CONCURRENT_COLLECTORS` separately bounds how many collectors' own loops run concurrently
- **Adaptive scheduling**: each collector runs its own group-clocked loop; the scheduler solves per-endpoint-group intervals from data volatility floors (~60s/300s/900s+ typical) and the API budget, stretching lower-priority groups automatically under pressure — see [docs/observability/scheduler.md](docs/observability/scheduler.md)
- **Inventory-routed lookups**: Collectors fetch network/device data through the shared `OrganizationInventory` cache to suppress duplicate API calls
- **Batch controls**: Tunable batch sizes and delays (`MERAKI_EXPORTER_API__*BATCH_SIZE`, `MERAKI_EXPORTER_API__BATCH_DELAY`)
- **Adaptive smoothing**: Per-collector batch smoothing spreads work across the interval, capped at 30% of `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT` so a single collector cannot starve the run budget
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
