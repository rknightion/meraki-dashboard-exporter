"""Nested configuration models for better organization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, get_args
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import NoDecode

from .constants.config_constants import (
    MERAKI_API_BASE_URL,
    MERAKI_API_BASE_URL_CANADA,
    MERAKI_API_BASE_URL_CHINA,
    MERAKI_API_BASE_URL_INDIA,
    MERAKI_API_BASE_URL_US_FED,
)
from .logging import get_logger

logger = get_logger(__name__)

#: Well-known Meraki regional API base URLs. A configured ``api_base_url`` that
#: is well-formed but not in this set is accepted with a warning (custom proxies
#: and future regions must keep working) - see :class:`MerakiSettings`.
KNOWN_REGION_BASE_URLS: frozenset[str] = frozenset({
    MERAKI_API_BASE_URL,
    MERAKI_API_BASE_URL_CANADA,
    MERAKI_API_BASE_URL_CHINA,
    MERAKI_API_BASE_URL_INDIA,
    MERAKI_API_BASE_URL_US_FED,
})


def _split_collector_csv(v: object) -> set[str]:
    """Accept a set/list or a comma-separated / JSON-array string of names.

    pydantic-settings does not auto-coerce a CSV env string into a ``set[str]``
    for nested ``BaseModel`` fields (only at the top ``BaseSettings`` boundary),
    so - like :class:`NetworkFilterSettings` - we normalise here. This lets the
    documented ``COLLECTORS__ENABLED_COLLECTORS=a,b,c`` env form boot instead of
    raising ``SettingsError`` (#514).
    """
    if v is None:
        return set()
    if isinstance(v, (set, frozenset, list, tuple)):
        return {str(item).strip() for item in v if str(item).strip()}
    if isinstance(v, str):
        stripped = v.strip()
        if not stripped:
            return set()
        # Allow JSON-array form too (consistent with histogram_buckets).
        if stripped.startswith("[") and stripped.endswith("]"):
            import json

            parsed = json.loads(stripped)
            return {str(item).strip() for item in parsed if str(item).strip()}
        return {item.strip() for item in stripped.split(",") if item.strip()}
    raise ValueError(f"Collector set field got unsupported type: {type(v)!r}")


class APISettings(BaseModel):
    """API-related configuration settings."""

    max_retries: int = Field(
        3,
        ge=0,
        le=10,
        description="Maximum number of retries for API requests",
    )
    timeout: int = Field(
        30,
        ge=10,
        le=300,
        description=(
            "Per-request API timeout in seconds (SDK single_request_timeout). Note this "
            "applies to EACH page request, so a total_pages='all' bulk fetch may make "
            "many such requests; the overall fetch is additionally bounded by "
            "per_fetch_deadline_seconds. Reviewed for large-org bulk fetches (#556): "
            "kept at 30s (raise only if large-org page latencies are observed to exceed it)."
        ),
    )
    concurrency_limit: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum concurrent API requests (global fallback)",
    )
    concurrency_limit_fast: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum concurrent API requests for FAST tier collectors",
    )
    concurrency_limit_medium: int = Field(
        3,
        ge=1,
        le=20,
        description="Maximum concurrent API requests for MEDIUM tier collectors",
    )
    concurrency_limit_slow: int = Field(
        2,
        ge=1,
        le=20,
        description="Maximum concurrent API requests for SLOW tier collectors",
    )
    batch_size: int = Field(
        20,  # Increased from 10 for better throughput
        ge=1,
        le=100,  # Increased max from 50
        description="Default batch size for API operations",
    )
    device_batch_size: int = Field(
        20,  # Optimized for device operations
        ge=1,
        le=100,
        description="Batch size for device operations",
    )
    network_batch_size: int = Field(
        30,  # Optimized for network operations
        ge=1,
        le=100,
        description="Batch size for network operations",
    )
    client_batch_size: int = Field(
        20,  # Optimized for client operations
        ge=1,
        le=100,
        description="Batch size for client operations (e.g., MR client metrics)",
    )
    batch_delay: float = Field(
        0.5,
        ge=0.0,
        le=5.0,
        description="Delay between batches in seconds",
    )
    rate_limit_retry_wait: int = Field(
        5,
        ge=1,
        le=60,
        description="Wait time in seconds when rate limited",
    )
    action_batch_retry_wait: int = Field(
        10,
        ge=1,
        le=60,
        description="Wait time for action batch retries",
    )
    validate_kwargs: bool = Field(
        False,
        description=(
            "When True, the Meraki SDK logs warnings if API methods are called with "
            "unrecognized kwargs. Recommended for dev/CI; off by default in production."
        ),
    )
    requests_proxy: str | None = Field(
        None,
        description=(
            "HTTPS proxy URL for Meraki API requests (SDK requests_proxy); when unset "
            "the requests HTTPS_PROXY/NO_PROXY env vars still apply."
        ),
    )
    certificate_path: str | None = Field(
        None,
        description=(
            "Path to a custom CA bundle for verifying the Meraki API TLS cert (SDK "
            "certificate_path); mount into read-only containers as a volume."
        ),
    )
    rate_limit_enabled: bool = Field(
        True,
        description="Enable client-side rate limiting to smooth API calls",
    )
    rate_limit_requests_per_second: float = Field(
        10.0,
        ge=1.0,
        le=50.0,
        description="Target requests per second per organization",
    )
    rate_limit_burst: int = Field(
        20,
        ge=1,
        le=100,
        description="Token bucket burst capacity per organization",
    )
    rate_limit_shared_fraction: float = Field(
        0.8,
        ge=0.1,
        le=1.0,
        description=(
            "Fraction of the org API call budget this exporter is allowed to consume. "
            "Defaults to 0.8 so ~20% headroom is left for other consumers of the same "
            "org budget (dashboards, other tools, humans); set to 1.0 to claim the whole "
            "budget (#550)."
        ),
    )
    rate_limit_jitter_ratio: float = Field(
        0.1,
        ge=0.0,
        le=0.5,
        description="Jitter ratio applied to client-side rate limiter waits",
    )
    smoothing_enabled: bool = Field(
        True,
        description="Spread batch work across the collection interval",
    )
    smoothing_window_ratio: float = Field(
        0.8,
        ge=0.1,
        le=1.0,
        description="Fraction of the collection interval used for smoothing",
    )
    smoothing_min_batch_delay: float = Field(
        1.0,
        ge=0.0,
        le=60.0,
        description="Minimum delay between batches when smoothing",
    )
    smoothing_max_batch_delay: float = Field(
        15.0,
        ge=0.0,
        le=300.0,
        description="Maximum delay between batches when smoothing",
    )
    ms_port_status_use_org_endpoint: bool = Field(
        True,
        description="Use org-level switch port status endpoint for MS status metrics",
    )
    ms_port_usage_interval: int = Field(
        600,
        ge=0,
        le=3600,
        description="Minimum seconds between per-switch port usage/POE refreshes",
    )
    ms_packet_stats_interval: int = Field(
        600,
        ge=0,
        le=3600,
        description="Minimum seconds between per-switch packet stats refreshes",
    )
    client_app_usage_interval: int = Field(
        600,
        ge=0,
        le=3600,
        description="Minimum seconds between client application usage refreshes",
    )
    client_signal_quality_interval: int = Field(
        600,
        ge=0,
        le=3600,
        description="Minimum seconds between per-client wireless signal-quality refreshes",
    )
    client_signal_quality_max_clients: int = Field(
        200,
        ge=0,
        le=5000,
        description=(
            "Maximum wireless clients queried for signal quality per network per cycle "
            "(0 disables the cap). Bounds the sequential per-client API fan-out."
        ),
    )
    retry_after_max_seconds: int = Field(
        60,
        ge=1,
        le=3600,
        description=(
            "Upper bound (seconds) honoured for a server-sent Retry-After header when "
            "backing off a throttled (429/503) request. Caps pathological Retry-After "
            "values so a single throttled request cannot stall a collection cycle "
            "indefinitely."
        ),
    )
    executor_workers: int = Field(
        10,
        ge=1,
        le=100,
        description=(
            "Size of the thread pool used to run the synchronous Meraki SDK off the "
            "event loop (the asyncio.to_thread executor). Bounds the number of "
            "concurrent blocking SDK calls independently of the per-tier API "
            "concurrency limits."
        ),
    )
    per_fetch_deadline_seconds: int = Field(
        120,
        ge=1,
        le=600,
        description=(
            "Wall-clock deadline (seconds) for a single logical fetch, including all "
            "paginated page requests made under total_pages='all'. Sits between the SDK "
            "per-request timeout (see 'timeout') and the per-collector timeout so a slow "
            "bulk fetch fails fast instead of consuming the whole collector budget."
        ),
    )


class UpdateIntervals(BaseModel):
    """Update interval configuration with validation."""

    fast: int = Field(
        60,
        ge=30,
        le=300,
        description="Interval for fast-moving data (sensors) in seconds",
    )
    medium: int = Field(
        300,
        ge=300,
        le=1800,
        description="Interval for medium-moving data (device metrics) in seconds",
    )
    slow: int = Field(
        900,
        ge=600,
        le=3600,
        description="Interval for slow-moving data (configuration) in seconds",
    )

    @model_validator(mode="after")
    def validate_intervals(self) -> UpdateIntervals:
        """Ensure intervals are properly ordered."""
        if self.medium < self.fast:
            raise ValueError("Medium interval must be >= fast interval")
        if self.slow < self.medium:
            raise ValueError("Slow interval must be >= medium interval")
        # Ensure medium interval is a multiple of fast interval for better alignment
        if self.medium % self.fast != 0:
            raise ValueError(
                f"Medium interval ({self.medium}s) should be a multiple of fast interval ({self.fast}s)"
            )
        return self


class MonitoringSettings(BaseModel):
    """Monitoring and observability settings."""

    max_consecutive_failures: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum consecutive failures before alerting",
    )
    histogram_buckets: list[float] = Field(
        default=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
        description="Histogram buckets for collector duration metrics",
    )
    license_expiration_warning_days: int = Field(
        30,
        ge=7,
        le=90,
        description="Days before license expiration to start warning",
    )
    metric_ttl_multiplier: float = Field(
        2.0,
        ge=1.0,
        le=10.0,
        description="Multiplier for metric TTL (collection_interval * multiplier)",
    )
    max_cardinality_per_collector: int = Field(
        10000,
        ge=100,
        le=1000000,
        description="Maximum number of tracked label sets per collector before shedding oldest",
    )
    liveness_max_stale_seconds: int = Field(
        0,
        ge=0,
        le=86400,
        description=(
            "Dead-man switch threshold. /health returns 503 once no collector has "
            "completed a successful run within this many seconds, so Kubernetes/Docker "
            "restart a wedged exporter instead of leaving it serving stale metrics. "
            "0 (default) auto-derives the threshold from the SLOW tier interval "
            "(3 x slow interval). Set a large value to effectively disable."
        ),
    )

    @field_validator("histogram_buckets")
    @classmethod
    def validate_buckets(cls, v: list[float]) -> list[float]:
        """Ensure buckets are sorted and positive."""
        if not v:
            raise ValueError("Histogram buckets cannot be empty")
        if not all(b > 0 for b in v):
            raise ValueError("All bucket values must be positive")
        if v != sorted(v):
            raise ValueError("Bucket values must be in ascending order")
        return v


class CardinalitySettings(BaseModel):
    """Metric cardinality guard-rail settings (SCALE-01 / #540 family).

    Bounds per-metric-family series growth at scale and configures the
    cardinality monitor. This is only the config surface; the behaviour that
    consumes these settings (the per-family cap enforcement and the monitor)
    lives in ``core/cardinality.py`` and the collector emit path.
    """

    max_series_per_family: int = Field(
        50000,
        ge=100,
        le=10_000_000,
        description=(
            "Maximum number of active time series permitted per metric family (metric "
            "name). When a family exceeds this, ``action`` decides what happens."
        ),
    )
    action: Literal["warn", "drop"] = Field(
        "warn",
        description=(
            "What to do when a metric family exceeds max_series_per_family: 'warn' logs "
            "and keeps emitting; 'drop' stops emitting new series for that family."
        ),
    )
    # NoDecode disables pydantic-settings JSON-parsing of complex types so the raw
    # env-var string reaches our _split_csv validator - the documented CSV form
    # (CARDINALITY__DISABLED_METRICS=a,b,c) would otherwise crash at boot with
    # SettingsError because a bare CSV string is not valid JSON (same pattern as #514).
    disabled_metrics: Annotated[set[str], NoDecode] = Field(
        default_factory=set,
        description=(
            "Metric family names to disable entirely (never emitted). Accepts a "
            "comma-separated string or a JSON array via env "
            "(MERAKI_EXPORTER_CARDINALITY__DISABLED_METRICS=a,b,c)."
        ),
    )
    monitor_interval_seconds: int = Field(
        300,
        ge=10,
        le=3600,
        description="How often (seconds) the cardinality monitor samples the registry.",
    )
    monitor_max_label_values: int = Field(
        100,
        ge=1,
        le=100000,
        description=(
            "Maximum distinct values retained per label when the cardinality monitor "
            "tracks label-value breakdowns, bounding the monitor's own memory."
        ),
    )

    @field_validator("disabled_metrics", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> set[str]:
        """Accept a set, a comma-separated string, or a JSON array from env vars."""
        return _split_collector_csv(v)


class OTelSettings(BaseModel):
    """OpenTelemetry configuration settings."""

    enabled: bool = Field(
        False,
        description="Enable OpenTelemetry tracing",
    )
    endpoint: str | None = Field(
        None,
        description="OpenTelemetry collector endpoint (OTLP gRPC)",
    )
    insecure: bool = Field(
        True,
        description=(
            "Send OTLP traces over an insecure (non-TLS) channel. Set False to use "
            "TLS/system-trust-store transport to the collector endpoint."
        ),
    )
    service_name: str = Field(
        "meraki-dashboard-exporter",
        description="Service name for OpenTelemetry tracing",
    )
    sampling_rate: float = Field(
        0.1,
        ge=0.0,
        le=1.0,
        description=(
            "Trace sampling rate (0.0-1.0). 0 disables sampling, 1 samples every "
            "trace, values in between use ratio-based parent sampling."
        ),
    )
    resource_attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Additional resource attributes for OpenTelemetry",
    )

    @model_validator(mode="after")
    def validate_endpoint(self) -> OTelSettings:
        """Ensure endpoint is provided when enabled."""
        if self.enabled and not self.endpoint:
            raise ValueError("OTEL endpoint must be provided when OTEL is enabled")
        return self


class ServerSettings(BaseModel):
    """HTTP server configuration."""

    host: str = Field(
        "0.0.0.0",  # nosec B104
        description="Host to bind the exporter to",
    )
    port: int = Field(
        9099,
        ge=1,
        le=65535,
        description="Port to bind the exporter to",
    )
    api_token: SecretStr | None = Field(
        None,
        description=(
            "Optional bearer token required for state-changing POST control "
            "endpoints (/api/collectors/trigger, /api/clients/clear-dns-cache). "
            "When unset (default) these endpoints are unauthenticated - bind the "
            "exporter to a trusted interface. When set, requests must present "
            "'Authorization: Bearer <token>'."
        ),
    )
    ui_enabled: bool = Field(
        True,
        description=(
            "When false, sensitive GET UI/status endpoints return 404 "
            "(metrics/health/ready stay open)."
        ),
    )


class WebhookSettings(BaseModel):
    """Webhook receiver configuration."""

    enabled: bool = Field(
        False,
        description="Enable webhook receiver endpoint",
    )
    shared_secret: SecretStr | None = Field(
        None,
        description="Shared secret for webhook validation (recommended)",
    )
    require_secret: bool = Field(
        True,
        description="Require shared secret validation (disable for testing only)",
    )
    allow_insecure: bool = Field(
        False,
        description=(
            "Explicit opt-in to run the webhook receiver enabled without require_secret; "
            "startup refuses the insecure combo unless this is true."
        ),
    )
    max_payload_size: int = Field(
        1024 * 1024,  # 1MB
        ge=1024,
        le=10 * 1024 * 1024,  # 10MB max
        description="Maximum webhook payload size in bytes",
    )


class CollectorSettings(BaseModel):
    """Collector-specific settings."""

    # NoDecode disables pydantic-settings JSON-parsing of complex types so the
    # raw env-var string reaches our _split_csv validator - the documented CSV
    # form (COLLECTORS__ENABLED_COLLECTORS=a,b,c) would otherwise crash at boot
    # with SettingsError because a bare CSV string is not valid JSON (#514).
    enabled_collectors: Annotated[set[str], NoDecode] = Field(
        default_factory=lambda: {
            "alerts",
            "clients",
            "config",
            "device",
            "mtsensor",
            "mtsensoralerts",
            "networkhealth",
            "organization",
        },
        description="Enabled collector names",
    )
    disable_collectors: Annotated[set[str], NoDecode] = Field(
        default_factory=set,
        description="Explicitly disabled collectors (overrides enabled)",
    )
    collector_timeout: int = Field(
        240,
        ge=30,
        le=600,
        description="Timeout for individual collector runs in seconds",
    )

    @field_validator("enabled_collectors", "disable_collectors", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> set[str]:
        """Accept a set, a comma-separated string, or a JSON array from env vars."""
        return _split_collector_csv(v)

    @property
    def active_collectors(self) -> set[str]:
        """The final set of active collectors."""
        return self.enabled_collectors - self.disable_collectors


class ClientSettings(BaseModel):
    """Client data collection settings."""

    enabled: bool = Field(
        False,
        description="Enable client data collection",
    )
    dns_timeout: float = Field(
        5.0,
        ge=0.5,
        le=10.0,
        description="DNS lookup timeout in seconds",
    )
    dns_cache_ttl: int = Field(
        21600,  # 6 hours
        ge=300,  # 5 minutes minimum
        le=86400,  # 24 hours maximum
        description="DNS cache TTL in seconds (default: 6 hours)",
    )
    dns_cache_max_entries: int = Field(
        100000,
        ge=1000,
        le=5_000_000,
        description=(
            "Maximum number of reverse-DNS cache entries (and per-client IP-tracking "
            "entries) held in memory. When exceeded, expired entries are pruned first, "
            "then the oldest entries are evicted so RSS stays bounded under sustained "
            "client churn (#543)."
        ),
    )
    cache_ttl: int = Field(
        3600,
        ge=300,
        le=86400,
        description="Client cache TTL in seconds (for ID/hostname mappings, not metrics)",
    )
    max_clients_per_network: int = Field(
        10000,
        ge=100,
        le=50000,
        description="Maximum clients to track per network",
    )
    max_clients_total: int = Field(
        25000,
        ge=100,
        le=1_000_000,
        description=(
            "Global cap on clients emitted as metric series across ALL networks per "
            "collection cycle. Clients beyond the cap are dropped from metric emission "
            "with a warning and counted in meraki_exporter_clients_over_cap."
        ),
    )
    signal_quality_enabled: bool = Field(
        False,
        description=(
            "Enable per-client wireless signal quality (RSSI/SNR) collection. Costs one "
            "API call per wireless client per cycle (interval-gated); prohibitively "
            "expensive at scale, so disabled by default."
        ),
    )


class MerakiSettings(BaseModel):
    """Meraki API configuration."""

    api_key: SecretStr = Field(
        ...,
        description="Meraki Dashboard API key",
    )
    org_id: str | None = Field(
        None,
        description=(
            "Meraki organization ID. For v1 the single-organization contract "
            "applies (one poller instance = one organization): when the API key "
            "sees exactly one org it is auto-selected and org_id may be omitted; "
            "when the key sees several orgs, set org_id explicitly (startup fails "
            "fast on an ambiguous multi-org key). See discovery.py/app startup."
        ),
    )
    api_base_url: str = Field(
        "https://api.meraki.com/api/v1",
        description="Meraki API base URL (use regional endpoints if needed)",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: SecretStr) -> SecretStr:
        """Validate API key format."""
        key = v.get_secret_value()
        if not key or len(key) < 30:
            raise ValueError("Invalid API key format")
        return v

    @field_validator("api_base_url", mode="before")
    @classmethod
    def validate_api_base_url(cls, v: object) -> str:
        """Reject malformed base URLs; warn on unknown-but-well-formed regions.

        A typo'd base URL otherwise surfaces much later as an opaque connection
        failure (#590). We require a well-formed http(s) URL with a host. A
        well-formed URL that is not a recognised Meraki region is accepted with
        a warning so custom proxies / future regions keep working (CFG-15).
        """
        if not isinstance(v, str):
            raise ValueError("api_base_url must be a string")
        url = v.strip()
        if not url:
            raise ValueError("api_base_url must not be empty")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"Invalid api_base_url {url!r}: must be a well-formed http(s) URL "
                "(e.g. https://api.meraki.com/api/v1)"
            )
        if url.rstrip("/") not in {u.rstrip("/") for u in KNOWN_REGION_BASE_URLS}:
            logger.warning(
                "api_base_url is not a recognised Meraki region base URL; "
                "proceeding anyway (custom/proxy endpoint)",
                api_base_url=url,
                known_regions=sorted(KNOWN_REGION_BASE_URLS),
            )
        return url

    @field_validator("org_id", mode="before")
    @classmethod
    def validate_org_id(cls, v: object) -> str | None:
        """Sanity-check org_id: reject empty/whitespace, warn on non-numeric.

        Meraki organization IDs are numeric strings; a non-numeric value is
        accepted (defensive - the format could change) but warned about so an
        obvious typo is visible at startup (#590 / CFG-04).
        """
        if v is None:
            return None
        org_id = str(v).strip()
        if not org_id:
            raise ValueError("org_id must not be empty or whitespace when set")
        if not org_id.isdigit():
            logger.warning(
                "org_id is not numeric; Meraki organization IDs are normally "
                "numeric - double-check for a typo",
                org_id=org_id,
            )
        return org_id


class NetworkFilterSettings(BaseModel):
    """Network-level filter for restricting which networks are scraped.

    All fields default to empty. If every field is empty, the filter is
    inactive and the exporter scrapes every network in every configured org
    (preserving pre-filter behaviour). Resolution semantics:

    - If any include_* field is non-empty, a network must match at least one
      include rule (across name OR id OR tag) to be considered.
    - If a network matches any exclude rule, it is dropped.
    - Names use glob patterns via fnmatch (case-sensitive).
    """

    # NoDecode disables pydantic-settings JSON-parsing of complex types so the
    # raw env-var string reaches our _split_csv validator. Without it, a value
    # like "prod-*,staging-*" raises SettingsError because it's not valid JSON.
    include_names: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Network name globs to include. Supports * and ? wildcards.",
    )
    include_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Exact network IDs (e.g. L_xxx) to include.",
    )
    include_tags: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=("Network tags to include. A network matches if it carries any of these tags."),
    )
    exclude_names: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Network name globs to exclude. Applied AFTER includes.",
    )
    exclude_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Exact network IDs to exclude.",
    )
    exclude_tags: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Network tags to exclude.",
    )

    @field_validator(
        "include_names",
        "include_ids",
        "include_tags",
        "exclude_names",
        "exclude_ids",
        "exclude_tags",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, v: object) -> list[str]:
        """Accept either a list or a comma-separated string from env vars.

        pydantic-settings does not auto-coerce csv -> list for nested
        BaseModel fields (only at the top BaseSettings boundary), so we
        normalise here.
        """
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            # Allow JSON-array form too (consistent with histogram_buckets).
            if stripped.startswith("[") and stripped.endswith("]"):
                import json

                parsed = json.loads(stripped)
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        raise ValueError(f"NetworkFilterSettings list field got unsupported type: {type(v)!r}")

    @model_validator(mode="after")
    def _validate_globs(self) -> NetworkFilterSettings:
        """Compile globs at config time so typos fail fast."""
        import fnmatch

        for field_name in ("include_names", "exclude_names"):
            for pattern in getattr(self, field_name):
                try:
                    fnmatch.translate(pattern)
                except Exception as exc:  # pragma: no cover - defensive
                    raise ValueError(
                        f"Invalid glob pattern in {field_name}: {pattern!r} ({exc})"
                    ) from exc
        return self

    @property
    def is_active(self) -> bool:
        """True iff any include or exclude rule is configured."""
        return bool(
            self.include_names
            or self.include_ids
            or self.include_tags
            or self.exclude_names
            or self.exclude_ids
            or self.exclude_tags
        )


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = Field(
        "INFO",
        description="Logging level (case-insensitive; normalised to upper-case)",
    )
    log_format: str = Field(
        "logfmt",
        description="Structured-log renderer: 'logfmt' (default) or 'json'.",
    )

    @field_validator("level", mode="before")
    @classmethod
    def _normalise_level(cls, v: object) -> str:
        """Accept case-insensitive log levels, normalising to upper-case (#598)."""
        if not isinstance(v, str):
            raise ValueError("Logging level must be a string")
        level = v.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(
                f"Invalid log level {v!r}. Must be one of {sorted(allowed)} (case-insensitive)"
            )
        return level

    @field_validator("log_format", mode="before")
    @classmethod
    def _normalise_log_format(cls, v: object) -> str:
        """Accept case-insensitive 'logfmt'/'json', normalising to lower-case (#310)."""
        if not isinstance(v, str):
            raise ValueError("log_format must be a string")
        fmt = v.strip().lower()
        allowed = {"logfmt", "json"}
        if fmt not in allowed:
            raise ValueError(
                f"Invalid log_format {v!r}. Must be one of {sorted(allowed)} (case-insensitive)"
            )
        return fmt


def _submodel_of(annotation: Any) -> type[BaseModel] | None:
    """Return the nested ``BaseModel`` subclass in an annotation, if any.

    Handles direct annotations (``MerakiSettings``) and unions
    (``MerakiSettings | None``); returns ``None`` for scalar/collection leaves
    so those become terminal env-var names.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    return None


def known_env_var_names(
    model_cls: type[BaseModel],
    *,
    prefix: str = "MERAKI_EXPORTER_",
    delimiter: str = "__",
) -> set[str]:
    """Compute the set of recognised (upper-cased) env-var names for a settings model.

    Recursively walks ``model_fields``, building ``PREFIX + path`` joined by the
    nested delimiter for every leaf field. Used to reconcile the observed
    environment against the schema so typo'd ``MERAKI_EXPORTER_*`` vars can be
    flagged at startup (#515).
    """
    names: set[str] = set()

    def _walk(cls: type[BaseModel], cur_prefix: str) -> None:
        for name, field in cls.model_fields.items():
            env_name = f"{cur_prefix}{name}".upper()
            sub = _submodel_of(field.annotation)
            if sub is not None:
                _walk(sub, f"{cur_prefix}{name}{delimiter}")
            else:
                names.add(env_name)

    _walk(model_cls, prefix)
    return names


def find_unrecognized_env_vars(
    environ: Mapping[str, str],
    model_cls: type[BaseModel],
    *,
    prefix: str = "MERAKI_EXPORTER_",
    delimiter: str = "__",
) -> list[str]:
    """Return ``MERAKI_EXPORTER_*`` env keys not recognised by the settings schema.

    Typo'd or unknown prefixed env vars are silently ignored by pydantic
    (``extra="ignore"``), so a misspelled setting looks applied but does nothing.
    This diffs the observed prefixed environment against the known field set and
    returns the offending original key names (values are never returned) so the
    caller can emit a startup WARN (#515). A ``<KNOWN>_FILE`` variant (the
    file-based secret convention, #587) is treated as recognised.
    """
    known = known_env_var_names(model_cls, prefix=prefix, delimiter=delimiter)
    upper_prefix = prefix.upper()
    unrecognized: list[str] = []
    for key in environ:
        upper = key.upper()
        if not upper.startswith(upper_prefix):
            continue
        if upper in known:
            continue
        # Accept the file-based secret convention: MERAKI_EXPORTER_..._FILE
        if upper.endswith("_FILE") and upper[: -len("_FILE")] in known:
            continue
        unrecognized.append(key)
    return sorted(unrecognized)
