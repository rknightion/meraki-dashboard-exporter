"""Tests for the MeshCollector (wireless mesh link health, #307)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.network_health_collectors.mesh import (
    MeshCollector,
)

if TYPE_CHECKING:
    pass


class TestMeshCollector:
    """Test MeshCollector functionality."""

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
        parent._group_ttl_seconds = MagicMock(return_value=None)
        return parent

    @pytest.fixture
    def collector(self, mock_parent: MagicMock) -> MeshCollector:
        """Create the collector instance."""
        return MeshCollector(mock_parent)

    @pytest.fixture
    def network(self) -> dict:
        """Standard network dict, already NetworkFilter-stamped by the coordinator."""
        return {
            "id": "N_1",
            "name": "Test Network",
            "orgId": "org_1",
            "orgName": "Test Org",
        }

    def test_initialization(self, collector: MeshCollector, mock_parent: MagicMock) -> None:
        """Test collector initialization sets up parent/api/settings."""
        assert collector.parent == mock_parent
        assert collector.api == mock_parent.api
        assert collector.settings == mock_parent.settings

    def test_gauges_created(self, collector: MeshCollector, mock_parent: MagicMock) -> None:
        """Test that all three mesh gauges are created on init."""
        assert mock_parent._create_gauge.call_count == 3
        assert collector._mesh_throughput_bps is not None
        assert collector._mesh_route_metric is not None
        assert collector._mesh_usage_percent is not None

    async def test_single_repeater_emits_all_three_series(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a single repeater entry emits throughput/metric/usage series."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q234-ABCD-5678",
                    "meshRoute": ["Q234-ABCD-5678", "QWEY-SKTD-ST01"],
                    "latestMeshPerformance": {
                        "mbps": 43,
                        "metric": 12345,
                        "usagePercentage": "50%",
                    },
                }
            ]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 3
        emitted = {call[0][0]: call[0][2] for call in mock_parent._set_metric.call_args_list}
        assert emitted[collector._mesh_throughput_bps] == pytest.approx(43 * 1_000_000 / 8)
        assert emitted[collector._mesh_route_metric] == 12345.0
        assert emitted[collector._mesh_usage_percent] == 50.0

        for call in mock_parent._set_metric.call_args_list:
            _gauge, labels, _value, _metric_name = call[0]
            assert labels["network_id"] == "N_1"
            assert labels["org_id"] == "org_1"
            assert labels["serial"] == "Q234-ABCD-5678"

    async def test_metric_names(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that the correct metric name string is passed for each gauge."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q234-ABCD-5678",
                    "latestMeshPerformance": {"mbps": 1, "metric": 1, "usagePercentage": "1%"},
                }
            ]
        )

        await collector.collect(network)

        metric_names = {call[0][3] for call in mock_parent._set_metric.call_args_list}
        assert metric_names == {
            "meraki_mr_mesh_throughput_bytes_per_second",
            "meraki_mr_mesh_route_metric",
            "meraki_mr_mesh_usage_percent",
        }

    async def test_usage_percentage_as_bare_number(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test usagePercentage parses leniently when given as a bare number, not a string."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q234-ABCD-5678",
                    "latestMeshPerformance": {"usagePercentage": 75},
                }
            ]
        )

        await collector.collect(network)

        emitted = {call[0][0]: call[0][2] for call in mock_parent._set_metric.call_args_list}
        assert emitted[collector._mesh_usage_percent] == 75.0

    async def test_empty_response_emits_nothing(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a network with no repeaters (empty list) emits no series (not zero)."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(return_value=[])

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_missing_serial_skips_row(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a row without a serial is skipped rather than crashing."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[{"latestMeshPerformance": {"mbps": 10}}]
        )

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_missing_latest_mesh_performance_skips_gracefully(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a row missing latestMeshPerformance entirely doesn't crash or emit."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[{"serial": "Q234-ABCD-5678"}]
        )

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_partial_performance_fields_emit_only_present_ones(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test only the present sub-fields are emitted when some are null/absent."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q234-ABCD-5678",
                    "latestMeshPerformance": {"mbps": None, "metric": 99},
                }
            ]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 1
        emitted = {call[0][0]: call[0][2] for call in mock_parent._set_metric.call_args_list}
        assert emitted[collector._mesh_route_metric] == 99.0
        assert collector._mesh_throughput_bps not in emitted
        assert collector._mesh_usage_percent not in emitted

    async def test_400_error_handled_gracefully_as_debug(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a 400 (no repeaters on this network - the common case) doesn't crash."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            side_effect=Exception("400 Bad Request")
        )

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_404_error_handled_gracefully(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a 404 doesn't crash and emits nothing."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            side_effect=Exception("404 Not Found")
        )

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_generic_error_handled_gracefully(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test a non-4xx error is swallowed (logged) rather than raised."""
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            side_effect=Exception("connection reset by peer")
        )

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_ttl_forwarded_from_group(
        self,
        collector: MeshCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test the per-group TTL is forwarded to every _set_metric call."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=999.0)
        mock_api.wireless.getNetworkWirelessMeshStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q234-ABCD-5678",
                    "latestMeshPerformance": {"mbps": 1, "metric": 1, "usagePercentage": "1%"},
                }
            ]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 3
        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs.get("ttl_seconds") == 999.0
