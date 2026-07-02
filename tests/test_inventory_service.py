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


class TestOrganizationInventoryNetworkFilter:
    """Network-filter behaviour at the inventory read path."""

    async def test_get_networks_applies_filter(self, mock_api, mock_settings) -> None:
        """get_networks returns only filtered networks; cache stores the full list."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod-a", "tags": ["production"]},
            {"id": "L_2", "name": "lab-a", "tags": ["lab"]},
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inv = OrganizationInventory(mock_api, mock_settings, network_filter=nf)

        result = await inv.get_networks("ORG")
        assert [n["id"] for n in result] == ["L_1"]

        # Cache contains the full unfiltered list.
        assert [n["id"] for n in inv._networks["ORG"]] == ["L_1", "L_2"]

        # unfiltered=True returns the full list.
        full = await inv.get_networks("ORG", unfiltered=True)
        assert [n["id"] for n in full] == ["L_1", "L_2"]

    async def test_get_networks_no_filter_returns_all(self, mock_api, mock_settings) -> None:
        """When no filter is supplied, get_networks returns all networks."""
        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "x", "tags": []},
            {"id": "L_2", "name": "y", "tags": []},
        ]
        inv = OrganizationInventory(mock_api, mock_settings, network_filter=None)

        result = await inv.get_networks("ORG")
        assert [n["id"] for n in result] == ["L_1", "L_2"]

    async def test_get_networks_filter_applies_on_cache_hit(self, mock_api, mock_settings) -> None:
        """Regression: filter must apply on cache-hit returns, not just cache-miss.

        The cache-hit path is the production-warm path — missing it is a silent
        regression. This test exercises both pre-lock and post-lock cache hits.
        """
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inv = OrganizationInventory(mock_api, mock_settings, network_filter=nf)

        # First call populates the cache.
        first = await inv.get_networks("ORG")
        assert [n["id"] for n in first] == ["L_1"]

        # Second call must hit the cache AND still apply the filter.
        second = await inv.get_networks("ORG")
        assert [n["id"] for n in second] == ["L_1"]

        # Confirm the SDK was only called once — second call was a cache hit.
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1

    async def test_get_devices_drops_devices_in_excluded_networks(
        self, mock_api, mock_settings
    ) -> None:
        """Devices whose networkId is excluded are dropped from get_devices."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
        mock_api.organizations.getOrganizationDevices.return_value = [
            {"serial": "Q1", "networkId": "L_1"},
            {"serial": "Q2", "networkId": "L_2"},
            {"serial": "Q3", "networkId": "L_1"},
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inv = OrganizationInventory(mock_api, mock_settings, network_filter=nf)
        # Populate networks cache first so the filter has a list to resolve against.
        await inv.get_networks("ORG")

        result = await inv.get_devices("ORG")
        assert sorted(d["serial"] for d in result) == ["Q1", "Q3"]

        # Underlying cache still has all devices.
        assert {d["serial"] for d in inv._devices["ORG"]} == {"Q1", "Q2", "Q3"}

        # unfiltered returns all.
        all_devices = await inv.get_devices("ORG", unfiltered=True)
        assert sorted(d["serial"] for d in all_devices) == ["Q1", "Q2", "Q3"]

    async def test_get_device_availabilities_filters_by_network(
        self, mock_api, mock_settings
    ) -> None:
        """Device availability records for excluded networks are dropped."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
        mock_api.organizations.getOrganizationDevicesAvailabilities.return_value = [
            {"serial": "Q1", "network": {"id": "L_1"}, "status": "online"},
            {"serial": "Q2", "network": {"id": "L_2"}, "status": "online"},
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inv = OrganizationInventory(mock_api, mock_settings, network_filter=nf)
        await inv.get_networks("ORG")

        result = await inv.get_device_availabilities("ORG")
        assert [a["serial"] for a in result] == ["Q1"]

    async def test_get_device_availabilities_filters_flat_network_id_shape(
        self, mock_api, mock_settings
    ) -> None:
        """Filter handles availability records with flat networkId field too."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
        mock_api.organizations.getOrganizationDevicesAvailabilities.return_value = [
            {"serial": "Q1", "networkId": "L_1", "status": "online"},
            {"serial": "Q2", "networkId": "L_2", "status": "online"},
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inv = OrganizationInventory(mock_api, mock_settings, network_filter=nf)
        await inv.get_networks("ORG")

        result = await inv.get_device_availabilities("ORG")
        assert [a["serial"] for a in result] == ["Q1"]


class TestOrganizationInventoryValidation:
    """Reject SDK responses with the exhausted-retry error shape before caching.

    The Meraki SDK returns a ``{"errors": [...]}`` dict on retry exhaustion or
    semantic validation failures. Inventory must surface those via
    ``validate_response_format`` so downstream collectors don't iterate over
    error dicts.
    """

    async def test_get_organizations_rejects_error_shape(self, mock_api, mock_settings) -> None:
        """Reject SDK error-shape responses for getOrganizations and skip caching."""
        from meraki_dashboard_exporter.core.error_handling import DataValidationError

        mock_settings.meraki.org_id = None
        mock_api.organizations.getOrganizations.return_value = {"errors": ["something broke"]}
        inventory = OrganizationInventory(mock_api, mock_settings)

        with pytest.raises(DataValidationError):
            await inventory.get_organizations()

        # Cache must remain unpopulated.
        assert inventory._organizations is None
        assert inventory._org_timestamp == 0.0

    async def test_get_organizations_rate_limit_in_body_raises_retryable(
        self, mock_api, mock_settings
    ) -> None:
        """Rate-limit errors in the body raise RetryableAPIError so retries kick in."""
        from meraki_dashboard_exporter.core.error_handling import RetryableAPIError

        mock_settings.meraki.org_id = None
        mock_api.organizations.getOrganizations.return_value = {
            "errors": ["API rate limit exceeded for organization"]
        }
        inventory = OrganizationInventory(mock_api, mock_settings)

        with pytest.raises(RetryableAPIError):
            await inventory.get_organizations()
        assert inventory._organizations is None

    async def test_get_networks_rejects_error_shape(self, mock_api, inventory_service) -> None:
        """Reject SDK error-shape responses for getOrganizationNetworks and skip caching."""
        from meraki_dashboard_exporter.core.error_handling import DataValidationError

        mock_api.organizations.getOrganizationNetworks.return_value = {
            "errors": ["network fetch failed"]
        }

        with pytest.raises(DataValidationError):
            await inventory_service.get_networks("ORG")

        assert "ORG" not in inventory_service._networks

    async def test_get_networks_rejects_unexpected_dict(self, mock_api, inventory_service) -> None:
        """A bare dict where a list is expected raises DataValidationError."""
        from meraki_dashboard_exporter.core.error_handling import DataValidationError

        # A dict (not list, not "items"-wrapped, not "errors"-shaped) is invalid.
        mock_api.organizations.getOrganizationNetworks.return_value = {"id": "L_1"}

        with pytest.raises(DataValidationError):
            await inventory_service.get_networks("ORG")
        assert "ORG" not in inventory_service._networks

    async def test_get_devices_rejects_error_shape(self, mock_api, inventory_service) -> None:
        """Reject SDK error-shape responses for getOrganizationDevices and skip caching."""
        from meraki_dashboard_exporter.core.error_handling import DataValidationError

        mock_api.organizations.getOrganizationDevices.return_value = {
            "errors": ["device fetch failed"]
        }

        with pytest.raises(DataValidationError):
            await inventory_service.get_devices("ORG")
        assert "ORG" not in inventory_service._devices

    async def test_get_device_availabilities_rejects_error_shape(
        self, mock_api, inventory_service
    ) -> None:
        """Reject SDK error-shape responses for getOrganizationDevicesAvailabilities."""
        from meraki_dashboard_exporter.core.error_handling import DataValidationError

        mock_api.organizations.getOrganizationDevicesAvailabilities.return_value = {
            "errors": ["availability fetch failed"]
        }

        with pytest.raises(DataValidationError):
            await inventory_service.get_device_availabilities("ORG")
        assert "ORG" not in inventory_service._device_availabilities

    async def test_get_licenses_overview_swallows_validation_error(
        self, mock_api, inventory_service
    ) -> None:
        """Best-effort endpoint catches validation errors and returns empty dict."""
        mock_api.organizations.getOrganizationLicensesOverview.return_value = {
            "errors": ["unsupported"]
        }

        result = await inventory_service.get_licenses_overview("ORG")
        assert result == {}
        assert "ORG" not in inventory_service._licenses_overview

    async def test_get_login_security_swallows_validation_error(
        self, mock_api, inventory_service
    ) -> None:
        """Best-effort endpoint catches validation errors and returns empty dict."""
        mock_api.organizations.getOrganizationLoginSecurity.return_value = {
            "errors": ["unsupported"]
        }

        result = await inventory_service.get_login_security("ORG")
        assert result == {}
        assert "ORG" not in inventory_service._login_security


class TestOrganizationInventoryAllowedIds:
    """`get_allowed_network_ids` exposes the filter-resolved network set to collectors."""

    async def test_returns_none_when_no_filter(self, mock_api, mock_settings) -> None:
        """Without a NetworkFilter the helper returns None (filtering disabled)."""
        inventory = OrganizationInventory(mock_api, mock_settings, network_filter=None)
        assert await inventory.get_allowed_network_ids("ORG") is None

    async def test_returns_none_when_filter_inactive(self, mock_api, mock_settings) -> None:
        """An empty NetworkFilter is inactive and the helper returns None."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        nf = NetworkFilter(NetworkFilterSettings())  # no rules → inactive
        inventory = OrganizationInventory(mock_api, mock_settings, network_filter=nf)
        assert await inventory.get_allowed_network_ids("ORG") is None

    async def test_returns_filtered_set(self, mock_api, mock_settings) -> None:
        """Active filter returns the resolved set of allowed network IDs."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
            {"id": "L_3", "name": "prod-2", "tags": []},
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inventory = OrganizationInventory(mock_api, mock_settings, network_filter=nf)

        allowed = await inventory.get_allowed_network_ids("ORG")
        assert allowed == {"L_1", "L_3"}

    async def test_populates_network_cache_once(self, mock_api, mock_settings) -> None:
        """Repeated calls reuse the cached network list — no extra API call."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []}
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inventory = OrganizationInventory(mock_api, mock_settings, network_filter=nf)

        await inventory.get_allowed_network_ids("ORG")
        await inventory.get_allowed_network_ids("ORG")
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1

    async def test_force_refresh_bumps_api_call(self, mock_api, mock_settings) -> None:
        """force_refresh=True bypasses the cache and fetches a fresh list."""
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        mock_api.organizations.getOrganizationNetworks.return_value = [
            {"id": "L_1", "name": "prod", "tags": []}
        ]
        nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inventory = OrganizationInventory(mock_api, mock_settings, network_filter=nf)

        await inventory.get_allowed_network_ids("ORG")
        await inventory.get_allowed_network_ids("ORG", force_refresh=True)
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2


class TestFilterMatchSeriesExpiry:
    """meraki_network_filter_match series must not leak for deleted networks (F-079)."""

    def test_stale_filter_match_series_removed(self, inventory_service) -> None:
        """Deleted networks must have their filter_match series removed.

        A network present in one refresh but gone in the next must have its
        filter_match series removed, not left as a stale orphan.
        """
        gauge = inventory_service._filter_match_gauge

        nets_v1 = [
            {"id": "N_1", "name": "one"},
            {"id": "N_2", "name": "two"},
        ]
        inventory_service._emit_filter_metrics("ORG", nets_v1)
        assert ("ORG", "N_1") in gauge._metrics
        assert ("ORG", "N_2") in gauge._metrics

        # N_2 deleted; refresh with only N_1.
        inventory_service._emit_filter_metrics("ORG", [{"id": "N_1", "name": "one"}])
        assert ("ORG", "N_1") in gauge._metrics
        assert ("ORG", "N_2") not in gauge._metrics

    def test_uses_metric_name_enums(self, inventory_service) -> None:
        """The filter/cache-size gauges must use enum-derived names, not raw literals."""
        from meraki_dashboard_exporter.core.constants.metrics_constants import (
            CollectorMetricName,
            NetworkMetricName,
        )

        assert (
            inventory_service._filter_match_gauge._name
            == NetworkMetricName.NETWORK_FILTER_MATCH.value
        )
        assert (
            inventory_service._cache_size._name == CollectorMetricName.INVENTORY_CACHE_ENTRIES.value
        )
