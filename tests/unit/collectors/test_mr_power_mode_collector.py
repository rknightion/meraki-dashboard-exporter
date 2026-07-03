"""Tests for MR current power-mode gauge (#325) on MRPerformanceCollector."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr.performance import MRPerformanceCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName


def _make_gauge(name: object, description: str, labelnames: list[str]) -> Gauge:
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


class TestMRPowerModeCollection:
    """Test collect_power_mode on MRPerformanceCollector."""

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
        parent.settings.api.batch_size = 20
        parent.inventory = None
        parent.rate_limiter = None
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        parent._should_run_group = MagicMock(return_value=True)
        parent._group_ttl_seconds = MagicMock(return_value=None)
        parent._mark_group_ran = MagicMock()
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def collector(self, mock_parent: MagicMock) -> MRPerformanceCollector:
        """Collector."""
        return MRPerformanceCollector(mock_parent)

    def test_power_mode_gauge_created(
        self, collector: MRPerformanceCollector, mock_parent: MagicMock
    ) -> None:
        """Power mode gauge created."""
        names = {c.args[0] for c in mock_parent._create_gauge.call_args_list}
        assert MRMetricName.MR_POWER_MODE in names
        pm_call = next(
            c
            for c in mock_parent._create_gauge.call_args_list
            if c.args[0] == MRMetricName.MR_POWER_MODE
        )
        assert set(pm_call.kwargs["labelnames"]) == {
            "org_id",
            "network_id",
            "serial",
            "model",
            "device_type",
            "mode",
        }

    async def test_emits_newest_power_mode_one_hot(
        self, collector: MRPerformanceCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Emits newest power mode one hot."""
        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory = MagicMock(
            return_value=[
                {
                    "serial": "Q1",
                    "model": "MR46",
                    "network": {"id": "net1"},
                    "events": [
                        {"ts": "2026-07-03T09:00:00Z", "powerMode": "low"},
                        {"ts": "2026-07-03T11:00:00Z", "powerMode": "full"},
                    ],
                }
            ]
        )

        await collector.collect_power_mode("org1", "Org", {})

        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory.assert_called_once_with(
            "org1", total_pages="all", timespan=86400
        )
        pm_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_power_mode
        ]
        assert len(pm_calls) == 1
        labels = pm_calls[0].args[1]
        assert labels["serial"] == "Q1"
        assert labels["mode"] == "full"
        assert labels["model"] == "MR46"
        assert labels["device_type"] == "MR"
        assert pm_calls[0].args[2] == 1.0

    async def test_device_without_events_skipped(
        self, collector: MRPerformanceCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Device without events skipped."""
        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory = MagicMock(
            return_value=[{"serial": "Q1", "network": {"id": "net1"}, "events": []}]
        )
        await collector.collect_power_mode("org1", "Org", {})
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MR_POWER_MODE)

    async def test_respects_network_filter(
        self, collector: MRPerformanceCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Respects network filter."""
        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "network": {"id": "N_IN"},
                    "events": [{"ts": "t", "powerMode": "full"}],
                },
                {
                    "serial": "Q-OUT",
                    "network": {"id": "N_OUT"},
                    "events": [{"ts": "t", "powerMode": "low"}],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_IN"})

        await collector.collect_power_mode("org1", "Org", {})
        pm_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_power_mode
        ]
        assert len(pm_calls) == 1
        assert pm_calls[0].args[1]["serial"] == "Q-IN"

    async def test_gate_closed_skips_fetch(
        self, collector: MRPerformanceCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Gate closed skips fetch."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        await collector.collect_power_mode("org1", "Org", {})
        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_error_shape_absorbed(
        self, collector: MRPerformanceCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Error shape absorbed."""
        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )
        await collector.collect_power_mode("org1", "Org", {})
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_ttl_threaded(
        self, collector: MRPerformanceCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Ttl threaded."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=900.0)
        mock_api.wireless.getOrganizationWirelessDevicesPowerModeHistory = MagicMock(
            return_value=[
                {
                    "serial": "Q1",
                    "model": "MR46",
                    "network": {"id": "net1"},
                    "events": [{"ts": "t", "powerMode": "full"}],
                }
            ]
        )
        await collector.collect_power_mode("org1", "Org", {})
        pm_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c.args[0] is collector._mr_power_mode
        ]
        assert pm_calls
        for c in pm_calls:
            assert c.kwargs["ttl_seconds"] == 900.0
