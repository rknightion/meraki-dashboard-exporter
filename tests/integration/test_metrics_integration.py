"""Integration tests for end-to-end metric collection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def test_registry():
    """Create a test-specific registry to avoid conflicts."""
    registry = CollectorRegistry()
    yield registry
    # Clean up
    registry._collector_to_names.clear()
    registry._names_to_collectors.clear()


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings for integration tests."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_ORG_ID", "123456")
    monkeypatch.setenv("MERAKI_EXPORTER_DEVICE_TYPES", '["MT", "MR", "MS"]')
    settings = Settings()
    return settings


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    mock_client = MagicMock(spec=AsyncMerakiClient)
    mock_api = MagicMock()
    mock_api.organizations = MagicMock()
    mock_api.networks = MagicMock()
    mock_api.wireless = MagicMock()
    mock_api.sensor = MagicMock()
    mock_api.switch = MagicMock()
    mock_client.api = mock_api
    return mock_client


class TestMetricsIntegration:
    """Test end-to-end metric collection flows."""

    @pytest.mark.asyncio
    async def test_full_collection_cycle(self, mock_api_client, monkeypatch):
        """Test a complete collection cycle with multiple collectors."""
        # Create settings without org_id for full testing
        monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
        monkeypatch.setenv("MERAKI_EXPORTER_DEVICE_TYPES", '["MT", "MR", "MS"]')
        # No org_id set
        mock_settings = Settings()

        # Use isolated registry
        isolated_registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

        # Mock organizations first (needed for collectors without org_id)
        mock_api_client.api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123456", "name": "Test Organization"}]
        )

        # Set up mock responses for organization collector
        mock_api_client.api.organizations.getOrganizationLicenses = MagicMock(
            return_value=[
                {"licenseType": "ENT", "state": "active", "expirationDate": "2025-01-01"},
                {"licenseType": "MR", "state": "expired", "expirationDate": "2024-01-01"},
            ]
        )

        mock_api_client.api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {"id": "N_123", "name": "Test Network", "productTypes": ["wireless", "switch"]}
            ]
        )

        mock_api_client.api.organizations.getOrganizationApiRequests = MagicMock(
            return_value=[
                {"method": "GET", "host": "api.meraki.com", "path": "/api/v1/organizations"},
                {"method": "POST", "host": "api.meraki.com", "path": "/api/v1/networks"},
            ]
        )

        # Set up mock responses for device collector
        mock_api_client.api.organizations.getOrganizationDevices = MagicMock(
            return_value=[
                {
                    "serial": "Q2KD-XXXX",
                    "name": "AP1",
                    "model": "MR36",
                    "status": "online",
                    "networkId": "N_123",
                },
                {
                    "serial": "Q2SW-XXXX",
                    "name": "Switch1",
                    "model": "MS120",
                    "status": "offline",
                    "networkId": "N_123",
                },
                {
                    "serial": "Q2MT-XXXX",
                    "name": "Sensor1",
                    "model": "MT10",
                    "status": "online",
                    "networkId": "N_123",
                },
            ]
        )

        # Mock switch port statuses
        mock_api_client.api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {"portId": "1", "enabled": True, "status": "Connected", "duplex": "full"},
                {"portId": "2", "enabled": True, "status": "Disconnected"},
            ]
        )

        # Mock MR client count
        mock_api_client.api.wireless.getDeviceWirelessStatus = MagicMock(
            return_value={"basicServiceSets": [{"ssidName": "Guest", "clientCount": 10}]}
        )

        # Mock sensor readings
        mock_api_client.api.sensor.getOrganizationSensorReadingsLatest = MagicMock(
            return_value=[
                {
                    "serial": "Q2MT-XXXX",
                    "readings": [
                        {"metric": "temperature", "celsius": 22.5},
                        {"metric": "humidity", "relativePercentage": 45.0},
                    ],
                }
            ]
        )

        # Mock alerts
        mock_api_client.api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            return_value=[
                {
                    "id": "alert1",
                    "type": "connectivity",
                    "categoryType": "network",
                    "severity": "critical",
                    "deviceType": "MR",
                    "network": {"id": "N_123", "name": "Test Network"},
                    "dismissedAt": None,
                    "resolvedAt": None,
                }
            ]
        )

        # Create collector manager
        manager = CollectorManager(client=mock_api_client, settings=mock_settings)

        # Run initial collection
        await manager.collect_initial()

        # Verify API calls were made for MEDIUM tier collectors
        mock_api_client.api.organizations.getOrganizationLicenses.assert_called()
        mock_api_client.api.organizations.getOrganizationDevices.assert_called()
        mock_api_client.api.organizations.getOrganizationAssuranceAlerts.assert_called()

        # Sensor collector is FAST tier, so it's not called during initial collection
        mock_api_client.api.sensor.getOrganizationSensorReadingsLatest.assert_not_called()

        # Now collect FAST tier to verify sensor collector
        from meraki_dashboard_exporter.core.constants import UpdateTier

        await manager.collect_tier(UpdateTier.FAST)

        # Sensor collector uses getOrganizationDevices with productTypes=["sensor"]
        # Just verify the FAST tier ran without errors

    @pytest.mark.asyncio
    async def test_tiered_collection(self, mock_api_client, mock_settings, monkeypatch):
        """Test that different tiers collect at appropriate intervals."""
        # Use isolated registry
        isolated_registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

        # Set up minimal mock responses
        mock_api_client.api.sensor.getOrganizationSensorReadingsLatest = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationApiRequests = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationDevices = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            return_value=[]
        )

        # Create collector manager
        manager = CollectorManager(client=mock_api_client, settings=mock_settings)

        # Collect FAST tier
        from meraki_dashboard_exporter.core.constants import UpdateTier

        await manager.collect_tier(UpdateTier.FAST)

        # Sensor collector calls getOrganizationDevices with productTypes=["sensor"]
        # Verify at least one call was made (sensor collector will call it)
        mock_api_client.api.organizations.getOrganizationDevices.assert_called()

        # License API should NOT be called for FAST tier
        mock_api_client.api.organizations.getOrganizationLicenses.assert_not_called()

        # Reset mocks
        mock_api_client.api.organizations.getOrganizationDevices.reset_mock()

        # Collect MEDIUM tier
        await manager.collect_tier(UpdateTier.MEDIUM)

        # Organization APIs should be called for MEDIUM tier
        mock_api_client.api.organizations.getOrganizationLicenses.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_continues_collection(
        self, mock_api_client, mock_settings, monkeypatch
    ):
        """Test that collection continues even if one collector fails."""
        # Use isolated registry
        isolated_registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

        # Make device collector fail
        mock_api_client.api.organizations.getOrganizationDevices = MagicMock(
            side_effect=Exception("API rate limit exceeded")
        )

        # Other collectors should work
        mock_api_client.api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationApiRequests = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            return_value=[]
        )

        # Create collector manager
        manager = CollectorManager(client=mock_api_client, settings=mock_settings)

        # Run collection - should not raise exception
        from meraki_dashboard_exporter.core.constants import UpdateTier

        await manager.collect_tier(UpdateTier.MEDIUM)

        # Verify other collectors were still called despite device collector failure
        mock_api_client.api.organizations.getOrganizationLicenses.assert_called()
        mock_api_client.api.organizations.getOrganizationAssuranceAlerts.assert_called()

    @pytest.mark.asyncio
    async def test_empty_device_types_configuration(self, mock_api_client, monkeypatch):
        """Test behavior when no device types are configured."""
        # Configure with empty device types
        monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
        monkeypatch.setenv("MERAKI_EXPORTER_DEVICE_TYPES", "[]")
        settings = Settings()

        # Use isolated registry
        isolated_registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

        # Set up mock responses
        mock_api_client.api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationApiRequests = MagicMock(return_value=[])
        mock_api_client.api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            return_value=[]
        )

        # Mock getOrganizations to return an org
        mock_api_client.api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )

        # Create collector manager
        manager = CollectorManager(client=mock_api_client, settings=settings)

        # Run collection
        await manager.collect_initial()

        # Organization collector should still run even with no device types
        mock_api_client.api.organizations.getOrganizationLicenses.assert_called()
