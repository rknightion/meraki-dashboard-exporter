"""Nested configuration models for better organization."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import NoDecode


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
        description="API request timeout in seconds",
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
        1.0,
        ge=0.1,
        le=1.0,
        description="Fraction of org call budget reserved for this exporter",
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
    max_payload_size: int = Field(
        1024 * 1024,  # 1MB
        ge=1024,
        le=10 * 1024 * 1024,  # 10MB max
        description="Maximum webhook payload size in bytes",
    )


class CollectorSettings(BaseModel):
    """Collector-specific settings."""

    enabled_collectors: set[str] = Field(
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
    disable_collectors: set[str] = Field(
        default_factory=set,
        description="Explicitly disabled collectors (overrides enabled)",
    )
    collector_timeout: int = Field(
        240,
        ge=30,
        le=600,
        description="Timeout for individual collector runs in seconds",
    )

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


class MerakiSettings(BaseModel):
    """Meraki API configuration."""

    api_key: SecretStr = Field(
        ...,
        description="Meraki Dashboard API key",
    )
    org_id: str | None = Field(
        None,
        description="Meraki organization ID (optional, will fetch all orgs if not set)",
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
        description="Logging level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
