"""Tests for MX uplink health (loss/latency) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx_uplink_health import (
    MXUplinkHealthCollector,
)

if TYPE_CHECKING:
    pass


class TestMXUplinkHealthCollector:
    """Test MX uplink health collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.organizations = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collectors emit all rows.
        parent.inventory = None

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def collector(
        self,
        mock_parent: MagicMock,
    ) -> MXUplinkHealthCollector:
        """Create MX uplink health collector instance."""
        return MXUplinkHealthCollector(mock_parent)

    def test_initialization(
        self,
        collector: MXUplinkHealthCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test collector initialization sets up parent/api/settings and gauges."""
        assert collector.parent == mock_parent
        assert collector.api == mock_parent.api
        assert collector.settings == mock_parent.settings

    def test_gauges_created(
        self,
        collector: MXUplinkHealthCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that both loss and latency gauges are created on init."""
        assert mock_parent._create_gauge.call_count == 2
        assert collector._mx_uplink_loss_percent is not None
        assert collector._mx_uplink_latency_ms is not None

    async def test_basic_emission_latest_point(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that the latest non-null loss/latency sample is emitted."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_111",
                    "serial": "Q2AB-1234-5678",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "2026-07-01T00:00:00Z", "lossPercent": 1.0, "latencyMs": 10.0},
                        {"ts": "2026-07-01T00:01:00Z", "lossPercent": 0.5, "latencyMs": 12.5},
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2AB-1234-5678": {
                "name": "Office MX",
                "model": "MX68",
                "network_id": "N_111",
                "network_name": "Office Network",
                "device_type": "MX",
            }
        }

        await collector.collect_uplink_loss_latency("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 2

        gauge_0, labels_0, value_0, _ = mock_parent._set_metric.call_args_list[0][0]
        assert gauge_0 is collector._mx_uplink_loss_percent
        assert labels_0["serial"] == "Q2AB-1234-5678"
        assert labels_0["name"] == "Office MX"
        assert labels_0["interface"] == "wan1"
        assert labels_0["network_name"] == "Office Network"
        assert value_0 == 0.5

        gauge_1, labels_1, value_1, _ = mock_parent._set_metric.call_args_list[1][0]
        assert gauge_1 is collector._mx_uplink_latency_ms
        assert labels_1["interface"] == "wan1"
        assert value_1 == 12.5

    async def test_multiple_uplinks_per_device(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection across multiple uplinks for the same device."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 0.0, "latencyMs": 5.0},
                    ],
                },
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan2",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 2.0, "latencyMs": 20.0},
                    ],
                },
            ]
        )

        device_lookup = {
            "Q2AB-0001": {
                "name": "Branch MX",
                "model": "MX68",
                "network_id": "N_1",
                "network_name": "Branch",
                "device_type": "MX",
            },
        }

        await collector.collect_uplink_loss_latency("org1", "Test Org", device_lookup)

        # 2 uplinks * (loss + latency) = 4 metric emissions
        assert mock_parent._set_metric.call_count == 4
        interfaces = {call[0][1]["interface"] for call in mock_parent._set_metric.call_args_list}
        assert interfaces == {"wan1", "wan2"}

    async def test_multiple_ip_rows_same_uplink_last_write_wins(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that multiple destination-ip rows for the same uplink don't explode cardinality.

        The endpoint returns one row per (device, uplink, destination-ip); we
        label only by interface, so the last row processed wins.
        """
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0},
                    ],
                },
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "1.1.1.1",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 3.0, "latencyMs": 30.0},
                    ],
                },
            ]
        )

        device_lookup = {
            "Q2AB-0001": {
                "name": "Branch MX",
                "model": "MX68",
                "network_id": "N_1",
                "network_name": "Branch",
                "device_type": "MX",
            },
        }

        await collector.collect_uplink_loss_latency("org1", "Test Org", device_lookup)

        # Both rows emit (2 rows * 2 metrics), but only "interface" is labeled,
        # so the second (last) row's values are what a real Gauge would retain.
        assert mock_parent._set_metric.call_count == 4
        last_loss_call = mock_parent._set_metric.call_args_list[2][0]
        last_latency_call = mock_parent._set_metric.call_args_list[3][0]
        assert last_loss_call[2] == 3.0
        assert last_latency_call[2] == 30.0

    async def test_null_trailing_timeseries_picks_last_non_null(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that a trailing null sample doesn't hide the last real value."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0},
                        {"ts": "t2", "lossPercent": 2.0, "latencyMs": 20.0},
                        {"ts": "t3", "lossPercent": None, "latencyMs": None},
                    ],
                },
            ]
        )

        device_lookup = {
            "Q2AB-0001": {
                "name": "Branch MX",
                "model": "MX68",
                "network_id": "N_1",
                "network_name": "Branch",
                "device_type": "MX",
            },
        }

        await collector.collect_uplink_loss_latency("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 2
        _, _, loss_value, _ = mock_parent._set_metric.call_args_list[0][0]
        _, _, latency_value, _ = mock_parent._set_metric.call_args_list[1][0]
        assert loss_value == 2.0
        assert latency_value == 20.0

    async def test_loss_and_latency_become_null_independently(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that loss and latency are picked independently from the time series."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0},
                        {"ts": "t2", "lossPercent": None, "latencyMs": 25.0},
                    ],
                },
            ]
        )

        device_lookup = {
            "Q2AB-0001": {
                "name": "Branch MX",
                "model": "MX68",
                "network_id": "N_1",
                "network_name": "Branch",
                "device_type": "MX",
            },
        }

        await collector.collect_uplink_loss_latency("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 2
        gauge_0, _, loss_value, _ = mock_parent._set_metric.call_args_list[0][0]
        gauge_1, _, latency_value, _ = mock_parent._set_metric.call_args_list[1][0]
        assert gauge_0 is collector._mx_uplink_loss_percent
        assert loss_value == 1.0  # falls back to the earlier non-null loss sample
        assert gauge_1 is collector._mx_uplink_latency_ms
        assert latency_value == 25.0  # latest non-null latency sample

    async def test_empty_response(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[]
        )

        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_all_null_timeseries_skips_emission(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that a row with no non-null samples emits nothing."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": None, "latencyMs": None},
                    ],
                },
            ]
        )

        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_network_filter_exclusion(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit uplink health metrics."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "serial": "Q-IN",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [{"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0}],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "serial": "Q-OUT",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [{"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0}],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        for call in mock_parent._set_metric.call_args_list:
            assert call[0][1]["network_id"] == "N_INCLUDED"
            assert call[0][1]["serial"] == "Q-IN"

    async def test_api_error_handled_gracefully(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_unknown_serial_falls_back_to_serial_as_name(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection when serial is not in the device lookup."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_999",
                    "serial": "Q2XX-UNKNOWN",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [{"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0}],
                },
            ]
        )

        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        _, labels, _, _ = mock_parent._set_metric.call_args_list[0][0]
        assert labels["name"] == "Q2XX-UNKNOWN"
        assert labels["serial"] == "Q2XX-UNKNOWN"
