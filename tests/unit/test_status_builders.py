"""Tests for the /status enrichment builders.

Covers network-filter state (#311), webhook health (#317), and the redacted
effective-config view (#312).
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Gauge
from pydantic import SecretStr

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import (
    MerakiSettings,
    NetworkFilterSettings,
    WebhookSettings,
)
from meraki_dashboard_exporter.core.constants.metrics_constants import NetworkMetricName
from meraki_dashboard_exporter.core.webhook_handler import WebhookHandler
from meraki_dashboard_exporter.services.status import (
    build_effective_config,
    build_network_filter_status,
    build_webhook_status,
)

RAW_KEY = "supersecret_api_key_at_least_30_characters_long"
RAW_SECRET = "webhook_shared_secret_value_123"


def _settings(**kwargs: object) -> Settings:
    return Settings(
        meraki=MerakiSettings(api_key=SecretStr(RAW_KEY), org_id="123456"),
        **kwargs,  # type: ignore[arg-type]
    )


class TestBuildNetworkFilterStatus:
    """#311 - surface effective NetworkFilter state."""

    def test_inactive_filter_reports_empty_rules(self) -> None:
        """Inactive filter reports empty rules."""
        status = build_network_filter_status(_settings(), registry=CollectorRegistry())
        assert status.is_active is False
        assert status.include_names == []
        assert status.exclude_tags == []
        assert status.per_org == []

    def test_active_filter_surfaces_parsed_rules(self) -> None:
        """Active filter surfaces parsed rules."""
        settings = _settings(
            network_filter=NetworkFilterSettings(
                include_names=["prod-*", "staging-*"],
                exclude_tags=["decommissioned"],
            )
        )
        status = build_network_filter_status(settings, registry=CollectorRegistry())
        assert status.is_active is True
        assert status.include_names == ["prod-*", "staging-*"]
        assert status.exclude_tags == ["decommissioned"]

    def test_per_org_counts_read_from_gauges(self) -> None:
        """Per org counts read from gauges."""
        registry = CollectorRegistry()
        total = Gauge(
            NetworkMetricName.NETWORK_FILTER_NETWORKS.value,
            "total",
            ["org_id"],
            registry=registry,
        )
        resolved = Gauge(
            NetworkMetricName.NETWORK_FILTER_RESOLVED.value,
            "resolved",
            ["org_id"],
            registry=registry,
        )
        total.labels(org_id="123456").set(10)
        resolved.labels(org_id="123456").set(3)

        status = build_network_filter_status(_settings(), registry=registry)
        assert status.per_org == [
            {"org_id": "123456", "total_networks": 10, "resolved_networks": 3}
        ]


class TestBuildWebhookStatus:
    """#317 - surface webhook receiver health."""

    def test_none_when_disabled(self) -> None:
        """None when disabled."""
        settings = _settings(webhooks=WebhookSettings(enabled=False))
        assert build_webhook_status(None, settings) is None

    def test_populated_from_handler(self) -> None:
        """Populated from handler."""
        settings = _settings(
            webhooks=WebhookSettings(
                enabled=True,
                shared_secret=SecretStr(RAW_SECRET),
                require_secret=True,
            )
        )
        handler = WebhookHandler(settings)
        handler.record_validation_failure("invalid_json")

        status = build_webhook_status(handler, settings, now=1000.0)
        assert status is not None
        assert status.enabled is True
        assert status.require_secret is True
        assert status.validation_failures == 1
        assert status.last_event_time is None
        assert status.last_event_ago == "Never"


class TestBuildEffectiveConfig:
    """#312 - redacted effective-config view."""

    def test_secrets_masked_and_config_resolved(self) -> None:
        """Secrets masked and config resolved."""
        settings = _settings(
            webhooks=WebhookSettings(
                enabled=True,
                shared_secret=SecretStr(RAW_SECRET),
                require_secret=True,
            )
        )
        config = build_effective_config(settings)

        # Secrets masked.
        assert config["meraki"]["api_key"] == "**********"
        assert config["webhooks"]["shared_secret"] == "**********"
        # Raw secret values never appear anywhere in the dumped view.
        flat = repr(config)
        assert RAW_KEY not in flat
        assert RAW_SECRET not in flat
        # Non-secret resolved values present.
        assert config["meraki"]["org_id"] == "123456"
        assert config["webhooks"]["enabled"] is True
