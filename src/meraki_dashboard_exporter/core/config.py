"""Configuration management for the Meraki Dashboard Exporter."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import DEFAULT_API_TIMEOUT, DEFAULT_SCRAPE_INTERVAL


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

    # Scraping settings
    scrape_interval: int = Field(
        DEFAULT_SCRAPE_INTERVAL,
        ge=60,
        le=3600,
        description="Interval between metric scrapes in seconds",
    )
    api_timeout: int = Field(
        DEFAULT_API_TIMEOUT,
        ge=10,
        le=300,
        description="API request timeout in seconds",
    )

    # Server settings
    host: str = Field("0.0.0.0", description="Host to bind the exporter to")
    port: int = Field(9090, ge=1, le=65535, description="Port to bind the exporter to")

    # Device types to collect metrics for
    device_types: list[Literal["MS", "MR", "MV", "MT", "MX", "MG"]] = Field(
        ["MS", "MR", "MV", "MT"],
        description="Device types to collect metrics for",
    )

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
    def validate_otel_endpoint(cls, v: str | None, info) -> str | None:
        """Validate OTEL endpoint when OTEL is enabled."""
        if info.data.get("otel_enabled") and not v:
            raise ValueError("OTEL endpoint must be provided when OTEL is enabled")
        return v
