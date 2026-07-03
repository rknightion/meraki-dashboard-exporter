"""Tests for the FirmwareCollector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.firmware import (
    FirmwareCollector,
)

if TYPE_CHECKING:
    pass


class TestFirmwareCollector:
    """Test FirmwareCollector functionality."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        from pydantic import SecretStr

        from meraki_dashboard_exporter.core.config import Settings
        from meraki_dashboard_exporter.core.config_models import MerakiSettings

        return Settings(
            meraki=MerakiSettings(
                api_key=SecretStr("6bec40cf957de430a6f1f2baa056b367d6172e1e"), org_id="test-org-id"
            )
        )

    @pytest.fixture
    def isolated_registry(self, monkeypatch):
        """Create an isolated Prometheus registry."""
        from prometheus_client import CollectorRegistry

        registry = CollectorRegistry()
        return registry

    @pytest.fixture
    def firmware_collector(
        self, mock_api_builder, settings, isolated_registry
    ) -> FirmwareCollector:
        """Create FirmwareCollector instance with mocked dependencies."""

        class MockParentCollector:
            def __init__(self) -> None:
                self.api = mock_api_builder.build()
                self.settings = settings
                self._api_calls: dict[str, int] = {}
                self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

            def _should_run_group(self, group: object) -> bool:
                return True

            def _mark_group_ran(self, group: object) -> None:
                pass

            def _group_ttl_seconds(self, group: object) -> float | None:
                return None

            def _track_api_call(self, method_name: str) -> None:
                self._api_calls[method_name] = self._api_calls.get(method_name, 0) + 1

            def _set_metric_value(
                self,
                metric_name: str,
                labels: dict[str, str],
                value: float | None,
                ttl_seconds: float | None = None,
            ) -> None:
                if value is not None:
                    key = (metric_name, tuple(sorted(labels.items())))
                    self._metrics[key] = value

        parent = MockParentCollector()
        return FirmwareCollector(parent=parent)  # type: ignore[arg-type]

    async def test_collect_firmware_upgrades_by_product_and_status(
        self, firmware_collector, mock_api_builder
    ):
        """Test aggregation of firmware upgrade events by (productTypes, status)."""
        org_id = "123"
        org_name = "Test Org"

        upgrades_response = [
            {
                "upgradeId": "1",
                "upgradeBatchId": "b1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "completed",
                "productTypes": "switch",
                "time": "2026-06-01T00:00:00Z",
                "completedAt": "2026-06-01T01:00:00Z",
            },
            {
                "upgradeId": "2",
                "upgradeBatchId": "b1",
                "network": {"id": "n2", "name": "Network 2"},
                "status": "completed",
                "productTypes": "switch",
                "time": "2026-06-01T00:00:00Z",
                "completedAt": "2026-06-01T01:00:00Z",
            },
            {
                "upgradeId": "3",
                "upgradeBatchId": "b2",
                "network": {"id": "n3", "name": "Network 3"},
                "status": "scheduled",
                "productTypes": "wireless",
                "time": "2026-07-01T00:00:00Z",
                "completedAt": None,
            },
            {
                "upgradeId": "4",
                "upgradeBatchId": "b3",
                "network": {"id": "n4", "name": "Network 4"},
                "status": "canceled",
                "productTypes": "appliance",
                "time": "2026-06-15T00:00:00Z",
                "completedAt": None,
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", upgrades_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        assert api.organizations.getOrganizationFirmwareUpgrades.called
        assert api.organizations.getOrganizationFirmwareUpgrades.call_args[0][0] == org_id
        assert (
            api.organizations.getOrganizationFirmwareUpgrades.call_args[1]["total_pages"] == "all"
        )

        parent = firmware_collector.parent

        expected_totals = [
            ("switch", "completed", 2),
            ("wireless", "scheduled", 1),
            ("appliance", "canceled", 1),
        ]
        for product_type, status, count in expected_totals:
            key = (
                "_org_firmware_upgrades_total",
                (
                    ("org_id", org_id),
                    ("product_type", product_type),
                    ("status", status),
                ),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

        # Pending subset: only "scheduled" (wireless) counts as pending here.
        pending_key = (
            "_org_firmware_upgrades_pending_total",
            (("org_id", org_id), ("product_type", "wireless")),
        )
        assert pending_key in parent._metrics
        assert parent._metrics[pending_key] == 1

        # Non-pending product types should not have a pending metric.
        for product_type in ("switch", "appliance"):
            key = (
                "_org_firmware_upgrades_pending_total",
                (("org_id", org_id), ("product_type", product_type)),
            )
            assert key not in parent._metrics

    async def test_collect_pending_statuses(self, firmware_collector, mock_api_builder):
        """Test that scheduled/pending/started statuses all count as pending."""
        org_id = "456"
        org_name = "Pending Org"

        upgrades_response = [
            {
                "upgradeId": "1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "scheduled",
                "productTypes": "switch",
            },
            {
                "upgradeId": "2",
                "network": {"id": "n2", "name": "Network 2"},
                "status": "pending",
                "productTypes": "switch",
            },
            {
                "upgradeId": "3",
                "network": {"id": "n3", "name": "Network 3"},
                "status": "started",
                "productTypes": "switch",
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", upgrades_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        pending_key = (
            "_org_firmware_upgrades_pending_total",
            (("org_id", org_id), ("product_type", "switch")),
        )
        assert pending_key in parent._metrics
        assert parent._metrics[pending_key] == 3

    async def test_collect_with_empty_response(self, firmware_collector, mock_api_builder):
        """Test handling of empty firmware upgrade list."""
        org_id = "789"
        org_name = "Empty Org"

        api = mock_api_builder.with_custom_response("getOrganizationFirmwareUpgrades", []).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_missing_fields_defaults_to_unknown(
        self, firmware_collector, mock_api_builder
    ):
        """Test that missing productTypes/status default to 'unknown'."""
        org_id = "111"
        org_name = "Missing Fields Org"

        upgrades_response = [
            {"upgradeId": "1", "network": {"id": "n1", "name": "Network 1"}},
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", upgrades_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        key = (
            "_org_firmware_upgrades_total",
            (
                ("org_id", org_id),
                ("product_type", "unknown"),
                ("status", "unknown"),
            ),
        )
        assert key in parent._metrics
        assert parent._metrics[key] == 1

    async def test_collect_with_404_error(self, firmware_collector, mock_api_builder):
        """Test handling of 404 error (no firmware upgrade info)."""
        org_id = "222"
        org_name = "No Firmware API Org"

        api = mock_api_builder.with_error(
            "getOrganizationFirmwareUpgrades", Exception("404 Not Found")
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_api_error(self, firmware_collector, mock_api_builder):
        """Test handling of general API errors."""
        org_id = "333"
        org_name = "API Error Org"

        api = mock_api_builder.with_error(
            "getOrganizationFirmwareUpgrades", Exception("Connection timeout")
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        assert len(parent._metrics) == 0

    async def test_fetch_firmware_upgrades_parameters(self, firmware_collector, mock_api_builder):
        """Test that _fetch_firmware_upgrades passes correct parameters."""
        org_id = "test-org-123"

        api = mock_api_builder.with_custom_response("getOrganizationFirmwareUpgrades", []).build()
        firmware_collector.api = api

        result = await firmware_collector._fetch_firmware_upgrades(org_id)

        assert api.organizations.getOrganizationFirmwareUpgrades.called
        call_args = api.organizations.getOrganizationFirmwareUpgrades.call_args
        assert call_args[0][0] == org_id
        assert call_args[1]["total_pages"] == "all"
        assert result == []

    async def test_collect_applies_network_filter(self, firmware_collector, mock_api_builder):
        """F-010: events for networks excluded by NetworkFilter must not be counted."""
        org_id = "999"
        org_name = "Filtered Org"

        upgrades_response = [
            {
                "upgradeId": "1",
                "network": {"id": "N_INCLUDED", "name": "Included"},
                "status": "Completed",
                "productTypes": "switch",
            },
            {
                "upgradeId": "2",
                "network": {"id": "N_EXCLUDED", "name": "Excluded"},
                "status": "Completed",
                "productTypes": "switch",
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", upgrades_response
        ).build()
        firmware_collector.api = api

        firmware_collector.inventory = MagicMock()
        firmware_collector.inventory.get_allowed_network_ids = AsyncMock(
            return_value={"N_INCLUDED"}
        )

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        key = (
            "_org_firmware_upgrades_total",
            (
                ("org_id", org_id),
                ("product_type", "switch"),
                ("status", "Completed"),
            ),
        )
        assert key in parent._metrics
        # Only the event for N_INCLUDED should be counted.
        assert parent._metrics[key] == 1

    async def test_collect_pending_statuses_case_insensitive(
        self, firmware_collector, mock_api_builder
    ):
        """F-055: the API returns capitalized statuses; pending must still be detected."""
        org_id = "654"
        org_name = "Cased Org"

        upgrades_response = [
            {
                "upgradeId": "1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "Scheduled",
                "productTypes": "wireless",
            },
            {
                "upgradeId": "2",
                "network": {"id": "n2", "name": "Network 2"},
                "status": "Started",
                "productTypes": "wireless",
            },
            {
                "upgradeId": "3",
                "network": {"id": "n3", "name": "Network 3"},
                "status": "Completed",
                "productTypes": "wireless",
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", upgrades_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        pending_key = (
            "_org_firmware_upgrades_pending_total",
            (("org_id", org_id), ("product_type", "wireless")),
        )
        assert pending_key in parent._metrics
        assert parent._metrics[pending_key] == 2

    async def test_collect_zeroes_stale_combos_across_cycles(
        self, firmware_collector, mock_api_builder
    ):
        """F-056: a combo present last cycle but absent this cycle must report 0."""
        org_id = "777"
        org_name = "Flappy Org"

        first_response = [
            {
                "upgradeId": "1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "Started",
                "productTypes": "switch",
            },
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", first_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        total_key = (
            "_org_firmware_upgrades_total",
            (
                ("org_id", org_id),
                ("product_type", "switch"),
                ("status", "Started"),
            ),
        )
        pending_key = (
            "_org_firmware_upgrades_pending_total",
            (("org_id", org_id), ("product_type", "switch")),
        )
        assert parent._metrics[total_key] == 1
        assert parent._metrics[pending_key] == 1

        # Second cycle: the upgrade has moved to Completed and no more events for the
        # "Started" status arrive. The old "Started" combo should now report 0, and
        # the pending gauge for switch should also drop to 0 since nothing pending
        # remains.
        second_response = [
            {
                "upgradeId": "1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "Completed",
                "productTypes": "switch",
            },
        ]
        api2 = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", second_response
        ).build()
        firmware_collector.api = api2

        await firmware_collector.collect(org_id, org_name)

        assert parent._metrics[total_key] == 0
        assert parent._metrics[pending_key] == 0
        completed_key = (
            "_org_firmware_upgrades_total",
            (
                ("org_id", org_id),
                ("product_type", "switch"),
                ("status", "Completed"),
            ),
        )
        assert parent._metrics[completed_key] == 1

    async def test_collect_cancelled_spellings_not_pending(
        self, firmware_collector, mock_api_builder
    ):
        """#526: verify both cancel spellings are counted and never treated as pending.

        Both 'Canceled' (single-L, observed live) and 'Cancelled' (spec spelling) must be
        counted in the total gauge under their own raw status label, and neither spelling
        should ever be treated as pending.
        """
        org_id = "526"
        org_name = "Cancel Spelling Org"

        upgrades_response = [
            {
                "upgradeId": "1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "Canceled",
                "productTypes": "switch",
            },
            {
                "upgradeId": "2",
                "network": {"id": "n2", "name": "Network 2"},
                "status": "Cancelled",
                "productTypes": "switch",
            },
            {
                "upgradeId": "3",
                "network": {"id": "n3", "name": "Network 3"},
                "status": "CANCELED",
                "productTypes": "wireless",
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", upgrades_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent

        for product_type, status in (
            ("switch", "Canceled"),
            ("switch", "Cancelled"),
            ("wireless", "CANCELED"),
        ):
            key = (
                "_org_firmware_upgrades_total",
                (
                    ("org_id", org_id),
                    ("product_type", product_type),
                    ("status", status),
                ),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == 1

        # Neither cancel spelling (in any case) should ever register as pending.
        for product_type in ("switch", "wireless"):
            pending_key = (
                "_org_firmware_upgrades_pending_total",
                (("org_id", org_id), ("product_type", product_type)),
            )
            assert pending_key not in parent._metrics

    async def test_collect_zeroes_stale_combos_on_quiet_window(
        self, firmware_collector, mock_api_builder
    ):
        """F-056: an empty response (no events this window) must still zero prior combos."""
        org_id = "888"
        org_name = "Quiet Org"

        first_response = [
            {
                "upgradeId": "1",
                "network": {"id": "n1", "name": "Network 1"},
                "status": "Completed",
                "productTypes": "appliance",
            },
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgrades", first_response
        ).build()
        firmware_collector.api = api

        await firmware_collector.collect(org_id, org_name)

        parent = firmware_collector.parent
        total_key = (
            "_org_firmware_upgrades_total",
            (
                ("org_id", org_id),
                ("product_type", "appliance"),
                ("status", "Completed"),
            ),
        )
        assert parent._metrics[total_key] == 1

        api2 = mock_api_builder.with_custom_response("getOrganizationFirmwareUpgrades", []).build()
        firmware_collector.api = api2

        await firmware_collector.collect(org_id, org_name)

        assert parent._metrics[total_key] == 0
