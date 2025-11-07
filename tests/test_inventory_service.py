"""Unit tests for OrganizationInventory service (P5.1.2 - Phase 1.2)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.helpers.factories import DeviceFactory, NetworkFactory, OrganizationFactory


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    api = MagicMock()
    # Use MagicMock (not AsyncMock) because inventory service calls these
    # synchronous methods via asyncio.to_thread()
    api.organizations = MagicMock()
    api.organizations.getOrganizations = MagicMock()
    api.organizations.getOrganizationNetworks = MagicMock()
    api.organizations.getOrganizationDevices = MagicMock()
    return api


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.meraki.org_id = None  # Multi-org by default
    return settings


@pytest.fixture
def inventory_service(mock_api, mock_settings):
    """Create an inventory service instance."""
    return OrganizationInventory(mock_api, mock_settings)


class TestOrganizationInventoryBasics:
    """Test basic inventory service functionality."""

    async def test_get_organizations_single_org(self, mock_api, mock_settings, inventory_service):
        """Test getting organizations when org_id is configured."""
        # Configure for single org
        mock_settings.meraki.org_id = "123456"

        result = await inventory_service.get_organizations()

        assert len(result) == 1
        assert result[0]["id"] == "123456"
        # In single-org mode, API is NOT called - org list is created directly
        mock_api.organizations.getOrganizations.assert_not_called()

    async def test_get_organizations_multi_org(self, mock_api, mock_settings, inventory_service):
        """Test getting all organizations in multi-org mode."""
        mock_settings.meraki.org_id = None

        orgs = OrganizationFactory.create_many(3)
        mock_api.organizations.getOrganizations.return_value = orgs

        result = await inventory_service.get_organizations()

        assert len(result) == 3
        mock_api.organizations.getOrganizations.assert_called_once()

    async def test_get_organizations_caching(self, mock_api, mock_settings, inventory_service):
        """Test that organizations are cached."""
        orgs = OrganizationFactory.create_many(2)
        mock_api.organizations.getOrganizations.return_value = orgs

        # First call - should hit API
        result1 = await inventory_service.get_organizations()
        assert len(result1) == 2
        assert mock_api.organizations.getOrganizations.call_count == 1

        # Second call - should use cache
        result2 = await inventory_service.get_organizations()
        assert len(result2) == 2
        assert result1 == result2
        # API should not be called again
        assert mock_api.organizations.getOrganizations.call_count == 1

    async def test_get_networks(self, mock_api, inventory_service):
        """Test getting networks for an organization."""
        org_id = "org_123"
        networks = NetworkFactory.create_many(5, org_id=org_id)
        mock_api.organizations.getOrganizationNetworks.return_value = networks

        result = await inventory_service.get_networks(org_id)

        assert len(result) == 5
        assert all(net["organizationId"] == org_id for net in result)
        mock_api.organizations.getOrganizationNetworks.assert_called_once_with(
            org_id, total_pages="all"
        )

    async def test_get_networks_caching(self, mock_api, inventory_service):
        """Test that networks are cached per organization."""
        org_id = "org_123"
        networks = NetworkFactory.create_many(3, org_id=org_id)
        mock_api.organizations.getOrganizationNetworks.return_value = networks

        # First call - should hit API
        result1 = await inventory_service.get_networks(org_id)
        assert len(result1) == 3
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1

        # Second call - should use cache
        result2 = await inventory_service.get_networks(org_id)
        assert len(result2) == 3
        assert result1 == result2
        # API should not be called again
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1

    async def test_get_devices_all(self, mock_api, inventory_service):
        """Test getting all devices for an organization."""
        org_id = "org_123"
        devices = DeviceFactory.create_many(10)
        mock_api.organizations.getOrganizationDevices.return_value = devices

        result = await inventory_service.get_devices(org_id)

        assert len(result) == 10
        mock_api.organizations.getOrganizationDevices.assert_called_once_with(
            org_id, total_pages="all"
        )

    async def test_get_devices_filtered_by_network(self, mock_api, inventory_service):
        """Test getting devices filtered by network."""
        org_id = "org_123"
        network_id = "N_456"

        # Create devices for different networks
        devices_net1 = DeviceFactory.create_many(5, network_id=network_id)
        devices_net2 = DeviceFactory.create_many(3, network_id="N_789")
        all_devices = devices_net1 + devices_net2

        mock_api.organizations.getOrganizationDevices.return_value = all_devices

        result = await inventory_service.get_devices(org_id, network_id=network_id)

        # Should only return devices for specified network
        assert len(result) == 5
        assert all(dev["networkId"] == network_id for dev in result)

    async def test_get_devices_caching(self, mock_api, inventory_service):
        """Test that devices are cached."""
        org_id = "org_123"
        devices = DeviceFactory.create_many(5)
        mock_api.organizations.getOrganizationDevices.return_value = devices

        # First call - should hit API
        result1 = await inventory_service.get_devices(org_id)
        assert len(result1) == 5
        assert mock_api.organizations.getOrganizationDevices.call_count == 1

        # Second call - should use cache
        result2 = await inventory_service.get_devices(org_id)
        assert len(result2) == 5
        assert result1 == result2
        # API should not be called again
        assert mock_api.organizations.getOrganizationDevices.call_count == 1


class TestOrganizationInventoryCacheInvalidation:
    """Test cache invalidation functionality."""

    async def test_invalidate_specific_org(self, mock_api, inventory_service):
        """Test invalidating cache for a specific organization."""
        org_id = "org_123"
        networks = NetworkFactory.create_many(3, org_id=org_id)
        devices = DeviceFactory.create_many(5)

        mock_api.organizations.getOrganizationNetworks.return_value = networks
        mock_api.organizations.getOrganizationDevices.return_value = devices

        # Cache networks and devices
        await inventory_service.get_networks(org_id)
        await inventory_service.get_devices(org_id)

        # Verify cached
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1
        assert mock_api.organizations.getOrganizationDevices.call_count == 1

        # Invalidate specific org
        await inventory_service.invalidate(org_id=org_id)

        # Next call should hit API again
        await inventory_service.get_networks(org_id)
        await inventory_service.get_devices(org_id)

        assert mock_api.organizations.getOrganizationNetworks.call_count == 2
        assert mock_api.organizations.getOrganizationDevices.call_count == 2

    async def test_invalidate_all_orgs(self, mock_api, mock_settings, inventory_service):
        """Test invalidating cache for all organizations."""
        mock_settings.meraki.org_id = None
        orgs = OrganizationFactory.create_many(2)
        mock_api.organizations.getOrganizations.return_value = orgs

        # Cache organizations
        await inventory_service.get_organizations()
        assert mock_api.organizations.getOrganizations.call_count == 1

        # Invalidate all
        await inventory_service.invalidate()

        # Next call should hit API again
        await inventory_service.get_organizations()
        assert mock_api.organizations.getOrganizations.call_count == 2

    async def test_cache_stats(self, mock_api, inventory_service):
        """Test cache statistics reporting."""
        org_id = "org_123"
        networks = NetworkFactory.create_many(3, org_id=org_id)
        devices = DeviceFactory.create_many(5)

        mock_api.organizations.getOrganizationNetworks.return_value = networks
        mock_api.organizations.getOrganizationDevices.return_value = devices

        # Initial stats should be empty
        stats = inventory_service.get_cache_stats()
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0

        # Access data to populate cache
        await inventory_service.get_networks(org_id)  # miss
        await inventory_service.get_networks(org_id)  # hit
        await inventory_service.get_devices(org_id)  # miss
        await inventory_service.get_devices(org_id)  # hit

        # Check stats - global counters across all cache types
        stats = inventory_service.get_cache_stats()
        assert stats["cache_hits"] == 2  # 1 network hit + 1 device hit
        assert stats["cache_misses"] == 2  # 1 network miss + 1 device miss
        assert stats["cached_networks"] == 1  # One org's networks cached
        assert stats["cached_devices"] == 1  # One org's devices cached


class TestOrganizationInventoryConcurrency:
    """Test concurrent access to inventory service."""

    async def test_concurrent_network_access(self, mock_api, inventory_service):
        """Test concurrent access to same organization networks."""
        import time

        org_id = "org_123"
        networks = NetworkFactory.create_many(5, org_id=org_id)

        # Simulate slow API call (synchronous, called via asyncio.to_thread)
        def slow_get_networks(*args, **kwargs):
            time.sleep(0.1)
            return networks

        mock_api.organizations.getOrganizationNetworks.side_effect = slow_get_networks

        # Make concurrent requests
        results = await asyncio.gather(
            inventory_service.get_networks(org_id),
            inventory_service.get_networks(org_id),
            inventory_service.get_networks(org_id),
        )

        # All should return same result
        assert all(len(r) == 5 for r in results)
        assert all(r == results[0] for r in results)

        # API should only be called once (due to locking)
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1

    async def test_concurrent_different_orgs(self, mock_api, inventory_service):
        """Test concurrent access to different organizations."""
        org1 = "org_123"
        org2 = "org_456"

        networks1 = NetworkFactory.create_many(3, org_id=org1)
        networks2 = NetworkFactory.create_many(4, org_id=org2)

        def side_effect(*args, **kwargs):
            org_id = args[0]
            if org_id == org1:
                return networks1
            return networks2

        mock_api.organizations.getOrganizationNetworks.side_effect = side_effect

        # Make concurrent requests for different orgs
        result1, result2 = await asyncio.gather(
            inventory_service.get_networks(org1),
            inventory_service.get_networks(org2),
        )

        assert len(result1) == 3
        assert len(result2) == 4
        # Should call API twice (once per org)
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2


class TestOrganizationInventoryEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_organizations(self, mock_api, mock_settings, inventory_service):
        """Test handling of empty organization list."""
        mock_settings.meraki.org_id = None
        mock_api.organizations.getOrganizations.return_value = []

        result = await inventory_service.get_organizations()

        assert len(result) == 0

    async def test_empty_networks(self, mock_api, inventory_service):
        """Test handling of organization with no networks."""
        org_id = "org_123"
        mock_api.organizations.getOrganizationNetworks.return_value = []

        result = await inventory_service.get_networks(org_id)

        assert len(result) == 0

    async def test_empty_devices(self, mock_api, inventory_service):
        """Test handling of organization with no devices."""
        org_id = "org_123"
        mock_api.organizations.getOrganizationDevices.return_value = []

        result = await inventory_service.get_devices(org_id)

        assert len(result) == 0

    async def test_api_error_handling(self, mock_api, inventory_service):
        """Test that API errors are propagated."""
        org_id = "org_123"
        mock_api.organizations.getOrganizationNetworks.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            await inventory_service.get_networks(org_id)

    async def test_network_filter_with_no_matching_devices(self, mock_api, inventory_service):
        """Test network filtering when no devices match."""
        org_id = "org_123"
        network_id = "N_nonexistent"

        devices = DeviceFactory.create_many(5, network_id="N_other")
        mock_api.organizations.getOrganizationDevices.return_value = devices

        result = await inventory_service.get_devices(org_id, network_id=network_id)

        assert len(result) == 0


class TestOrganizationInventoryMetrics:
    """Test metrics tracking in inventory service."""

    async def test_cache_hit_metrics(self, mock_api, inventory_service):
        """Test that cache hits are tracked correctly."""
        org_id = "org_123"
        networks = NetworkFactory.create_many(3, org_id=org_id)
        mock_api.organizations.getOrganizationNetworks.return_value = networks

        # First access (miss)
        await inventory_service.get_networks(org_id)

        # Multiple subsequent accesses (hits)
        await inventory_service.get_networks(org_id)
        await inventory_service.get_networks(org_id)
        await inventory_service.get_networks(org_id)

        stats = inventory_service.get_cache_stats()
        assert stats["cache_hits"] == 3
        assert stats["cache_misses"] == 1
        assert stats["cached_networks"] == 1  # One org cached

    async def test_cache_miss_metrics(self, mock_api, inventory_service):
        """Test that cache misses are tracked correctly."""
        networks1 = NetworkFactory.create_many(3, org_id="org_1")
        networks2 = NetworkFactory.create_many(4, org_id="org_2")

        def side_effect(*args, **kwargs):
            org_id = args[0]
            if org_id == "org_1":
                return networks1
            return networks2

        mock_api.organizations.getOrganizationNetworks.side_effect = side_effect

        # Access different orgs (all misses)
        await inventory_service.get_networks("org_1")
        await inventory_service.get_networks("org_2")

        stats = inventory_service.get_cache_stats()
        assert stats["cache_misses"] == 2
        assert stats["cache_hits"] == 0
        assert stats["cached_networks"] == 2  # Two orgs cached
