"""Integration test for collector manager with registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_client():
    """Create a mock Meraki client."""
    client = MagicMock()
    client.api = MagicMock()
    return client


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Create real settings with defaults for testing."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    return Settings()


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

        # Collectors are now a flat list (tiers removed, #631).
        assert len(manager.collectors) > 0

        # Verify specific collectors are present regardless of cadence.
        actual_names = {c.__class__.__name__ for c in manager.collectors}
        for name in (
            "MTSensorCollector",
            "OrganizationCollector",
            "DeviceCollector",
            "NetworkHealthCollector",
            "AlertsCollector",
            "ConfigCollector",
        ):
            assert name in actual_names, f"{name} not found in collectors"

    def test_manager_register_additional_collector(self, mock_client, mock_settings):
        """Test registering an additional collector after initialization."""
        from meraki_dashboard_exporter.core.collector import MetricCollector

        # Create manager
        manager = CollectorManager(mock_client, mock_settings)
        initial_count = len(manager.collectors)

        # Create and register a new collector
        class TestCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        test_collector = TestCollector(mock_client.api, mock_settings)
        manager.register_collector(test_collector)

        # Verify it was added to the flat collector list.
        assert len(manager.collectors) == initial_count + 1
        assert test_collector in manager.collectors
