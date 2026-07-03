"""Tests for MR Catalyst wireless-controller association collector (#326)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr.catalyst import MRCatalystCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName


def _make_gauge(name: object, description: str, labelnames: list[str]) -> Gauge:
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


class TestMRCatalystCollector:
    """Test the Catalyst wireless-controller association collector."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock api."""
        api = MagicMock()
        api.wireless = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Mock parent."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.inventory = None
        parent.rate_limiter = None
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        parent._should_run_group = MagicMock(return_value=True)
        parent._group_ttl_seconds = MagicMock(return_value=None)
        parent._mark_group_ran = MagicMock()
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def collector(self, mock_parent: MagicMock) -> MRCatalystCollector:
        """Collector."""
        return MRCatalystCollector(mock_parent)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation_creates_metrics(
        self, collector: MRCatalystCollector, mock_parent: MagicMock
    ) -> None:
        """Initialisation creates metrics."""
        names = {c.args[0] for c in mock_parent._create_gauge.call_args_list}
        assert names == {
            MRMetricName.MR_WIRELESS_CONTROLLER_INFO,
            MRMetricName.MR_WIRELESS_CONTROLLER_JOINED_TIMESTAMP_SECONDS,
        }
        info_call = next(
            c
            for c in mock_parent._create_gauge.call_args_list
            if c.args[0] == MRMetricName.MR_WIRELESS_CONTROLLER_INFO
        )
        assert set(info_call.kwargs["labelnames"]) == {
            "org_id",
            "network_id",
            "serial",
            "model",
            "controller_serial",
            "mode",
            "country_code",
        }

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    async def test_emits_info_and_timestamp(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Emits info and timestamp."""
        joined = "2026-06-01T12:00:00Z"
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value=[
                {
                    "serial": "CW1",
                    "model": "CW9166I",
                    "network": {"id": "net1"},
                    "controller": {"serial": "CTRL-1"},
                    "joinedAt": joined,
                    "mode": "local",
                    "countryCode": "US",
                    "tags": ["ignored"],
                    "details": [{"name": "x", "value": "y"}],
                }
            ]
        )

        await collector.collect_wireless_controllers("org1", "Org")

        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice.assert_called_once_with(
            "org1", total_pages="all", perPage=1000
        )

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_wireless_controller_info
        ]
        assert len(info_calls) == 1
        labels = info_calls[0].args[1]
        assert labels == {
            "org_id": "org1",
            "network_id": "net1",
            "serial": "CW1",
            "model": "CW9166I",
            "controller_serial": "CTRL-1",
            "mode": "local",
            "country_code": "US",
        }
        assert info_calls[0].args[2] == 1.0

        ts_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_wireless_controller_joined_timestamp_seconds
        ]
        assert len(ts_calls) == 1
        expected = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC).timestamp()
        assert ts_calls[0].args[2] == expected
        assert set(ts_calls[0].args[1]) == {"org_id", "network_id", "serial"}

    async def test_missing_serial_skipped(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Missing serial skipped."""
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value=[{"network": {"id": "net1"}, "controller": {"serial": "C"}}]
        )
        await collector.collect_wireless_controllers("org1", "Org")
        mock_parent._set_metric.assert_not_called()

    async def test_unparseable_joined_at_skips_timestamp_only(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Unparseable joined at skips timestamp only."""
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value=[
                {
                    "serial": "CW1",
                    "model": "CW9166I",
                    "network": {"id": "net1"},
                    "controller": {"serial": "C"},
                    "joinedAt": "not-a-date",
                    "mode": "local",
                    "countryCode": "GB",
                }
            ]
        )
        await collector.collect_wireless_controllers("org1", "Org")
        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_wireless_controller_info
        ]
        ts_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_wireless_controller_joined_timestamp_seconds
        ]
        assert len(info_calls) == 1
        assert ts_calls == []

    async def test_empty_response_is_noop(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Empty response is noop."""
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value=[]
        )
        await collector.collect_wireless_controllers("org1", "Org")
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_called_once_with(
            EndpointGroupName.MR_WIRELESS_CONTROLLER
        )

    # ------------------------------------------------------------------
    # NetworkFilter enforcement
    # ------------------------------------------------------------------

    async def test_respects_network_filter(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Respects network filter."""
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value=[
                {"serial": "CW-IN", "network": {"id": "N_IN"}, "controller": {"serial": "C"}},
                {"serial": "CW-OUT", "network": {"id": "N_OUT"}, "controller": {"serial": "C"}},
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_IN"})

        await collector.collect_wireless_controllers("org1", "Org")

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_wireless_controller_info
        ]
        assert len(info_calls) == 1
        assert info_calls[0].args[1]["serial"] == "CW-IN"

    # ------------------------------------------------------------------
    # Scheduler gating + error handling
    # ------------------------------------------------------------------

    async def test_gate_closed_skips_fetch(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Gate closed skips fetch."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        await collector.collect_wireless_controllers("org1", "Org")
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_error_shape_absorbed(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Error shape absorbed."""
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )
        await collector.collect_wireless_controllers("org1", "Org")
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_ttl_threaded(
        self, collector: MRCatalystCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Ttl threaded."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=3600.0)
        mock_api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice = MagicMock(
            return_value=[
                {
                    "serial": "CW1",
                    "network": {"id": "net1"},
                    "controller": {"serial": "C"},
                    "joinedAt": "2026-06-01T12:00:00Z",
                }
            ]
        )
        await collector.collect_wireless_controllers("org1", "Org")
        for c in mock_parent._set_metric.call_args_list:
            assert c.kwargs["ttl_seconds"] == 3600.0
