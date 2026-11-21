"""Tests for FirmwareCollector.collect_compliance (#611)."""

from __future__ import annotations

import json
from pathlib import Path
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
        self._device_firmware_info = None

    def _expire_metric_series(
        self, metric: object, labels: dict[str, str], metric_name: str | None = None
    ) -> None:
        pass

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

    @staticmethod
    def _key(org_id: str, network_id: str):
        return ("_network_firmware_up_to_date", (("network_id", network_id), ("org_id", org_id)))

    async def test_network_up_to_date_when_no_pending(self, mock_api_builder):
        """A network whose rows are all finished reports up_to_date=1."""
        org_id = "org2"
        devices = [
            {"serial": "S1", "model": "MS120-8", "networkId": "N_A"},
            {"serial": "S2", "model": "MR46", "networkId": "N_A"},
        ]
        by_device = [
            {"serial": "S1", "upgrade": {"status": "Completed"}},
            {"serial": "S2", "upgrade": {"status": "Completed"}},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Two")

        assert collector.parent._metrics[self._key(org_id, "N_A")] == 1

    async def test_network_not_up_to_date_when_pending(self, mock_api_builder):
        """A network with a scheduled or started upgrade reports 0, case-insensitively."""
        org_id = "org3"
        devices = [
            {"serial": "S1", "model": "MS120-8", "networkId": "N_B"},
            {"serial": "S2", "model": "MR46", "networkId": "N_B"},
            {"serial": "S3", "model": "MS120-8", "networkId": "N_C"},
            {"serial": "S4", "model": "MS120-8", "networkId": "N_D"},
        ]
        by_device = [
            {"serial": "S1", "upgrade": {"status": "Completed"}},
            {"serial": "S2", "upgrade": {"status": "Scheduled"}},
            {"serial": "S3", "upgrade": {"status": "started"}},
            {"serial": "S4", "upgrade": {"status": "canceled"}},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Three")

        m = collector.parent._metrics
        assert m[self._key(org_id, "N_B")] == 0
        assert m[self._key(org_id, "N_C")] == 0
        assert m[self._key(org_id, "N_D")] == 1

    async def test_unknown_or_missing_status_does_not_mark_pending(self, mock_api_builder):
        """A status the spec does not list, or no status at all, never turns a network to 0."""
        org_id = "org3b"
        devices = [
            {"serial": "S1", "model": "MS120-8", "networkId": "N_E"},
            {"serial": "S2", "model": "MS120-8", "networkId": "N_E"},
            {"serial": "S3", "model": "MS120-8", "networkId": "N_E"},
        ]
        by_device = [
            {"serial": "S1", "upgrade": {"status": "in_progress"}},
            {"serial": "S2", "upgrade": {}},
            {"serial": "S3"},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Three B")

        assert collector.parent._metrics[self._key(org_id, "N_E")] == 1

    async def test_network_filter_excludes_rows(self, mock_api_builder):
        """Networks outside the allow-list get no sample, however their rows look."""
        org_id = "org4"
        devices = [
            {"serial": "S1", "model": "MS120-8", "networkId": "N_IN"},
            {"serial": "S2", "model": "MS120-8", "networkId": "N_OUT"},
        ]
        by_device = [
            {"serial": "S1", "upgrade": {"status": "Scheduled"}},
            {"serial": "S2", "upgrade": {"status": "Scheduled"}},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder, devices=devices, allowed={"N_IN"})
        collector.api = api

        await collector.collect_compliance(org_id, "Org Four")

        m = collector.parent._metrics
        assert m[self._key(org_id, "N_IN")] == 0
        assert self._key(org_id, "N_OUT") not in m

    async def test_network_without_rows_is_up_to_date(self, mock_api_builder):
        """A switch or AP network with no current upgrade row reports 1, others no sample."""
        org_id = "org7"
        devices = [
            {"serial": "S1", "model": "MS120-8", "networkId": "N_QUIET"},
            {"serial": "S2", "model": "CW9162", "productType": "wireless", "networkId": "N_WIFI"},
            {"serial": "S3", "model": "MX68", "networkId": "N_MX"},
            {"serial": "S4", "model": "MS120-8"},
            {"model": "MS120-8", "networkId": "N_NOSERIAL"},
        ]
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", []
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Seven")

        m = collector.parent._metrics
        assert m[self._key(org_id, "N_QUIET")] == 1
        assert m[self._key(org_id, "N_WIFI")] == 1
        assert self._key(org_id, "N_MX") not in m
        assert self._key(org_id, "N_NOSERIAL") not in m

    async def test_corpus_fixture_resolves_network_from_inventory(self, mock_api_builder):
        """The live-verified by-device capture has no network key; inventory supplies it."""
        org_id = "org8"
        corpus = (
            Path(__file__).resolve().parents[1]
            / "harness"
            / "corpus"
            / "get-organization-firmware-upgrades-by-device-01.json"
        )
        by_device = json.loads(corpus.read_text())
        assert by_device
        assert all("network" not in row for row in by_device)
        serials = sorted({row["serial"] for row in by_device})
        assert len(serials) == 10
        devices = [
            {"serial": serial, "model": "MS120-8", "networkId": "N_SW"} for serial in serials
        ]
        devices.append({"serial": "Q2MX-0000-0001", "model": "MX68", "networkId": "N_APPLIANCE"})
        api = mock_api_builder.with_custom_response(
            "getOrganizationFirmwareUpgradesByDevice", by_device
        ).build()
        collector = self._collector(mock_api_builder, devices=devices)
        collector.api = api

        await collector.collect_compliance(org_id, "Org Eight")

        m = collector.parent._metrics
        assert m[self._key(org_id, "N_SW")] == 1
        assert self._key(org_id, "N_APPLIANCE") not in m
        call = api.organizations.getOrganizationFirmwareUpgradesByDevice.call_args
        assert call.kwargs["currentUpgradesOnly"] is True
        assert call.kwargs["perPage"] == 1000

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
