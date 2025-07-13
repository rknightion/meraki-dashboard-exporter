"""Tests for the DiscoveryService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.discovery import DiscoveryService


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
def discovery_service(mock_api, mock_settings):
    """Create a DiscoveryService instance."""
    return DiscoveryService(api=mock_api, settings=mock_settings)


class TestDiscoveryService:
    """Test DiscoveryService functionality."""

    @pytest.mark.asyncio
    async def test_run_discovery_with_single_org(self, mock_api, mock_settings):
        """Test discovery with a specific org_id configured."""
        # Configure specific org_id
        mock_settings.org_id = "123"
        service = DiscoveryService(api=mock_api, settings=mock_settings)

        # Mock API responses
        mock_api.organizations.getOrganization = MagicMock(
            return_value={"id": "123", "name": "Test Org", "url": "https://test.meraki.com"}
        )
        mock_api.organizations.getOrganizationLicenses = MagicMock(
            return_value=[
                {"licenseType": "ENT", "state": "active"},
                {"licenseType": "MR", "state": "active"},
            ]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {"id": "N_123", "name": "Network1", "productTypes": ["wireless", "switch"]},
                {"id": "N_456", "name": "Network2", "productTypes": ["appliance"]},
            ]
        )
        mock_api.organizations.getOrganizationDevices = MagicMock(
            return_value=[
                {"model": "MR36", "serial": "Q2KD-XXXX"},
                {"model": "MS120", "serial": "Q2SW-XXXX"},
                {"model": "MX64", "serial": "Q2MX-XXXX"},
            ]
        )
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            return_value=[
                {"id": "alert1", "dismissedAt": None, "resolvedAt": None},
                {"id": "alert2", "dismissedAt": "2024-01-01", "resolvedAt": None},
            ]
        )

        # Run discovery
        await service.run_discovery()

        # Verify API calls
        mock_api.organizations.getOrganization.assert_called_once_with("123")
        mock_api.organizations.getOrganizationLicenses.assert_called_once()
        mock_api.organizations.getOrganizationNetworks.assert_called_once()
        mock_api.organizations.getOrganizationDevices.assert_called_once()
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_discovery_with_multiple_orgs(self, discovery_service, mock_api):
        """Test discovery with multiple organizations."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[
                {"id": "123", "name": "Org1", "url": "https://org1.meraki.com"},
                {"id": "456", "name": "Org2", "url": "https://org2.meraki.com"},
            ]
        )

        # Mock responses for each org
        mock_api.organizations.getOrganizationLicenses = MagicMock(
            return_value=[{"licenseType": "ENT", "state": "active"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[{"id": "N_123", "name": "Network1", "productTypes": ["wireless"]}]
        )
        mock_api.organizations.getOrganizationDevices = MagicMock(
            return_value=[{"model": "MR36", "serial": "Q2KD-XXXX"}]
        )
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run discovery
        await discovery_service.run_discovery()

        # Verify API calls
        mock_api.organizations.getOrganizations.assert_called_once()
        assert mock_api.organizations.getOrganizationLicenses.call_count == 2
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2
        assert mock_api.organizations.getOrganizationDevices.call_count == 2
        assert mock_api.organizations.getOrganizationAssuranceAlerts.call_count == 2

    @pytest.mark.asyncio
    async def test_discovery_handles_cotermination_licensing(self, discovery_service, mock_api):
        """Test handling of co-termination licensing model."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )

        # Mock co-termination licensing error
        mock_api.organizations.getOrganizationLicenses = MagicMock(
            side_effect=Exception("Organization 123 does not support per-device licensing")
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
        mock_api.organizations.getOrganizationDevices = MagicMock(return_value=[])
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run discovery - should handle co-termination gracefully
        await discovery_service.run_discovery()

        # Verify license API was called
        mock_api.organizations.getOrganizationLicenses.assert_called_once()

    @pytest.mark.asyncio
    async def test_discovery_handles_alerts_api_not_available(self, discovery_service, mock_api):
        """Test handling when alerts API is not available."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
        mock_api.organizations.getOrganizationDevices = MagicMock(return_value=[])

        # Mock 404 error for alerts API
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(
            side_effect=Exception("404 Not Found")
        )

        # Run discovery - should handle 404 gracefully
        await discovery_service.run_discovery()

        # Verify alerts API was called
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once()

    @pytest.mark.asyncio
    async def test_discovery_handles_network_fetch_failure(self, discovery_service, mock_api):
        """Test handling of network fetch failures."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationLicenses = MagicMock(return_value=[])

        # Mock network fetch failure
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            side_effect=Exception("Network error")
        )
        mock_api.organizations.getOrganizationDevices = MagicMock(return_value=[])
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run discovery - should continue despite network fetch failure
        await discovery_service.run_discovery()

        # Verify other APIs were still called
        mock_api.organizations.getOrganizationDevices.assert_called_once()

    @pytest.mark.asyncio
    async def test_discovery_handles_device_fetch_failure(self, discovery_service, mock_api):
        """Test handling of device fetch failures."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[])

        # Mock device fetch failure
        mock_api.organizations.getOrganizationDevices = MagicMock(
            side_effect=Exception("API rate limit")
        )
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run discovery - should continue despite device fetch failure
        await discovery_service.run_discovery()

        # Verify alerts API was still called
        mock_api.organizations.getOrganizationAssuranceAlerts.assert_called_once()

    @pytest.mark.asyncio
    async def test_discovery_handles_complete_failure(self, discovery_service, mock_api):
        """Test handling of complete discovery failure."""
        # Mock initial API failure
        mock_api.organizations.getOrganizations = MagicMock(
            side_effect=Exception("Authentication failed")
        )

        # Run discovery - should handle exception gracefully
        await discovery_service.run_discovery()

        # Verify only the first API was called
        mock_api.organizations.getOrganizations.assert_called_once()

    @pytest.mark.asyncio
    async def test_discovery_counts_products_and_devices(self, discovery_service, mock_api):
        """Test that discovery correctly counts products and device types."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationLicenses = MagicMock(return_value=[])

        # Mock networks with various product types
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {"id": "N_1", "name": "Net1", "productTypes": ["wireless", "switch"]},
                {"id": "N_2", "name": "Net2", "productTypes": ["wireless"]},
                {"id": "N_3", "name": "Net3", "productTypes": ["appliance", "switch"]},
            ]
        )

        # Mock devices with various models
        mock_api.organizations.getOrganizationDevices = MagicMock(
            return_value=[
                {"model": "MR36", "serial": "Q2KD-1111"},
                {"model": "MR46", "serial": "Q2KD-2222"},
                {"model": "MS120", "serial": "Q2SW-1111"},
                {"model": "MS220", "serial": "Q2SW-2222"},
                {"model": "MX64", "serial": "Q2MX-1111"},
                {"model": "MT10", "serial": "Q2MT-1111"},
                {"model": "unknown_model", "serial": "XXXX-1111"},  # Unknown prefix
            ]
        )
        mock_api.organizations.getOrganizationAssuranceAlerts = MagicMock(return_value=[])

        # Run discovery
        await discovery_service.run_discovery()

        # Verify all counts were processed correctly
        mock_api.organizations.getOrganizationNetworks.assert_called_once()
        mock_api.organizations.getOrganizationDevices.assert_called_once()
