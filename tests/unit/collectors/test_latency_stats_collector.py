"""Tests for the LatencyStatsCollector (MR wireless latency stats)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.network_health_collectors.latency_stats import (
    LatencyStatsCollector,
)

if TYPE_CHECKING:
    pass


class TestLatencyStatsCollector:
    """Test LatencyStatsCollector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.wireless = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent NetworkHealthCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def collector(self, mock_parent: MagicMock) -> LatencyStatsCollector:
        """Create the collector instance."""
        return LatencyStatsCollector(mock_parent)

    @pytest.fixture
    def network(self) -> dict:
        """Standard network dict, already NetworkFilter-stamped by the coordinator."""
        return {
            "id": "N_1",
            "name": "Test Network",
            "orgId": "org_1",
            "orgName": "Test Org",
        }

    def test_initialization(self, collector: LatencyStatsCollector, mock_parent: MagicMock) -> None:
        """Test collector initialization sets up parent/api/settings."""
        assert collector.parent == mock_parent
        assert collector.api == mock_parent.api
        assert collector.settings == mock_parent.settings

    def test_gauges_created(self, collector: LatencyStatsCollector, mock_parent: MagicMock) -> None:
        """Test that both device and client latency gauges are created on init."""
        assert mock_parent._create_gauge.call_count == 2
        assert collector._mr_device_latency_ms is not None
        assert collector._mr_network_client_latency_ms is not None

    async def test_device_latency_all_traffic_classes(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that per-AP latency is emitted for each traffic class."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "latencyStats": {
                        "backgroundTraffic": {"avg": 10.0},
                        "bestEffortTraffic": {"avg": 20.0},
                        "videoTraffic": {"avg": 30.0},
                        "voiceTraffic": {"avg": 5.0},
                    },
                }
            ]
        )
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(return_value=[])

        await collector.collect(network)

        # 4 device emissions (one per traffic class); no client aggregate (empty client rows)
        assert mock_parent._set_metric.call_count == 4
        emitted = {
            call[0][1]["traffic_class"]: call[0][2]
            for call in mock_parent._set_metric.call_args_list
        }
        # API reports milliseconds; converted /1000 to seconds (#531).
        assert emitted == {
            "background": 0.01,
            "best_effort": 0.02,
            "video": 0.03,
            "voice": 0.005,
        }
        for call in mock_parent._set_metric.call_args_list:
            gauge, labels, _value, metric_name = call[0]
            assert gauge is collector._mr_device_latency_ms
            assert labels["serial"] == "Q2AB-0001"
            assert labels["network_id"] == "N_1"
            assert metric_name == "meraki_mr_device_latency_seconds"

    async def test_device_latency_null_avg_skipped(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that a null avg for a traffic class is skipped, others still emit."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "latencyStats": {
                        "backgroundTraffic": {"avg": None},
                        "bestEffortTraffic": {"avg": 20.0},
                        "videoTraffic": {"avg": None},
                        "voiceTraffic": {"avg": 5.0},
                    },
                }
            ]
        )
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(return_value=[])

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 2
        emitted_classes = {
            call[0][1]["traffic_class"] for call in mock_parent._set_metric.call_args_list
        }
        assert emitted_classes == {"best_effort", "voice"}

    async def test_client_aggregate_is_mean(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that the network-wide client latency is the mean across clients, per class."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(return_value=[])
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(
            return_value=[
                {
                    "mac": "aa:bb:cc:dd:ee:01",
                    "latencyStats": {
                        "backgroundTraffic": {"avg": 10.0},
                        "bestEffortTraffic": {"avg": 20.0},
                        "videoTraffic": {"avg": 30.0},
                        "voiceTraffic": {"avg": 40.0},
                    },
                },
                {
                    "mac": "aa:bb:cc:dd:ee:02",
                    "latencyStats": {
                        "backgroundTraffic": {"avg": 30.0},
                        "bestEffortTraffic": {"avg": 40.0},
                        "videoTraffic": {"avg": 50.0},
                        "voiceTraffic": {"avg": 60.0},
                    },
                },
            ]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 4
        emitted = {
            call[0][1]["traffic_class"]: call[0][2]
            for call in mock_parent._set_metric.call_args_list
        }
        # API reports milliseconds; converted /1000 to seconds (#531).
        assert emitted == {
            "background": 0.02,
            "best_effort": 0.03,
            "video": 0.04,
            "voice": 0.05,
        }
        for call in mock_parent._set_metric.call_args_list:
            gauge, labels, _value, metric_name = call[0]
            assert gauge is collector._mr_network_client_latency_ms
            assert "mac" not in labels
            assert "serial" not in labels
            assert metric_name == "meraki_mr_network_client_latency_seconds"

    async def test_client_aggregate_skips_null_avg_per_client(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that a client with a null avg for one class doesn't pollute that class's mean."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(return_value=[])
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(
            return_value=[
                {
                    "mac": "aa:bb:cc:dd:ee:01",
                    "latencyStats": {
                        "backgroundTraffic": {"avg": 10.0},
                        "bestEffortTraffic": {"avg": None},
                        "videoTraffic": {"avg": None},
                        "voiceTraffic": {"avg": None},
                    },
                },
                {
                    "mac": "aa:bb:cc:dd:ee:02",
                    "latencyStats": {
                        "backgroundTraffic": {"avg": 30.0},
                        "bestEffortTraffic": {"avg": None},
                        "videoTraffic": {"avg": None},
                        "voiceTraffic": {"avg": None},
                    },
                },
            ]
        )

        await collector.collect(network)

        # Only background traffic has any non-null data across clients
        assert mock_parent._set_metric.call_count == 1
        gauge, labels, value, _metric_name = mock_parent._set_metric.call_args_list[0][0]
        assert gauge is collector._mr_network_client_latency_ms
        assert labels["traffic_class"] == "background"
        assert value == 0.02

    async def test_no_client_rows_skips_aggregate(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that an empty client latency stats response emits nothing for the aggregate."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(return_value=[])
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(return_value=[])

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_device_fetch_error_does_not_prevent_client_aggregate(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that a failing device-latency fetch doesn't kill the client aggregate fetch."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(
            side_effect=Exception("API connection failed")
        )
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(
            return_value=[
                {
                    "mac": "aa:bb:cc:dd:ee:01",
                    "latencyStats": {"backgroundTraffic": {"avg": 15.0}},
                },
            ]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 1
        gauge, labels, value, _metric_name = mock_parent._set_metric.call_args_list[0][0]
        assert gauge is collector._mr_network_client_latency_ms
        assert labels["traffic_class"] == "background"
        assert value == 0.015

    async def test_client_fetch_error_does_not_prevent_device_emission(
        self,
        collector: LatencyStatsCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that a failing client-latency fetch doesn't kill the device emission."""
        mock_api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "latencyStats": {"backgroundTraffic": {"avg": 12.0}},
                },
            ]
        )
        mock_api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 1
        gauge, labels, value, _metric_name = mock_parent._set_metric.call_args_list[0][0]
        assert gauge is collector._mr_device_latency_ms
        assert labels["serial"] == "Q2AB-0001"
        assert value == 0.012
