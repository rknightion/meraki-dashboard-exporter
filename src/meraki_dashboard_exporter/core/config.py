"""Configuration management for the Meraki Dashboard Exporter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_models import (
    APISettings,
    CardinalitySettings,
    ClientSettings,
    CollectorSettings,
    LoggingSettings,
    MerakiSettings,
    MonitoringSettings,
    NetworkFilterSettings,
    OTelSettings,
    ServerSettings,
    UpdateIntervals,
    WebhookSettings,
    find_unrecognized_env_vars,
)
from .config_sources import FileSecretsSettingsSource
from .logging import get_logger

if TYPE_CHECKING:
    from pydantic_settings import PydanticBaseSettingsSource

logger = get_logger(__name__)


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
    webhooks: WebhookSettings = Field(
        default_factory=WebhookSettings,
        description="Webhook receiver settings",
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
    cardinality: CardinalitySettings = Field(
        default_factory=CardinalitySettings,
        description="Metric cardinality guard-rail settings",
    )
    clients: ClientSettings = Field(
        default_factory=ClientSettings,
        description="Client data collection settings",
    )
    network_filter: NetworkFilterSettings = Field(
        default_factory=NetworkFilterSettings,
        description="Network-level filter for restricting which networks are scraped",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add the ``<ENV_VAR>_FILE`` secret source (#587).

        The file-based secret source is placed **below** ``env_settings`` (and
        ``dotenv_settings``) so a directly-set env var still wins over a mounted
        secret file. See :mod:`.config_sources`.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            FileSecretsSettingsSource(settings_cls),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def validate_regional_settings(self) -> Settings:
        """Validate settings based on API region."""
        # If using a regional endpoint, ensure appropriate timeouts. The canonical
        # China host is api.meraki.cn, so match on "meraki.cn" (the old "china"
        # substring never matched the real base URL) (#518).
        if "meraki.cn" in self.meraki.api_base_url.lower() and self.api.timeout < 45:
            # China region typically needs longer timeouts
            self.api.timeout = 45
        return self

    @model_validator(mode="after")
    def warn_unrecognized_env_vars(self) -> Settings:
        """Emit a WARN for each unknown ``MERAKI_EXPORTER_*`` env var (#515).

        ``extra="ignore"`` silently drops typo'd prefixed env vars, so a
        misspelled setting looks applied but does nothing. Surface them once at
        startup. Values are never logged.
        """
        for key in find_unrecognized_env_vars(os.environ, type(self)):
            logger.warning(
                "Ignoring unrecognized MERAKI_EXPORTER_* environment variable "
                "(check for a typo; value not logged)",
                env_var=key,
            )
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
            "network_filter": {
                "is_active": self.network_filter.is_active,
                "include_names": self.network_filter.include_names,
                "include_ids": self.network_filter.include_ids,
                "include_tags": self.network_filter.include_tags,
                "exclude_names": self.network_filter.exclude_names,
                "exclude_ids": self.network_filter.exclude_ids,
                "exclude_tags": self.network_filter.exclude_tags,
            },
        }
