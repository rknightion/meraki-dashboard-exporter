"""Tests for the DiscoveryService using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.discovery import DiscoveryService
from tests.helpers.factories import NetworkFactory, OrganizationFactory


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    return settings


@pytest.fixture
def discovery_service(mock_api, mock_settings):
    """Create a DiscoveryService instance."""
    return DiscoveryService(api=mock_api, settings=mock_settings)


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    mock = MagicMock()
    mock.organizations = MagicMock()
    return mock


class TestDiscoveryService:
    """Test DiscoveryService functionality."""

    @pytest.mark.asyncio
    async def test_run_discovery_with_single_org(self, mock_api, mock_settings):
        """Test discovery with a specific org_id configured."""
        mock_settings.meraki.org_id = "123"
        service = DiscoveryService(api=mock_api, settings=mock_settings)

        org = OrganizationFactory.create(org_id="123", name="Test Org")
        networks = [
            NetworkFactory.create(
                network_id="N_123",
                name="Network1",
                product_types=["wireless", "switch"],
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_456",
                name="Network2",
                product_types=["appliance"],
                org_id=org["id"],
            ),
        ]

        mock_api.organizations.getOrganization = MagicMock(return_value=org)
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=networks)

        result = await service.run_discovery()

        mock_api.organizations.getOrganization.assert_called_once_with("123")
        mock_api.organizations.getOrganizationNetworks.assert_called_once_with(
            "123", total_pages="all"
        )
        assert len(result["organizations"]) == 1
        assert result["organizations"][0]["id"] == "123"

    @pytest.mark.asyncio
    async def test_run_discovery_with_multiple_orgs(self, discovery_service, mock_api):
        """Test discovery with multiple organizations."""
        orgs = [
            OrganizationFactory.create(org_id="123", name="Org1"),
            OrganizationFactory.create(org_id="456", name="Org2"),
        ]
        network = NetworkFactory.create(
            network_id="N_123",
            name="Network1",
            product_types=["wireless"],
        )

        mock_api.organizations.getOrganizations = MagicMock(return_value=orgs)
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[network])

        await discovery_service.run_discovery()

        mock_api.organizations.getOrganizations.assert_called_once()
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2

    @pytest.mark.asyncio
    async def test_discovery_handles_network_fetch_failure(self, discovery_service, mock_api):
        """Test handling of network fetch failures."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            side_effect=Exception("Network error")
        )

        result = await discovery_service.run_discovery()

        mock_api.organizations.getOrganizationNetworks.assert_called_once()
        assert "123: networks_fetch_failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_discovery_handles_complete_failure(self, discovery_service, mock_api):
        """Test handling of complete discovery failure."""
        mock_api.organizations.getOrganizations = MagicMock(
            side_effect=Exception("Authentication failed")
        )

        result = await discovery_service.run_discovery()

        mock_api.organizations.getOrganizations.assert_called_once()
        assert "discovery_failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_discovery_counts_products(self, discovery_service, mock_api):
        """Test that discovery correctly counts product types from networks."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        networks = [
            NetworkFactory.create(
                network_id="N_1",
                name="Net1",
                product_types=["wireless", "switch"],
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_2",
                name="Net2",
                product_types=["wireless"],
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_3",
                name="Net3",
                product_types=["appliance", "switch"],
                org_id=org["id"],
            ),
        ]

        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=networks)

        result = await discovery_service.run_discovery()

        mock_api.organizations.getOrganizationNetworks.assert_called_once()
        assert result["networks"]["123"]["count"] == 3
        assert result["networks"]["123"]["product_types"]["wireless"] == 2
        assert result["networks"]["123"]["product_types"]["switch"] == 2
        assert result["networks"]["123"]["product_types"]["appliance"] == 1

    @pytest.mark.asyncio
    async def test_discovery_returns_summary_structure(self, discovery_service, mock_api):
        """Test that discovery returns proper summary structure."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[])

        result = await discovery_service.run_discovery()

        assert "organizations" in result
        assert "networks" in result
        assert "errors" in result
        assert len(result["organizations"]) == 1
        assert result["organizations"][0]["name"] == "Test Org"
