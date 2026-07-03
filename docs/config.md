# Configuration Reference

A comprehensive reference for all configuration options available in the Meraki Dashboard Exporter.

## Overview

The exporter can be configured using environment variables.
All configuration is based on Pydantic models with built-in validation.

## Environment Variable Format

Configuration follows a hierarchical structure using environment variables:

- **All settings**: `MERAKI_EXPORTER_{SECTION}__{SETTING}`
- **Double underscore** (`__`) separates nested configuration levels

!!! example "Environment Variable Examples"
    ```bash
    # Meraki API configuration
    export MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here
    export MERAKI_EXPORTER_MERAKI__ORG_ID=123456
    
    # Logging configuration
    export MERAKI_EXPORTER_LOGGING__LEVEL=INFO
    
    # API settings
    export MERAKI_EXPORTER_API__TIMEOUT=30
    export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=5
    ```

## Meraki Settings

Core Meraki API configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_MERAKI__API_KEY` | `SecretStr` | `_(required)_` | Meraki Dashboard API key |
| `MERAKI_EXPORTER_MERAKI__ORG_ID` | `str | None` | `_(none)_` | Meraki organization ID. For v1 the single-organization contract applies (one poller instance = one organization): when the API key sees exactly one org it is auto-selected and org_id may be omitted; when the key sees several orgs, set org_id explicitly (startup fails fast on an ambiguous multi-org key). See discovery.py/app startup. |
| `MERAKI_EXPORTER_MERAKI__API_BASE_URL` | `str` | `https://api.meraki.com/api/v1` | Meraki API base URL (use regional endpoints if needed) |

## Logging Settings

Logging configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_LOGGING__LEVEL` | `str` | `INFO` | Logging level (case-insensitive; normalised to upper-case) |
| `MERAKI_EXPORTER_LOGGING__LOG_FORMAT` | `str` | `logfmt` | Structured-log renderer: 'logfmt' (default) or 'json'. |

## API Settings

Configuration for Meraki API interactions

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_API__MAX_RETRIES` | `int` | `3` | Maximum number of retries for API requests (min: 0, max: 10) |
| `MERAKI_EXPORTER_API__TIMEOUT` | `int` | `30` | Per-request API timeout in seconds (SDK single_request_timeout). Note this applies to EACH page request, so a total_pages='all' bulk fetch may make many such requests; the overall fetch is additionally bounded by per_fetch_deadline_seconds. Reviewed for large-org bulk fetches (#556): kept at 30s (raise only if large-org page latencies are observed to exceed it). (min: 10, max: 300) |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` | `int` | `5` | Maximum concurrent API requests (global fallback) (min: 1, max: 20) |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_FAST` | `int` | `5` | Maximum concurrent API requests for FAST tier collectors (min: 1, max: 20) |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_MEDIUM` | `int` | `3` | Maximum concurrent API requests for MEDIUM tier collectors (min: 1, max: 20) |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_SLOW` | `int` | `2` | Maximum concurrent API requests for SLOW tier collectors (min: 1, max: 20) |
| `MERAKI_EXPORTER_API__BATCH_SIZE` | `int` | `20` | Default batch size for API operations (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__DEVICE_BATCH_SIZE` | `int` | `20` | Batch size for device operations (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__NETWORK_BATCH_SIZE` | `int` | `30` | Batch size for network operations (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__CLIENT_BATCH_SIZE` | `int` | `20` | Batch size for client operations (e.g., MR client metrics) (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__BATCH_DELAY` | `float` | `0.5` | Delay between batches in seconds (min: 0.0, max: 5.0) |
| `MERAKI_EXPORTER_API__RATE_LIMIT_RETRY_WAIT` | `int` | `5` | Wait time in seconds when rate limited (min: 1, max: 60) |
| `MERAKI_EXPORTER_API__ACTION_BATCH_RETRY_WAIT` | `int` | `10` | Wait time for action batch retries (min: 1, max: 60) |
| `MERAKI_EXPORTER_API__VALIDATE_KWARGS` | `bool` | `False` | When True, the Meraki SDK logs warnings if API methods are called with unrecognized kwargs. Recommended for dev/CI; off by default in production. |
| `MERAKI_EXPORTER_API__REQUESTS_PROXY` | `str | None` | `_(none)_` | HTTPS proxy URL for Meraki API requests (SDK requests_proxy); when unset the requests HTTPS_PROXY/NO_PROXY env vars still apply. |
| `MERAKI_EXPORTER_API__CERTIFICATE_PATH` | `str | None` | `_(none)_` | Path to a custom CA bundle for verifying the Meraki API TLS cert (SDK certificate_path); mount into read-only containers as a volume. |
| `MERAKI_EXPORTER_API__RATE_LIMIT_ENABLED` | `bool` | `True` | Enable client-side rate limiting to smooth API calls |
| `MERAKI_EXPORTER_API__RATE_LIMIT_REQUESTS_PER_SECOND` | `float` | `10.0` | Target requests per second per organization (min: 1.0, max: 50.0) |
| `MERAKI_EXPORTER_API__RATE_LIMIT_BURST` | `int` | `20` | Token bucket burst capacity per organization (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__RATE_LIMIT_SHARED_FRACTION` | `float` | `0.8` | Fraction of the org API call budget this exporter is allowed to consume. Defaults to 0.8 so ~20% headroom is left for other consumers of the same org budget (dashboards, other tools, humans); set to 1.0 to claim the whole budget (#550). (min: 0.1, max: 1.0) |
| `MERAKI_EXPORTER_API__RATE_LIMIT_JITTER_RATIO` | `float` | `0.1` | Jitter ratio applied to client-side rate limiter waits (min: 0.0, max: 0.5) |
| `MERAKI_EXPORTER_API__SMOOTHING_ENABLED` | `bool` | `True` | Spread batch work across the collection interval |
| `MERAKI_EXPORTER_API__SMOOTHING_WINDOW_RATIO` | `float` | `0.8` | Fraction of the collection interval used for smoothing (min: 0.1, max: 1.0) |
| `MERAKI_EXPORTER_API__SMOOTHING_MIN_BATCH_DELAY` | `float` | `1.0` | Minimum delay between batches when smoothing (min: 0.0, max: 60.0) |
| `MERAKI_EXPORTER_API__SMOOTHING_MAX_BATCH_DELAY` | `float` | `15.0` | Maximum delay between batches when smoothing (min: 0.0, max: 300.0) |
| `MERAKI_EXPORTER_API__MS_PORT_STATUS_USE_ORG_ENDPOINT` | `bool` | `True` | Use org-level switch port status endpoint for MS status metrics |
| `MERAKI_EXPORTER_API__MS_PORT_USAGE_INTERVAL` | `int` | `600` | Minimum seconds between per-switch port usage/POE refreshes (min: 0, max: 3600) |
| `MERAKI_EXPORTER_API__MS_PACKET_STATS_INTERVAL` | `int` | `600` | Minimum seconds between per-switch packet stats refreshes (min: 0, max: 3600) |
| `MERAKI_EXPORTER_API__CLIENT_APP_USAGE_INTERVAL` | `int` | `600` | Minimum seconds between client application usage refreshes (min: 0, max: 3600) |
| `MERAKI_EXPORTER_API__CLIENT_SIGNAL_QUALITY_INTERVAL` | `int` | `600` | Minimum seconds between per-client wireless signal-quality refreshes (min: 0, max: 3600) |
| `MERAKI_EXPORTER_API__CLIENT_SIGNAL_QUALITY_MAX_CLIENTS` | `int` | `200` | Maximum wireless clients queried for signal quality per network per cycle (0 disables the cap). Bounds the sequential per-client API fan-out. (min: 0, max: 5000) |
| `MERAKI_EXPORTER_API__RETRY_AFTER_MAX_SECONDS` | `int` | `60` | Upper bound (seconds) honoured for a server-sent Retry-After header when backing off a throttled (429/503) request. Caps pathological Retry-After values so a single throttled request cannot stall a collection cycle indefinitely. (min: 1, max: 3600) |
| `MERAKI_EXPORTER_API__EXECUTOR_WORKERS` | `int` | `10` | Size of the thread pool used to run the synchronous Meraki SDK off the event loop (the asyncio.to_thread executor). Bounds the number of concurrent blocking SDK calls independently of the per-tier API concurrency limits. (min: 1, max: 100) |
| `MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS` | `int` | `120` | Wall-clock deadline (seconds) for a single logical fetch, including all paginated page requests made under total_pages='all'. Sits between the SDK per-request timeout (see 'timeout') and the per-collector timeout so a slow bulk fetch fails fast instead of consuming the whole collector budget. (min: 1, max: 600) |

## Update Intervals

Control how often different types of metrics are collected

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_UPDATE_INTERVALS__FAST` | `int` | `60` | Interval for fast-moving data (sensors) in seconds (min: 30, max: 300) |
| `MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM` | `int` | `300` | Interval for medium-moving data (device metrics) in seconds (min: 300, max: 1800) |
| `MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW` | `int` | `900` | Interval for slow-moving data (configuration) in seconds (min: 600, max: 3600) |

`MEDIUM` must be greater than or equal to `FAST`, `SLOW` must be greater than or equal to `MEDIUM`, and `MEDIUM` must be a multiple of `FAST`.

## Server Settings

HTTP server configuration for the metrics endpoint

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_SERVER__HOST` | `str` | `0.0.0.0` | Host to bind the exporter to |
| `MERAKI_EXPORTER_SERVER__PORT` | `int` | `9099` | Port to bind the exporter to (min: 1, max: 65535) |
| `MERAKI_EXPORTER_SERVER__API_TOKEN` | `SecretStr | None` | `_(none)_` | Optional bearer token required for state-changing POST control endpoints (/api/collectors/trigger, /api/clients/clear-dns-cache). When unset (default) these endpoints are unauthenticated - bind the exporter to a trusted interface. When set, requests must present 'Authorization: Bearer <token>'. |
| `MERAKI_EXPORTER_SERVER__UI_ENABLED` | `bool` | `True` | When false, sensitive GET UI/status endpoints return 404 (metrics/health/ready stay open). |

## Webhook Settings

Webhook receiver configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_WEBHOOKS__ENABLED` | `bool` | `False` | Enable webhook receiver endpoint |
| `MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` | `SecretStr | None` | `_(none)_` | Shared secret for webhook validation (recommended) |
| `MERAKI_EXPORTER_WEBHOOKS__REQUIRE_SECRET` | `bool` | `True` | Require shared secret validation (disable for testing only) |
| `MERAKI_EXPORTER_WEBHOOKS__ALLOW_INSECURE` | `bool` | `False` | Explicit opt-in to run the webhook receiver enabled without require_secret; startup refuses the insecure combo unless this is true. |
| `MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE` | `int` | `1048576` | Maximum webhook payload size in bytes (min: 1024, max: 10485760) |

Webhooks are received on `POST /api/webhooks/meraki` when enabled.

## OpenTelemetry Settings

OpenTelemetry observability configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_OTEL__ENABLED` | `bool` | `False` | Enable OpenTelemetry tracing |
| `MERAKI_EXPORTER_OTEL__ENDPOINT` | `str | None` | `_(none)_` | OpenTelemetry collector endpoint (OTLP gRPC) |
| `MERAKI_EXPORTER_OTEL__INSECURE` | `bool` | `True` | Send OTLP traces over an insecure (non-TLS) channel. Set False to use TLS/system-trust-store transport to the collector endpoint. |
| `MERAKI_EXPORTER_OTEL__SERVICE_NAME` | `str` | `meraki-dashboard-exporter` | Service name for OpenTelemetry tracing |
| `MERAKI_EXPORTER_OTEL__SAMPLING_RATE` | `float` | `0.1` | Trace sampling rate (0.0-1.0). 0 disables sampling, 1 samples every trace, values in between use ratio-based parent sampling. (min: 0.0, max: 1.0) |
| `MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES` | `dict[str, str]` | `{}` | Additional resource attributes for OpenTelemetry |
| `MERAKI_EXPORTER_OTEL__LOGS` | `OTelLogsSettings` | `enabled=False endpoint=None insecure=None include_identifiers=False events=None` | OTLP data-log emitter settings (#622); independent of tracing. |
| `MERAKI_EXPORTER_OTEL__LOGS__ENABLED` | `bool` | `False` | Enable the OTLP data-log emitter for high-cardinality per-entity product data. Independent of otel.enabled (tracing). Off by default. |
| `MERAKI_EXPORTER_OTEL__LOGS__ENDPOINT` | `str | None` | `_(none)_` | OTLP gRPC endpoint for data logs. When None, falls back to otel.endpoint. An endpoint must resolve (own or inherited) when logs.enabled is True. |
| `MERAKI_EXPORTER_OTEL__LOGS__INSECURE` | `bool | None` | `_(none)_` | Send OTLP data logs over an insecure (non-TLS) channel. When None, inherits otel.insecure. |
| `MERAKI_EXPORTER_OTEL__LOGS__INCLUDE_IDENTIFIERS` | `bool` | `False` | PII opt-in. When False (default), the emitter drops identifier attributes (client.mac / client.hostname / client.description) from every record; only stable IDs (client.id) are emitted. Set True to include the human-readable identifiers. |
| `MERAKI_EXPORTER_OTEL__LOGS__EVENTS` | `list[str] | None` | `_(none)_` | Per-data-class allowlist of built-in data-log event names (see DataLogEvent in core/otel_data_logs.py, e.g. "meraki.wireless.client.packet_loss"). None (default) enables all built-in events; an explicit list enables only the named events. Env: JSON array. |
| `MERAKI_EXPORTER_OTEL__METRICS` | `OTelMetricsSettings` | `enabled=False endpoint=None insecure=None export_interval_seconds=60 include='all' temporality='cumulative'` | OTLP metrics bridge settings (#313/#339); independent of tracing. |
| `MERAKI_EXPORTER_OTEL__METRICS__ENABLED` | `bool` | `False` | Enable the OTLP metrics bridge (push a periodic snapshot of the Prometheus registry via OTLP gRPC). Independent of otel.enabled (tracing) and otel.logs.enabled. Off by default; the /metrics scrape is unchanged either way. |
| `MERAKI_EXPORTER_OTEL__METRICS__ENDPOINT` | `str | None` | `_(none)_` | OTLP gRPC endpoint for metrics. When None, falls back to otel.endpoint. Must resolve (own or inherited) when metrics.enabled is True. |
| `MERAKI_EXPORTER_OTEL__METRICS__INSECURE` | `bool | None` | `_(none)_` | Send OTLP metrics over an insecure (non-TLS) channel. When None, inherits otel.insecure. |
| `MERAKI_EXPORTER_OTEL__METRICS__EXPORT_INTERVAL_SECONDS` | `int` | `60` | Seconds between registry snapshots pushed via OTLP. (min: 10, max: 3600) |
| `MERAKI_EXPORTER_OTEL__METRICS__INCLUDE` | `product | self | all` | `all` | Which telemetry plane to push, keyed on the metric-name prefix split: "product" = meraki_* excluding meraki_exporter_*; "self" = everything else (meraki_exporter_* plus the process/python runtime families); "all" = both. |
| `MERAKI_EXPORTER_OTEL__METRICS__TEMPORALITY` | `cumulative` | `cumulative` | Counter/histogram temporality. v1 accepts only 'cumulative' (Grafana Cloud expects cumulative; prometheus_client counters are cumulative-since-start, so this is the only faithful translation). |
| `MERAKI_EXPORTER_OTEL__CA_CERT_PATH` | `str | None` | `_(none)_` | Path to a CA certificate (PEM) used to verify the OTLP collector's TLS certificate, shared by all three OTLP channels (traces, data logs, metrics). Paths only - no inline PEM material (#314). |
| `MERAKI_EXPORTER_OTEL__CLIENT_CERT_PATH` | `str | None` | `_(none)_` | Path to a client certificate (PEM) for mTLS to the OTLP collector, shared by all three OTLP channels. Must be set together with client_key_path (#314). |
| `MERAKI_EXPORTER_OTEL__CLIENT_KEY_PATH` | `str | None` | `_(none)_` | Path to a client private key (PEM) for mTLS to the OTLP collector, shared by all three OTLP channels. Must be set together with client_cert_path (#314). |

## Monitoring Settings

Internal monitoring and alerting configuration

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_MONITORING__MAX_CONSECUTIVE_FAILURES` | `int` | `10` | Maximum consecutive failures before alerting (min: 1, max: 100) |
| `MERAKI_EXPORTER_MONITORING__HISTOGRAM_BUCKETS` | `list[float]` | `[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]` | Histogram buckets for collector duration metrics |
| `MERAKI_EXPORTER_MONITORING__LICENSE_EXPIRATION_WARNING_DAYS` | `int` | `30` | Days before license expiration to start warning (min: 7, max: 90) |
| `MERAKI_EXPORTER_MONITORING__METRIC_TTL_MULTIPLIER` | `float` | `2.0` | Multiplier for metric TTL (collection_interval * multiplier) (min: 1.0, max: 10.0) |
| `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` | `int` | `10000` | Maximum number of tracked label sets per collector before shedding oldest (min: 100, max: 1000000) |
| `MERAKI_EXPORTER_MONITORING__LIVENESS_MAX_STALE_SECONDS` | `int` | `0` | Dead-man switch threshold. /health returns 503 once no collector has completed a successful run within this many seconds, so Kubernetes/Docker restart a wedged exporter instead of leaving it serving stale metrics. 0 (default) auto-derives the threshold from the fastest *enabled* tier's interval (3 x that interval), so a stalled fast loop trips liveness promptly without slower tiers causing false positives. Set a large value to effectively disable. (min: 0, max: 86400) |

## Collector Settings

Enable/disable specific metric collectors

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS` | `set[str]` | `["alerts", "clients", "config", "device", "insight", "mtsensor", "mtsensoralerts", "networkhealth", "organization"]` | Enabled collector names |
| `MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS` | `set[str]` | `[]` | Explicitly disabled collectors (overrides enabled) |
| `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT` | `int` | `240` | Timeout for individual collector runs in seconds (min: 30, max: 600) |
| `MERAKI_EXPORTER_COLLECTORS__COLLECT_AP_SIGNAL_QUALITY` | `bool` | `True` | Collect per-AP wireless signal quality (RSSI/SNR). Costs ONE API call per selected AP per cycle (hourly cadence; no bulk endpoint exists). Scope the fan-out with ap_signal_quality_tags, or disable entirely. |
| `MERAKI_EXPORTER_COLLECTORS__AP_SIGNAL_QUALITY_TAGS` | `list[str]` | `[]` | Meraki device tags scoping AP signal-quality collection. Empty = all APs; non-empty = only APs carrying at least one of these tags (CSV or JSON array). |
| `MERAKI_EXPORTER_COLLECTORS__COLLECT_INSIGHT` | `bool` | `False` | Enable the Meraki Insight collector (license-gated WAN/application health). Off by default; degrades to a debug-level skip when the org lacks Insight. |
| `MERAKI_EXPORTER_COLLECTORS__INSIGHT_APP_HEALTH_ENABLED` | `bool` | `True` | When collect_insight is on, also fan out per-network application health (one call per network x monitored application per cycle). |

## Client Settings

Client data collection and DNS resolution settings

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_CLIENTS__ENABLED` | `bool` | `False` | Enable client data collection |
| `MERAKI_EXPORTER_CLIENTS__DNS_TIMEOUT` | `float` | `5.0` | DNS lookup timeout in seconds (min: 0.5, max: 10.0) |
| `MERAKI_EXPORTER_CLIENTS__DNS_CACHE_TTL` | `int` | `21600` | DNS cache TTL in seconds (default: 6 hours) (min: 300, max: 86400) |
| `MERAKI_EXPORTER_CLIENTS__DNS_CACHE_MAX_ENTRIES` | `int` | `100000` | Maximum number of reverse-DNS cache entries (and per-client IP-tracking entries) held in memory. When exceeded, expired entries are pruned first, then the oldest entries are evicted so RSS stays bounded under sustained client churn (#543). (min: 1000, max: 5000000) |
| `MERAKI_EXPORTER_CLIENTS__CACHE_TTL` | `int` | `3600` | Client cache TTL in seconds (for ID/hostname mappings, not metrics) (min: 300, max: 86400) |
| `MERAKI_EXPORTER_CLIENTS__MAX_CLIENTS_PER_NETWORK` | `int` | `10000` | Maximum clients to track per network (min: 100, max: 50000) |
| `MERAKI_EXPORTER_CLIENTS__MAX_CLIENTS_TOTAL` | `int` | `25000` | Global cap on clients emitted as metric series across ALL networks per collection cycle. Clients beyond the cap are dropped from metric emission with a warning and counted in meraki_exporter_clients_over_cap. (min: 100, max: 1000000) |
| `MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED` | `bool` | `False` | Enable per-client wireless signal quality (RSSI/SNR) collection. Costs one API call per wireless client per cycle (interval-gated); prohibitively expensive at scale, so disabled by default. |

## Cardinality Settings

Metric cardinality guard (series-per-family caps and shedding)

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_CARDINALITY__MAX_SERIES_PER_FAMILY` | `int` | `50000` | Maximum number of active time series permitted per metric family (metric name). When a family exceeds this, ``action`` decides what happens. (min: 100, max: 10000000) |
| `MERAKI_EXPORTER_CARDINALITY__ACTION` | `warn | drop` | `warn` | What to do when a metric family exceeds max_series_per_family: 'warn' logs and keeps emitting; 'drop' stops emitting new series for that family. |
| `MERAKI_EXPORTER_CARDINALITY__DISABLED_METRICS` | `set[str]` | `[]` | Metric family names to disable entirely (never emitted). Accepts a comma-separated string or a JSON array via env (MERAKI_EXPORTER_CARDINALITY__DISABLED_METRICS=a,b,c). |
| `MERAKI_EXPORTER_CARDINALITY__MONITOR_INTERVAL_SECONDS` | `int` | `300` | How often (seconds) the cardinality monitor samples the registry. (min: 10, max: 3600) |
| `MERAKI_EXPORTER_CARDINALITY__MONITOR_MAX_LABEL_VALUES` | `int` | `100` | Maximum distinct values retained per label when the cardinality monitor tracks label-value breakdowns, bounding the monitor's own memory. (min: 1, max: 100000) |

## Scheduler Settings

Adaptive budget-aware endpoint scheduler (AIMD, stretch, resolve cadence)

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_SCHEDULER__MODE` | `adaptive | fixed` | `adaptive` | 'adaptive' (default): solver stretches endpoint-group intervals to fit the API budget. 'fixed': floors/pins only, no stretching, no AIMD (transition fallback). |
| `MERAKI_EXPORTER_SCHEDULER__TARGET_UTILIZATION` | `float` | `0.7` | Fraction of the effective budget the solver plans to; headroom absorbs bursts. (min: 0.1, max: 1.0) |
| `MERAKI_EXPORTER_SCHEDULER__MAX_STRETCH_FACTOR` | `float` | `4.0` | Per-group interval cap as a multiple of its volatility floor. (min: 1.0, max: 16.0) |
| `MERAKI_EXPORTER_SCHEDULER__MAX_INTERVAL_SECONDS` | `int` | `3600` | Absolute per-group interval cap. (min: 300, max: 86400) |
| `MERAKI_EXPORTER_SCHEDULER__RESOLVE_INTERVAL_SECONDS` | `int` | `900` | How often the solver recomputes from org shape (matches inventory TTL). (min: 60, max: 86400) |
| `MERAKI_EXPORTER_SCHEDULER__AIMD_ENABLED` | `bool` | `True` | 429/Retry-After budget feedback (adaptive mode only). |
| `MERAKI_EXPORTER_SCHEDULER__AIMD_BACKOFF_MULTIPLIER` | `float` | `0.5` |  (min: 0.1, max: 0.9) |
| `MERAKI_EXPORTER_SCHEDULER__AIMD_RECOVERY_RPS_PER_MINUTE` | `float` | `0.1` |  (min: 0.01, max: 5.0) |
| `MERAKI_EXPORTER_SCHEDULER__AIMD_RESOLVE_HYSTERESIS` | `float` | `0.2` |  (min: 0.05, max: 1.0) |
| `MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES` | `dict[str, int]` | `{}` | Per-group interval pins, e.g. {"nh_connection_stats": 900}. Pinned groups are excluded from solver stretching. Env: JSON object. |

## Network Filter Settings

Restrict which networks are scraped by name glob, ID, or tag

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_NAMES` | `list[str]` | `[]` | Network name globs to include. Supports * and ? wildcards. |
| `MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_IDS` | `list[str]` | `[]` | Exact network IDs (e.g. L_xxx) to include. |
| `MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_TAGS` | `list[str]` | `[]` | Network tags to include. A network matches if it carries any of these tags. |
| `MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_NAMES` | `list[str]` | `[]` | Network name globs to exclude. Applied AFTER includes. |
| `MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_IDS` | `list[str]` | `[]` | Exact network IDs to exclude. |
| `MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_TAGS` | `list[str]` | `[]` | Network tags to exclude. |

All fields default to empty, which leaves the filter inactive (every network in every configured org is scraped). If any `INCLUDE_*` field is set, a network must match at least one include rule (by name, ID, or tag) to be considered; exclude rules are applied afterward and always win. Name fields (`INCLUDE_NAMES`/`EXCLUDE_NAMES`) are case-sensitive glob patterns (`*`/`?`). Values are comma-separated lists (or a JSON array string).

