"""Nested configuration models for better organization."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


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
        2.0,
        ge=0.5,
        le=10.0,
        description="DNS lookup timeout in seconds",
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


class ConfigurationProfile(BaseModel):
    """Configuration profile for different deployment scenarios."""

    name: str = Field(description="Profile name")
    description: str = Field(description="Profile description")
    api: APISettings = Field(default_factory=APISettings)
    update_intervals: UpdateIntervals = Field(default_factory=UpdateIntervals)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    collectors: CollectorSettings = Field(default_factory=CollectorSettings)
    clients: ClientSettings = Field(default_factory=ClientSettings)


# Predefined configuration profiles
PROFILES: dict[str, ConfigurationProfile] = {
    "development": ConfigurationProfile(
        name="development",
        description="Development environment with relaxed limits",
        api=APISettings(
            max_retries=1,
            timeout=60,
            concurrency_limit=2,
            batch_size=5,
        ),
        update_intervals=UpdateIntervals(
            fast=60,
            medium=300,
            slow=900,
        ),
        monitoring=MonitoringSettings(
            max_consecutive_failures=3,
            histogram_buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        ),
    ),
    "production": ConfigurationProfile(
        name="production",
        description="Production environment with standard settings",
        api=APISettings(
            max_retries=3,
            timeout=30,
            concurrency_limit=5,
            batch_size=10,
        ),
        update_intervals=UpdateIntervals(
            fast=60,
            medium=300,
            slow=900,
        ),
        monitoring=MonitoringSettings(),
    ),
    "high_volume": ConfigurationProfile(
        name="high_volume",
        description="High volume environment with aggressive settings",
        api=APISettings(
            max_retries=5,
            timeout=45,
            concurrency_limit=10,
            batch_size=20,
            batch_delay=1.0,
        ),
        update_intervals=UpdateIntervals(
            fast=120,
            medium=600,
            slow=1800,
        ),
        monitoring=MonitoringSettings(
            max_consecutive_failures=20,
            license_expiration_warning_days=60,
        ),
        collectors=CollectorSettings(
            collector_timeout=300,
        ),
    ),
    "minimal": ConfigurationProfile(
        name="minimal",
        description="Minimal configuration for testing",
        api=APISettings(
            concurrency_limit=1,
            batch_size=1,
        ),
        update_intervals=UpdateIntervals(
            fast=300,
            medium=600,
            slow=1800,
        ),
        collectors=CollectorSettings(
            enabled_collectors={"device", "organization"},
        ),
    ),
}
