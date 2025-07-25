"""Nested configuration models for better organization."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


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
        description="Maximum concurrent API requests",
    )
    batch_size: int = Field(
        10,
        ge=1,
        le=50,
        description="Default batch size for API operations",
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
        description="Enable OpenTelemetry export",
    )
    endpoint: str | None = Field(
        None,
        description="OpenTelemetry collector endpoint",
    )
    service_name: str = Field(
        "meraki-dashboard-exporter",
        description="Service name for OpenTelemetry",
    )
    export_interval: int = Field(
        60,
        ge=10,
        le=300,
        description="Export interval for OpenTelemetry metrics",
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
    path_prefix: str = Field(
        "",
        description="URL path prefix for all endpoints",
    )
    enable_health_check: bool = Field(
        True,
        description="Enable /health endpoint",
    )


class CollectorSettings(BaseModel):
    """Collector-specific settings."""

    enabled_collectors: set[str] = Field(
        default_factory=lambda: {
            "alerts",
            "config",
            "device",
            "mt_sensor",
            "network_health",
            "organization",
        },
        description="Enabled collector names",
    )
    disable_collectors: set[str] = Field(
        default_factory=set,
        description="Explicitly disabled collectors (overrides enabled)",
    )
    collector_timeout: int = Field(
        120,
        ge=30,
        le=600,
        description="Timeout for individual collector runs in seconds",
    )

    @property
    def active_collectors(self) -> set[str]:
        """Get the final set of active collectors."""
        return self.enabled_collectors - self.disable_collectors


class ClientSettings(BaseModel):
    """Client data collection settings."""

    enabled: bool = Field(
        False,
        description="Enable client data collection",
    )
    dns_server: str | None = Field(
        None,
        description="DNS server for reverse lookups (uses system default if not set)",
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


class SNMPSettings(BaseModel):
    """SNMP collector configuration."""

    enabled: bool = Field(
        False,
        description="Enable SNMP metric collection",
    )
    timeout: float = Field(
        5.0,
        ge=1.0,
        le=30.0,
        description="SNMP request timeout in seconds",
    )
    retries: int = Field(
        3,
        ge=1,
        le=10,
        description="SNMP request retry count",
    )
    bulk_max_repetitions: int = Field(
        25,
        ge=10,
        le=100,
        description="Maximum repetitions for SNMP BULK operations",
    )
    concurrent_device_limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum concurrent SNMP device queries",
    )
    org_v3_auth_password: SecretStr | None = Field(
        None,
        description="SNMPv3 authentication password for organization/cloud controller SNMP",
    )
    org_v3_priv_password: SecretStr | None = Field(
        None,
        description="SNMPv3 privacy password for organization/cloud controller SNMP",
    )


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = Field(
        "INFO",
        description="Logging level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
