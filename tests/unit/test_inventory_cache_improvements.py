"""Tests for inventory cache improvements: TTL jitter, cache warming, and size metrics."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.helpers.factories import DeviceFactory, NetworkFactory, OrganizationFactory


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    api = MagicMock()
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
def inventory(mock_api, mock_settings):
    """Create an inventory service instance."""
    return OrganizationInventory(mock_api, mock_settings)


class TestTTLJitter:
    """Test that TTL jitter produces varied expiry times."""

    def test_is_expired_fresh_entry(self, inventory):
        """A just-cached entry should not be expired."""
        timestamp = time.time()
        ttl = 300.0
        assert not inventory._is_expired(timestamp, ttl)

    def test_is_expired_old_entry(self, inventory):
        """An entry older than the max jittered TTL (110% of base) should always expire."""
        # 111% of TTL ensures we're past even the highest jitter value (100% + 10%)
        timestamp = time.time() - 300.0 * 1.11
        ttl = 300.0
        assert inventory._is_expired(timestamp, ttl)

    def test_is_expired_below_min_jitter(self, inventory):
        """An entry younger than the min jittered TTL (90% of base) should never expire."""
        # 89% of TTL ensures we're below even the lowest jitter value (100% - 10%)
        timestamp = time.time() - 300.0 * 0.89
        ttl = 300.0
        assert not inventory._is_expired(timestamp, ttl)

    def test_jitter_produces_varied_expiry_times(self, inventory):
        """Multiple calls with the same inputs should vary due to randomness."""
        # Use a borderline timestamp (at exactly 100% of TTL) where jitter matters
        ttl = 300.0
        # Timestamp right at the edge — the ±10% jitter means sometimes expired, sometimes not
        timestamp = time.time() - ttl  # exactly at base TTL

        results = set()
        for _ in range(50):
            result = inventory._is_expired(timestamp, ttl)
            results.add(result)
            if len(results) == 2:
                break  # Both True and False seen — jitter is working

        # With 50 samples and ±10% jitter, we should see both outcomes
        assert len(results) == 2, (
            "Expected both expired and not-expired results at the TTL boundary; "
            "jitter may not be applied"
        )

    def test_jitter_range_is_correct(self, inventory):
        """Verify jitter stays within ±10% of the base TTL."""
        ttl = 300.0

        with patch("meraki_dashboard_exporter.services.inventory.random.random") as mock_random:
            # Test minimum jitter (random() → 0.0 → jitter factor = 0.9)
            mock_random.return_value = 0.0
            # Entry at exactly 0.9 * TTL should be right at the boundary
            at_min = time.time() - (ttl * 0.9 - 0.001)
            assert not inventory._is_expired(at_min, ttl)
            at_min_expired = time.time() - (ttl * 0.9 + 0.001)
            assert inventory._is_expired(at_min_expired, ttl)

            # Test maximum jitter (random() → 1.0 → jitter factor = 1.1)
            mock_random.return_value = 1.0
            at_max = time.time() - (ttl * 1.1 - 0.001)
            assert not inventory._is_expired(at_max, ttl)
            at_max_expired = time.time() - (ttl * 1.1 + 0.001)
            assert inventory._is_expired(at_max_expired, ttl)


class TestWarmCache:
    """Test that warm_cache pre-populates organizations, networks, and devices."""

    async def test_warm_cache_fetches_orgs_networks_devices(self, mock_api, mock_settings):
        """warm_cache should fetch orgs, networks, and devices for all orgs."""
        orgs = OrganizationFactory.create_many(2)
        org_id_1 = orgs[0]["id"]
        org_id_2 = orgs[1]["id"]

        networks_1 = NetworkFactory.create_many(3, org_id=org_id_1)
        networks_2 = NetworkFactory.create_many(2, org_id=org_id_2)
        devices_1 = DeviceFactory.create_many(4)
        devices_2 = DeviceFactory.create_many(5)

        mock_api.organizations.getOrganizations.return_value = orgs

        def networks_side_effect(oid, **kwargs):
            if oid == org_id_1:
                return networks_1
            return networks_2

        def devices_side_effect(oid, **kwargs):
            if oid == org_id_1:
                return devices_1
            return devices_2

        mock_api.organizations.getOrganizationNetworks.side_effect = networks_side_effect
        mock_api.organizations.getOrganizationDevices.side_effect = devices_side_effect

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.warm_cache()

        # Organizations fetched once
        assert mock_api.organizations.getOrganizations.call_count == 1

        # Networks and devices fetched once per org
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2
        assert mock_api.organizations.getOrganizationDevices.call_count == 2

        # Data should now be in cache — subsequent calls should be cache hits
        stats_before = inventory.get_cache_stats()
        hits_before = stats_before["cache_hits"]

        result_nets = await inventory.get_networks(org_id_1)
        result_devs = await inventory.get_devices(org_id_1)

        assert result_nets == networks_1
        assert result_devs == devices_1

        stats_after = inventory.get_cache_stats()
        assert stats_after["cache_hits"] == hits_before + 2

        # API should NOT have been called again
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2
        assert mock_api.organizations.getOrganizationDevices.call_count == 2

    async def test_warm_cache_with_org_filter(self, mock_api, mock_settings):
        """warm_cache with org_ids only warms specified organizations."""
        orgs = OrganizationFactory.create_many(3)
        org_id_0 = orgs[0]["id"]
        org_id_1 = orgs[1]["id"]
        org_id_2 = orgs[2]["id"]

        mock_api.organizations.getOrganizations.return_value = orgs
        mock_api.organizations.getOrganizationNetworks.return_value = []
        mock_api.organizations.getOrganizationDevices.return_value = []

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.warm_cache(org_ids=[org_id_0, org_id_2])

        # Only 2 of 3 orgs should have been warmed
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2
        assert mock_api.organizations.getOrganizationDevices.call_count == 2

        # The filtered org should not be in cache
        assert org_id_1 not in inventory._networks
        assert org_id_1 not in inventory._devices

    async def test_warm_cache_handles_api_errors_gracefully(self, mock_api, mock_settings):
        """warm_cache should continue warming other orgs if one fails."""
        orgs = OrganizationFactory.create_many(2)
        org_id_0 = orgs[0]["id"]
        org_id_1 = orgs[1]["id"]

        mock_api.organizations.getOrganizations.return_value = orgs

        call_count = {"n": 0}

        def networks_side_effect(oid, **kwargs):
            call_count["n"] += 1
            if oid == org_id_0:
                raise Exception("API failure for org 0")
            return NetworkFactory.create_many(2, org_id=oid)

        mock_api.organizations.getOrganizationNetworks.side_effect = networks_side_effect
        mock_api.organizations.getOrganizationDevices.return_value = []

        inventory = OrganizationInventory(mock_api, mock_settings)
        # Should not raise even though one org fails
        await inventory.warm_cache()

        # Both orgs were attempted
        assert call_count["n"] >= 1
        # Second org should be cached
        assert org_id_1 in inventory._networks

    async def test_warm_cache_handles_org_fetch_failure(self, mock_api, mock_settings):
        """warm_cache should exit gracefully if fetching organizations fails."""
        mock_api.organizations.getOrganizations.side_effect = Exception("No orgs")

        inventory = OrganizationInventory(mock_api, mock_settings)
        # Must not raise
        await inventory.warm_cache()

        # No networks or devices should have been fetched
        assert mock_api.organizations.getOrganizationNetworks.call_count == 0
        assert mock_api.organizations.getOrganizationDevices.call_count == 0

    async def test_warm_cache_single_org_mode(self, mock_api, mock_settings):
        """warm_cache works correctly in single-org mode."""
        org_id = "123456"
        mock_settings.meraki.org_id = org_id
        mock_api.organizations.getOrganizationNetworks.return_value = NetworkFactory.create_many(
            3, org_id=org_id
        )
        mock_api.organizations.getOrganizationDevices.return_value = DeviceFactory.create_many(5)

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.warm_cache()

        # Single org mode — org list is synthetic, no API call for orgs
        assert mock_api.organizations.getOrganizations.call_count == 0

        # Networks and devices fetched for the single org
        assert mock_api.organizations.getOrganizationNetworks.call_count == 1
        assert mock_api.organizations.getOrganizationDevices.call_count == 1

        # Data should be cached
        assert org_id in inventory._networks
        assert org_id in inventory._devices


class TestCacheSizeMetrics:
    """Test that cache_size gauge is updated when cache entries are added."""

    def _get_gauge_value(self, inventory: OrganizationInventory, org_id: str, cache_type: str):
        """Read the current value of a cache_size label combination."""
        try:
            return inventory._cache_size.labels(org_id=org_id, cache_type=cache_type)._value.get()
        except Exception:
            return None

    async def test_cache_size_updated_on_network_fetch(self, mock_api, mock_settings):
        """Cache size gauge should update when networks are fetched."""
        org_id = "org_123"
        networks = NetworkFactory.create_many(7, org_id=org_id)
        mock_api.organizations.getOrganizationNetworks.return_value = networks

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.get_networks(org_id)

        value = self._get_gauge_value(inventory, org_id, "networks")
        assert value == 7.0

    async def test_cache_size_updated_on_device_fetch(self, mock_api, mock_settings):
        """Cache size gauge should update when devices are fetched."""
        org_id = "org_123"
        devices = DeviceFactory.create_many(12)
        mock_api.organizations.getOrganizationDevices.return_value = devices

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.get_devices(org_id)

        value = self._get_gauge_value(inventory, org_id, "devices")
        assert value == 12.0

    async def test_cache_size_updated_on_org_fetch(self, mock_api, mock_settings):
        """Cache size gauge should update when organizations are fetched."""
        orgs = OrganizationFactory.create_many(4)
        mock_api.organizations.getOrganizations.return_value = orgs

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.get_organizations()

        value = self._get_gauge_value(inventory, "global", "organizations")
        assert value == 4.0

    async def test_cache_size_reflects_latest_value(self, mock_api, mock_settings):
        """Cache size gauge should update to the new value on force refresh."""
        org_id = "org_123"

        mock_api.organizations.getOrganizationNetworks.return_value = NetworkFactory.create_many(
            3, org_id=org_id
        )
        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.get_networks(org_id)
        assert self._get_gauge_value(inventory, org_id, "networks") == 3.0

        # Force refresh with different count
        mock_api.organizations.getOrganizationNetworks.return_value = NetworkFactory.create_many(
            10, org_id=org_id
        )
        await inventory.get_networks(org_id, force_refresh=True)
        assert self._get_gauge_value(inventory, org_id, "networks") == 10.0

    async def test_cache_size_per_org(self, mock_api, mock_settings):
        """Cache size gauge should track sizes independently per org."""
        org_1 = "org_001"
        org_2 = "org_002"

        def networks_side_effect(oid, **kwargs):
            if oid == org_1:
                return NetworkFactory.create_many(5, org_id=oid)
            return NetworkFactory.create_many(2, org_id=oid)

        mock_api.organizations.getOrganizationNetworks.side_effect = networks_side_effect

        inventory = OrganizationInventory(mock_api, mock_settings)
        await inventory.get_networks(org_1)
        await inventory.get_networks(org_2)

        assert self._get_gauge_value(inventory, org_1, "networks") == 5.0
        assert self._get_gauge_value(inventory, org_2, "networks") == 2.0
