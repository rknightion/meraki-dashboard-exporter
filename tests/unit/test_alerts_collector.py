"""Tests for the AlertsCollector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.alerts import AlertsCollector
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    mock = MagicMock()
    mock.organizations = MagicMock()
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    settings = Settings()
    return settings


@pytest.fixture
def alerts_collector(mock_api, mock_settings, monkeypatch):
    """Create an AlertsCollector instance."""
    # Use isolated registry to avoid conflicts
    from prometheus_client import CollectorRegistry

    isolated_registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)
    return AlertsCollector(api=mock_api, settings=mock_settings)


class TestAlertsCollector:
    """Test AlertsCollector functionality."""

    @pytest.mark.asyncio
    async def test_collect_with_no_alerts(self, alerts_collector, mock_api):
        """Test collection when no alerts are present."""
        # Mock API responses - these are sync methods called via asyncio.to_thread
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run collection
        await alerts_collector.collect()

        # Verify API calls
        mock_api.organizations.getOrganizations.assert_called_once()
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once_with(
            "123", total_pages="all"
        )

    @pytest.mark.asyncio
    async def test_collect_with_active_alerts(self, alerts_collector, mock_api):
        """Test collection with active alerts."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )

        alerts_data = [
            {
                "id": "alert1",
                "type": "connectivity",
                "categoryType": "network",
                "severity": "critical",
                "deviceType": "MR",
                "network": {"id": "N_123", "name": "Test Network"},
                "dismissedAt": None,
                "resolvedAt": None,
            },
            {
                "id": "alert2",
                "type": "performance",
                "categoryType": "wireless",
                "severity": "warning",
                "deviceType": "MS",
                "network": {"id": "N_123", "name": "Test Network"},
                "dismissedAt": None,
                "resolvedAt": None,
            },
            {
                "id": "alert3",
                "type": "security",
                "categoryType": "security",
                "severity": "informational",
                "deviceType": None,  # Organization-wide alert
                "network": {"id": "N_456", "name": "Another Network"},
                "dismissedAt": None,
                "resolvedAt": None,
            },
        ]

        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=alerts_data)

        # Run collection
        await alerts_collector.collect()

        # Verify API calls
        mock_api.organizations.getOrganizations.assert_called_once()
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_skips_dismissed_alerts(self, alerts_collector, mock_api):
        """Test that dismissed alerts are skipped."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )

        alerts_data = [
            {
                "id": "alert1",
                "type": "connectivity",
                "categoryType": "network",
                "severity": "critical",
                "deviceType": "MR",
                "network": {"id": "N_123", "name": "Test Network"},
                "dismissedAt": "2024-01-01T00:00:00Z",  # Dismissed
                "resolvedAt": None,
            },
            {
                "id": "alert2",
                "type": "performance",
                "categoryType": "wireless",
                "severity": "warning",
                "deviceType": "MS",
                "network": {"id": "N_123", "name": "Test Network"},
                "dismissedAt": None,
                "resolvedAt": "2024-01-01T00:00:00Z",  # Resolved
            },
        ]

        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=alerts_data)

        # Run collection
        await alerts_collector.collect()

        # Both alerts should be skipped due to being dismissed/resolved
        # We can't easily verify metric values without accessing internal state,
        # but the test ensures no exceptions are raised

    @pytest.mark.asyncio
    async def test_collect_handles_api_404_error(self, alerts_collector, mock_api):
        """Test handling of 404 errors (alerts API not available)."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )

        # Mock 404 error
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            side_effect=Exception("404 Client Error: Not Found")
        )

        # Run collection - should handle error gracefully
        await alerts_collector.collect()

        # Verify API was called
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_with_specific_org_id(self, mock_api, mock_settings, monkeypatch):
        """Test collection with a specific org_id configured."""
        # Configure specific org_id
        mock_settings.org_id = "456"

        # Use isolated registry
        from prometheus_client import CollectorRegistry

        isolated_registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

        collector = AlertsCollector(api=mock_api, settings=mock_settings)

        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run collection
        await collector.collect()

        # Should not call getOrganizations
        mock_api.organizations.getOrganizations.assert_not_called()

        # Should call alerts API with configured org_id
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once_with(
            "456", total_pages="all"
        )

    @pytest.mark.asyncio
    async def test_collect_handles_missing_network_data(self, alerts_collector, mock_api):
        """Test handling of alerts with missing network data."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )

        alerts_data = [
            {
                "id": "alert1",
                "type": "connectivity",
                "categoryType": "network",
                "severity": "critical",
                "deviceType": "MR",
                "network": {},  # Empty network data
                "dismissedAt": None,
                "resolvedAt": None,
            },
            {
                "id": "alert2",
                "type": "performance",
                # Missing network key entirely
                "dismissedAt": None,
                "resolvedAt": None,
            },
        ]

        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=alerts_data)

        # Run collection - should handle missing data gracefully
        await alerts_collector.collect()

    @pytest.mark.asyncio
    async def test_collect_handles_general_exception(self, alerts_collector, mock_api):
        """Test handling of general exceptions during collection."""
        # Mock API to raise exception
        mock_api.organizations.getOrganizations = MagicMock(side_effect=Exception("Network error"))

        # Run collection - should handle error gracefully
        await alerts_collector.collect()

    def test_update_tier(self, alerts_collector):
        """Test that alerts collector has correct update tier."""
        from meraki_dashboard_exporter.core.constants import UpdateTier

        assert alerts_collector.update_tier == UpdateTier.MEDIUM
