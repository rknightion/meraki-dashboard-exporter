"""Configuration management for the Meraki Dashboard Exporter."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_models import (
    APISettings,
    ClientSettings,
    CollectorSettings,
    LoggingSettings,
    MerakiSettings,
    MonitoringSettings,
    OTelSettings,
    ServerSettings,
    SNMPSettings,
    UpdateIntervals,
)


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

    # Nested configuration models
    meraki: MerakiSettings = Field(
        ...,
        description="Meraki API configuration",
    )
    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
        description="Logging configuration",
    )
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
    clients: ClientSettings = Field(
        default_factory=ClientSettings,
        description="Client data collection settings",
    )
    snmp: SNMPSettings = Field(
        default_factory=SNMPSettings,
        description="SNMP collector settings",
    )

    @model_validator(mode="after")
    def validate_regional_settings(self) -> Settings:
        """Validate settings based on API region."""
        # If using a regional endpoint, ensure appropriate timeouts
        if "china" in self.meraki.api_base_url.lower() and self.api.timeout < 45:
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
            "meraki": {
                "org_id": self.meraki.org_id,
                "api_base_url": self.meraki.api_base_url,
            },
            "logging": self.logging.model_dump(),
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
            "snmp": {
                "enabled": self.snmp.enabled,
                "timeout": self.snmp.timeout,
                "retries": self.snmp.retries,
            },
        }
