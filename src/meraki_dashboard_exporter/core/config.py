"""Configuration management for the Meraki Dashboard Exporter."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_models import (
    PROFILES,
    APISettings,
    CollectorSettings,
    MonitoringSettings,
    OTelSettings,
    ServerSettings,
    UpdateIntervals,
)
from .constants import MERAKI_API_BASE_URL


class Settings(BaseSettings):
    """Application settings with nested configuration models."""

    model_config = SettingsConfigDict(
        env_prefix="MERAKI_EXPORTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",  # Allow MERAKI_EXPORTER_API__TIMEOUT
        extra="ignore",
    )

    # Profile selection
    profile: str | None = Field(
        None,
        description="Configuration profile to use (development, production, high_volume, minimal)",
    )

    # Meraki API settings - special handling for MERAKI_API_KEY without prefix
    api_key: Annotated[
        SecretStr,
        Field(
            ...,
            description="Meraki Dashboard API key",
            validation_alias="MERAKI_API_KEY",
        ),
    ]
    org_id: str | None = Field(
        None,
        description="Meraki organization ID (optional, will fetch all orgs if not set)",
    )
    api_base_url: str = Field(
        MERAKI_API_BASE_URL,
        description="Meraki API base URL (use regional endpoints if needed)",
    )

    # Nested configuration models
    api: APISettings = Field(
        default_factory=APISettings,
        description="API-related settings",
    )
    update_intervals: UpdateIntervals = Field(
        default_factory=UpdateIntervals,
        description="Update interval settings",
    )
    server: ServerSettings = Field(
        default_factory=ServerSettings,
        description="HTTP server settings",
    )
    otel: OTelSettings = Field(
        default_factory=OTelSettings,
        description="OpenTelemetry settings",
    )
    monitoring: MonitoringSettings = Field(
        default_factory=MonitoringSettings,
        description="Monitoring and observability settings",
    )
    collectors: CollectorSettings = Field(
        default_factory=CollectorSettings,
        description="Collector-specific settings",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO",
        description="Logging level",
    )

    # Computed properties for backward compatibility
    @property
    def api_max_retries(self) -> int:
        """Legacy property for API max retries."""
        return self.api.max_retries

    @property
    def api_timeout(self) -> int:
        """Legacy property for API timeout."""
        return self.api.timeout

    @property
    def fast_update_interval(self) -> int:
        """Fast update interval in seconds."""
        return self.update_intervals.fast

    @property
    def medium_update_interval(self) -> int:
        """Medium update interval in seconds."""
        return self.update_intervals.medium

    @property
    def slow_update_interval(self) -> int:
        """Slow update interval in seconds."""
        return self.update_intervals.slow

    @property
    def scrape_interval(self) -> int:
        """Legacy scrape interval property, returns fast update interval."""
        return self.update_intervals.fast

    @property
    def host(self) -> str:
        """Server host."""
        return self.server.host

    @property
    def port(self) -> int:
        """Server port."""
        return self.server.port

    @property
    def otel_enabled(self) -> bool:
        """Whether OpenTelemetry is enabled."""
        return self.otel.enabled

    @property
    def otel_endpoint(self) -> str | None:
        """OpenTelemetry endpoint."""
        return self.otel.endpoint

    @property
    def otel_service_name(self) -> str:
        """OpenTelemetry service name."""
        return self.otel.service_name

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: SecretStr) -> SecretStr:
        """Validate API key format."""
        key = v.get_secret_value()
        if not key or len(key) < 30:
            raise ValueError("Invalid API key format")
        return v

    @model_validator(mode="before")
    @classmethod
    def apply_profile(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Apply configuration profile if specified."""
        profile_name = values.get("profile")
        if profile_name and profile_name in PROFILES:
            profile = PROFILES[profile_name]
            # Apply profile defaults (can be overridden by env vars)
            if "api" not in values:
                values["api"] = profile.api.model_dump()
            if "update_intervals" not in values:
                values["update_intervals"] = profile.update_intervals.model_dump()
            if "monitoring" not in values:
                values["monitoring"] = profile.monitoring.model_dump()
            if "collectors" not in values:
                values["collectors"] = profile.collectors.model_dump()
        return values

    @model_validator(mode="after")
    def validate_regional_settings(self) -> Settings:
        """Validate settings based on API region."""
        # If using a regional endpoint, ensure appropriate timeouts
        if "china" in self.api_base_url.lower() and self.api.timeout < 45:
            # China region typically needs longer timeouts
            self.api.timeout = 45
        return self

    def get_collector_config(self, collector_name: str) -> dict[str, Any]:
        """Get configuration specific to a collector.

        Parameters
        ----------
        collector_name : str
            Name of the collector.

        Returns
        -------
        dict[str, Any]
            Collector-specific configuration.

        """
        # Future: Can add collector-specific overrides here
        return {
            "enabled": collector_name in self.collectors.active_collectors,
            "timeout": self.collectors.collector_timeout,
        }

    def to_summary(self) -> dict[str, Any]:
        """Get a summary of the configuration (safe for logging).

        Returns
        -------
        dict[str, Any]
            Configuration summary without sensitive data.

        """
        return {
            "profile": self.profile,
            "org_id": self.org_id,
            "api_base_url": self.api_base_url,
            "api": self.api.model_dump(),
            "update_intervals": self.update_intervals.model_dump(),
            "server": self.server.model_dump(),
            "otel": {
                "enabled": self.otel.enabled,
                "endpoint": self.otel.endpoint,
                "service_name": self.otel.service_name,
            },
            "monitoring": self.monitoring.model_dump(),
            "collectors": {
                "active": sorted(self.collectors.active_collectors),
                "timeout": self.collectors.collector_timeout,
            },
            "log_level": self.log_level,
        }
