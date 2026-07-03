"""Tests for FirmwareCollector.collect_compliance (#611)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.firmware import (
    FirmwareCollector,
)


class _MockParent:
    def __init__(self, api) -> None:
        self.api = api
        self.settings = None
        self.inventory = MagicMock()
        self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def _should_run_group(self, group: object) -> bool:
        return True

    def _mark_group_ran(self, group: object) -> None:
        pass

    def _group_ttl_seconds(self, group: object) -> float | None:
        return None

    def _track_api_call(self, method_name: str) -> None:
        pass

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


class TestFirmwareComplianceCollector:
    """Test firmware compliance (#611)."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    def _collector(self, mock_api_builder, devices=None, allowed=None) -> FirmwareCollector:
        parent = _MockParent(mock_api_builder.build())
        parent.inventory.get_devices = AsyncMock(return_value=devices or [])
        parent.inventory.get_allowed_network_ids = AsyncMock(return_value=allowed)
        collector = FirmwareCollector(parent=parent)  # type: ignore[arg-type]
        # BaseOrganizationCollector reads inventory from parent at construction.
        collector.inventory = parent.inventory
        return collector

    async def test_device_firmware_info_emitted_from_inventory(self, mock_api_builder):
        """Device firmware info rides cached inventory (value 1, join on serial)."""
        org_id = "org1"
        devices = [
            {
                "serial": "Q2AA-1111-2222",
                "model": "MR46",
                "networkId": "N_1",
                "firmware": "wireless-30-7",
            },
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", []
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        result = await collector.collect_compliance(org_id, "Org One")
        assert result is True

        key = (
            "_device_firmware_info",
            (
                ("device_type", "MR"),
                ("firmware", "wireless-30-7"),
                ("model", "MR46"),
                ("network_id", "N_1"),
                ("org_id", org_id),
                ("serial", "Q2AA-1111-2222"),
            ),
        )
        assert collector.parent._metrics[key] == 1

    async def test_network_up_to_date_when_no_pending(self, mock_api_builder):
        """A network with no pending device upgrade reports up_to_date=1."""
        org_id = "org2"
        by_device = [
            {"serial": "S1", "network": {"id": "N_A"}, "upgrade": {"status": "Completed"}},
            {"serial": "S2", "network": {"id": "N_A"}, "upgrade": {"status": "Nothing to upgrade"}},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Two")

        key = ("_network_firmware_up_to_date", (("network_id", "N_A"), ("org_id", org_id)))
        assert collector.parent._metrics[key] == 1

    async def test_network_not_up_to_date_when_pending(self, mock_api_builder):
        """A network with any pending/scheduled device upgrade reports 0."""
        org_id = "org3"
        by_device = [
            {"serial": "S1", "network": {"id": "N_B"}, "upgrade": {"status": "Completed"}},
            {"serial": "S2", "network": {"id": "N_B"}, "upgrade": {"status": "Scheduled"}},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Three")

        key = ("_network_firmware_up_to_date", (("network_id", "N_B"), ("org_id", org_id)))
        assert collector.parent._metrics[key] == 0

    async def test_network_filter_excludes_rows(self, mock_api_builder):
        """By-device rows for networks outside the filter are skipped."""
        org_id = "org4"
        by_device = [
            {"serial": "S1", "network": {"id": "N_IN"}, "upgrade": {"status": "Scheduled"}},
            {"serial": "S2", "network": {"id": "N_OUT"}, "upgrade": {"status": "Scheduled"}},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder, allowed={"N_IN"})
        collector.api = api

        await collector.collect_compliance(org_id, "Org Four")

        m = collector.parent._metrics
        assert ("_network_firmware_up_to_date", (("network_id", "N_IN"), ("org_id", org_id))) in m
        assert (
            "_network_firmware_up_to_date",
            (("network_id", "N_OUT"), ("org_id", org_id)),
        ) not in m

    async def test_top_level_status_fallback(self, mock_api_builder):
        """A top-level `status` (no nested upgrade) is still honoured."""
        org_id = "org5"
        by_device = [
            {"serial": "S1", "network": {"id": "N_C"}, "status": "pending"},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Five")
        key = ("_network_firmware_up_to_date", (("network_id", "N_C"), ("org_id", org_id)))
        assert collector.parent._metrics[key] == 0

    async def test_by_device_404_still_emits_device_info(self, mock_api_builder):
        """A 404 on the by-device endpoint is benign; device info still emitted."""
        org_id = "org6"
        devices = [
            {"serial": "S9", "model": "MS220-8P", "networkId": "N_9", "firmware": "switch-16"},
        ]
        api = mock_api_builder.with_error(
            "getOrganizationFirmwareUpgradesByDevice", Exception("404 Not Found")
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        result = await collector.collect_compliance(org_id, "Org Six")
        assert result is True
        info_keys = [k for k in collector.parent._metrics if k[0] == "_device_firmware_info"]
        assert len(info_keys) == 1
