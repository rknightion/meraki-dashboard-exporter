"""Configuration management for the Meraki Dashboard Exporter."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import DEFAULT_API_TIMEOUT, DEFAULT_MAX_RETRIES, MERAKI_API_BASE_URL


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_prefix="MERAKI_EXPORTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Allow MERAKI_API_KEY without prefix
        extra="ignore",
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
    api_max_retries: int = Field(
        DEFAULT_MAX_RETRIES,
        ge=0,
        le=10,
        description="Maximum number of retries for API requests",
    )

    # Scraping settings - Tiered update intervals
    fast_update_interval: int = Field(
        60,  # 1 minute
        ge=30,
        le=300,
        description="Interval for fast-moving data (sensors) in seconds",
        validation_alias="MERAKI_EXPORTER_FAST_UPDATE_INTERVAL",
    )
    medium_update_interval: int = Field(
        300,  # 5 minutes - aligns with Meraki API 5-minute data blocks
        ge=300,
        le=1800,
        description="Interval for medium-moving data (device metrics, org metrics) in seconds",
        validation_alias="MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL",
    )
    slow_update_interval: int = Field(
        900,  # 15 minutes
        ge=600,
        le=3600,
        description="Interval for slow-moving data (configuration, security settings) in seconds",
        validation_alias="MERAKI_EXPORTER_SLOW_UPDATE_INTERVAL",
    )
    api_timeout: int = Field(
        DEFAULT_API_TIMEOUT,
        ge=10,
        le=300,
        description="API request timeout in seconds",
    )

    # Legacy field for backwards compatibility
    @property
    def scrape_interval(self) -> int:
        """Legacy scrape interval property, returns fast update interval."""
        return self.fast_update_interval

    # Server settings
    host: str = Field("0.0.0.0", description="Host to bind the exporter to")  # nosec B104
    port: int = Field(9099, ge=1, le=65535, description="Port to bind the exporter to")

    # OpenTelemetry settings
    otel_enabled: bool = Field(False, description="Enable OpenTelemetry export")
    otel_endpoint: str | None = Field(
        None,
        description="OpenTelemetry collector endpoint",
    )
    otel_service_name: str = Field(
        "meraki-dashboard-exporter",
        description="Service name for OpenTelemetry",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO",
        description="Logging level",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: SecretStr) -> SecretStr:
        """Validate API key format."""
        key = v.get_secret_value()
        if not key or len(key) < 30:
            raise ValueError("Invalid API key format")
        return v

    @field_validator("otel_endpoint")
    @classmethod
    def validate_otel_endpoint(cls, v: str | None, info: Any) -> str | None:
        """Validate OTEL endpoint when OTEL is enabled."""
        if info.data.get("otel_enabled") and not v:
            raise ValueError("OTEL endpoint must be provided when OTEL is enabled")
        return v
