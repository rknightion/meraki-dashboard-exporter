"""Integration tests for collection cycle behavior.

Tests cross-cutting behavior that unit tests cannot cover:
- Inventory cache sharing across multiple callers
- Multi-org label isolation to prevent metric cross-contamination
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Gauge

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.helpers.factories import DeviceFactory, OrganizationFactory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Real Settings with minimal required env vars."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_API__SMOOTHING_ENABLED", "false")
    monkeypatch.setenv("MERAKI_EXPORTER_API__MAX_RETRIES", "0")
    return Settings()


@pytest.fixture
def mock_api() -> MagicMock:
    """Synchronous mock of the Meraki DashboardAPI (called via asyncio.to_thread)."""
    api = MagicMock()
    api.organizations = MagicMock()
    api.organizations.getOrganizations = MagicMock()
    api.organizations.getOrganizationNetworks = MagicMock()
    api.organizations.getOrganizationDevices = MagicMock()
    api.organizations.getOrganizationDevicesAvailabilities = MagicMock()
    return api


@pytest.fixture
def inventory(mock_api: MagicMock, mock_settings: Settings) -> OrganizationInventory:
    """OrganizationInventory wired to the mock API."""
    # AsyncMerakiClient._ensure_metrics_initialized() must be called so the
    # shared Counter exists before OrganizationInventory._make_api_call uses it.
    AsyncMerakiClient._ensure_metrics_initialized()
    return OrganizationInventory(api=mock_api, settings=mock_settings)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInventoryCacheSharedAcrossCollectors:
    """Verify that the inventory cache dedups API calls."""

    async def test_get_devices_calls_api_only_once(
        self, inventory: OrganizationInventory, mock_api: MagicMock
    ) -> None:
        """Second call for the same org_id must hit the cache, not the API."""
        org_id = "org_cache_test"
        devices = DeviceFactory.create_many(3, product_type="wireless")
        mock_api.organizations.getOrganizationDevices.return_value = devices

        # First call — cache miss, API is called
        result1 = await inventory.get_devices(org_id)

        # Second call — cache hit, API must NOT be called again
        result2 = await inventory.get_devices(org_id)

        assert result1 == result2
        assert len(result1) == 3
        mock_api.organizations.getOrganizationDevices.assert_called_once()

    async def test_cache_hit_increments_hit_counter(
        self, inventory: OrganizationInventory, mock_api: MagicMock
    ) -> None:
        """Cache stats should correctly track hits vs misses."""
        org_id = "org_stats_test"
        devices = DeviceFactory.create_many(2)
        mock_api.organizations.getOrganizationDevices.return_value = devices

        # First call is a miss
        await inventory.get_devices(org_id)
        stats_after_miss = inventory.get_cache_stats()
        assert stats_after_miss["cache_misses"] == 1
        assert stats_after_miss["cache_hits"] == 0

        # Second and third calls are hits
        await inventory.get_devices(org_id)
        await inventory.get_devices(org_id)
        stats_after_hits = inventory.get_cache_stats()
        assert stats_after_hits["cache_hits"] == 2
        assert stats_after_hits["cache_misses"] == 1

    async def test_force_refresh_bypasses_cache(
        self, inventory: OrganizationInventory, mock_api: MagicMock
    ) -> None:
        """force_refresh=True must bypass the cache and fetch from the API again."""
        org_id = "org_refresh_test"
        initial_devices = DeviceFactory.create_many(2)
        updated_devices = DeviceFactory.create_many(4)
        mock_api.organizations.getOrganizationDevices.side_effect = [
            initial_devices,
            updated_devices,
        ]

        result1 = await inventory.get_devices(org_id)
        result2 = await inventory.get_devices(org_id, force_refresh=True)

        assert len(result1) == 2
        assert len(result2) == 4
        assert mock_api.organizations.getOrganizationDevices.call_count == 2

    async def test_separate_orgs_cached_independently(
        self, inventory: OrganizationInventory, mock_api: MagicMock
    ) -> None:
        """Each org_id has its own cache slot — different orgs don't share data."""
        org_a = "org_A"
        org_b = "org_B"
        devices_a = DeviceFactory.create_many(2, product_type="wireless")
        devices_b = DeviceFactory.create_many(3, product_type="switch")

        def devices_side_effect(org_id: str, total_pages: str = "all") -> list:  # type: ignore[return]
            if org_id == org_a:
                return devices_a
            if org_id == org_b:
                return devices_b

        mock_api.organizations.getOrganizationDevices.side_effect = devices_side_effect

        result_a = await inventory.get_devices(org_a)
        result_b = await inventory.get_devices(org_b)

        assert len(result_a) == 2
        assert len(result_b) == 3
        # Each org fetched independently
        assert mock_api.organizations.getOrganizationDevices.call_count == 2

        # Second calls must come from cache — still 2 total API calls
        await inventory.get_devices(org_a)
        await inventory.get_devices(org_b)
        assert mock_api.organizations.getOrganizationDevices.call_count == 2


class TestMultiOrgLabelIsolation:
    """Verify metrics carry correct org_id labels with no cross-contamination."""

    async def test_org_labels_are_isolated(
        self, mock_api: MagicMock, mock_settings: Settings, isolated_registry: CollectorRegistry
    ) -> None:
        """Metrics set for org_A must not appear under org_B labels."""
        org_a = OrganizationFactory.create(org_id="org_label_a", name="Org A")
        org_b = OrganizationFactory.create(org_id="org_label_b", name="Org B")

        devices_a = DeviceFactory.create_many(2, product_type="wireless")
        devices_b = DeviceFactory.create_many(3, product_type="switch")

        mock_api.organizations.getOrganizations.return_value = [org_a, org_b]

        def devices_side_effect(org_id: str, total_pages: str = "all") -> list:  # type: ignore[return]
            if org_id == org_a["id"]:
                return devices_a
            if org_id == org_b["id"]:
                return devices_b

        mock_api.organizations.getOrganizationDevices.side_effect = devices_side_effect

        # Use an isolated registry so this gauge does not conflict with others
        test_gauge = Gauge(
            "test_org_device_count",
            "Device count per org (test)",
            labelnames=["org_id"],
            registry=isolated_registry,
        )

        AsyncMerakiClient._ensure_metrics_initialized()
        inv = OrganizationInventory(api=mock_api, settings=mock_settings)

        # Simulate two collectors independently fetching devices for their org
        devices_for_a = await inv.get_devices(org_a["id"])
        devices_for_b = await inv.get_devices(org_b["id"])

        # Record metrics for each org using their own label
        test_gauge.labels(org_id=org_a["id"]).set(len(devices_for_a))
        test_gauge.labels(org_id=org_b["id"]).set(len(devices_for_b))

        # prometheus_client.get_sample_value returns float | None
        value_a = isolated_registry.get_sample_value(
            "test_org_device_count", {"org_id": org_a["id"]}
        )
        value_b = isolated_registry.get_sample_value(
            "test_org_device_count", {"org_id": org_b["id"]}
        )

        assert value_a == 2.0, f"Expected 2 devices for org_A, got {value_a}"
        assert value_b == 3.0, f"Expected 3 devices for org_B, got {value_b}"

        # Verify no cross-contamination: org_A's label shouldn't see org_B's count
        assert value_a != value_b

    async def test_inventory_returns_correct_devices_per_org(
        self, mock_api: MagicMock, mock_settings: Settings
    ) -> None:
        """Inventory returns only devices for the requested org, not all devices."""
        org_a_id = "org_isolation_a"
        org_b_id = "org_isolation_b"

        devices_a = [
            DeviceFactory.create(serial="SERIAL-A1", product_type="wireless"),
            DeviceFactory.create(serial="SERIAL-A2", product_type="wireless"),
        ]
        devices_b = [
            DeviceFactory.create(serial="SERIAL-B1", product_type="switch"),
        ]

        def devices_side_effect(org_id: str, total_pages: str = "all") -> list:  # type: ignore[return]
            if org_id == org_a_id:
                return devices_a
            if org_id == org_b_id:
                return devices_b

        mock_api.organizations.getOrganizationDevices.side_effect = devices_side_effect

        AsyncMerakiClient._ensure_metrics_initialized()
        inv = OrganizationInventory(api=mock_api, settings=mock_settings)

        result_a = await inv.get_devices(org_a_id)
        result_b = await inv.get_devices(org_b_id)

        serials_a = {d["serial"] for d in result_a}
        serials_b = {d["serial"] for d in result_b}

        # No serials should overlap
        assert serials_a & serials_b == set(), "Device serials crossed org boundaries"
        assert "SERIAL-A1" in serials_a
        assert "SERIAL-A2" in serials_a
        assert "SERIAL-B1" in serials_b
        assert "SERIAL-B1" not in serials_a
        assert "SERIAL-A1" not in serials_b
