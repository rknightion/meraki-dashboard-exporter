"""Integration test for collector manager with registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.constants import UpdateTier


@pytest.fixture
def mock_client():
    """Create a mock Meraki client."""
    client = MagicMock()
    client.api = MagicMock()
    return client


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.update_intervals.fast = 60
    settings.update_intervals.medium = 300
    settings.update_intervals.slow = 900
    settings.organization_ids = ["123456"]
    return settings


class TestCollectorManagerIntegration:
    """Test collector manager with registry integration."""

    def setup_method(self) -> None:
        """Setup for each test."""
        # Don't clear registry in setup since collectors register on import
        pass

    def teardown_method(self) -> None:
        """Clear registry after each test."""
        # Note: This might affect other tests if they depend on registered collectors
        pass

    def test_manager_initializes_registered_collectors(self, mock_client, mock_settings):
        """Test that manager properly initializes all registered collectors."""
        # Create manager - this should auto-register all collectors
        manager = CollectorManager(mock_client, mock_settings)

        # Check that collectors were initialized for each tier
        assert len(manager.collectors[UpdateTier.FAST]) > 0
        assert len(manager.collectors[UpdateTier.MEDIUM]) > 0
        assert len(manager.collectors[UpdateTier.SLOW]) > 0

        # Verify specific collectors are present
        collector_names = {
            UpdateTier.FAST: ["MTSensorCollector"],
            UpdateTier.MEDIUM: [
                "OrganizationCollector",
                "DeviceCollector",
                "NetworkHealthCollector",
                "AlertsCollector",
            ],
            UpdateTier.SLOW: ["ConfigCollector"],
        }

        for tier, expected_names in collector_names.items():
            actual_names = [c.__class__.__name__ for c in manager.collectors[tier]]
            for name in expected_names:
                assert name in actual_names, f"{name} not found in {tier} tier"

    def test_manager_get_tier_interval(self, mock_client, mock_settings):
        """Test getting tier intervals."""
        manager = CollectorManager(mock_client, mock_settings)

        assert manager.get_tier_interval(UpdateTier.FAST) == 60
        assert manager.get_tier_interval(UpdateTier.MEDIUM) == 300
        assert manager.get_tier_interval(UpdateTier.SLOW) == 900

    def test_manager_register_additional_collector(self, mock_client, mock_settings):
        """Test registering an additional collector after initialization."""
        from meraki_dashboard_exporter.core.collector import MetricCollector

        # Create manager
        manager = CollectorManager(mock_client, mock_settings)
        initial_count = len(manager.collectors[UpdateTier.MEDIUM])

        # Create and register a new collector
        class TestCollector(MetricCollector):
            update_tier = UpdateTier.MEDIUM

            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        test_collector = TestCollector(mock_client.api, mock_settings)
        manager.register_collector(test_collector)

        # Verify it was added
        assert len(manager.collectors[UpdateTier.MEDIUM]) == initial_count + 1
        assert test_collector in manager.collectors[UpdateTier.MEDIUM]
