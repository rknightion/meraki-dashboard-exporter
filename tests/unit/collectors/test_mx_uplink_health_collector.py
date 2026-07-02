"""Tests for MX uplink health (loss/latency) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx_uplink_health import (
    MXUplinkHealthCollector,
)
from meraki_dashboard_exporter.core.domain_models import DeviceUplinkLossLatency

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
        assert collector._mx_uplink_latency_seconds is not None

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
        assert labels_0["network_id"] == "N_111"
        assert labels_0["interface"] == "wan1"
        assert "name" not in labels_0
        assert "network_name" not in labels_0
        assert "org_name" not in labels_0
        assert value_0 == 0.5

        gauge_1, labels_1, value_1, _ = mock_parent._set_metric.call_args_list[1][0]
        assert gauge_1 is collector._mx_uplink_latency_seconds
        assert labels_1["interface"] == "wan1"
        assert value_1 == pytest.approx(0.0125)

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

    async def test_multiple_ip_rows_same_uplink_aggregates_to_max(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Multiple destination-ip rows for one uplink aggregate to the worst case.

        The endpoint returns one row per (device, uplink, destination-ip). We
        label only by interface, so the rows must be aggregated to a single
        series per uplink taking the MAX loss and MAX latency across
        destinations (worst-case), not last-write-wins.
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

        # Two destination rows collapse to ONE uplink series -> 1 loss + 1 latency.
        assert mock_parent._set_metric.call_count == 2
        loss_call = mock_parent._set_metric.call_args_list[0][0]
        latency_call = mock_parent._set_metric.call_args_list[1][0]
        assert loss_call[0] is collector._mx_uplink_loss_percent
        assert loss_call[1]["interface"] == "wan1"
        assert loss_call[2] == 3.0  # max(1.0, 3.0)
        assert latency_call[0] is collector._mx_uplink_latency_seconds
        assert latency_call[2] == pytest.approx(0.030)  # max(10ms, 30ms)

    async def test_max_is_not_last_write_wins(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The worst (max) destination must win even when it is NOT the last row.

        Guards against a regression to last-write-wins: here the first row is
        the worst; a last-write-wins implementation would emit the second
        (better) row's values.
        """
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 5.0, "latencyMs": 50.0},
                    ],
                },
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "1.1.1.1",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0},
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
        loss_call = mock_parent._set_metric.call_args_list[0][0]
        latency_call = mock_parent._set_metric.call_args_list[1][0]
        assert loss_call[2] == 5.0  # max, from the FIRST row (not last-write-wins 1.0)
        assert latency_call[2] == pytest.approx(0.050)

    async def test_max_loss_and_latency_independent_across_rows(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Max loss and max latency are taken independently across destination rows.

        The worst loss and worst latency can come from different destination
        rows; each metric must take its own max.
        """
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "8.8.8.8",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 4.0, "latencyMs": 10.0},
                    ],
                },
                {
                    "networkId": "N_1",
                    "serial": "Q2AB-0001",
                    "uplink": "wan1",
                    "ip": "1.1.1.1",
                    "timeSeries": [
                        {"ts": "t1", "lossPercent": 1.0, "latencyMs": 40.0},
                    ],
                },
            ]
        )

        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        loss_call = mock_parent._set_metric.call_args_list[0][0]
        latency_call = mock_parent._set_metric.call_args_list[1][0]
        assert loss_call[2] == 4.0  # worst loss, from row 1
        assert latency_call[2] == pytest.approx(0.040)  # worst latency, from row 2

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
        assert latency_value == pytest.approx(0.020)

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
        assert gauge_1 is collector._mx_uplink_latency_seconds
        assert latency_value == pytest.approx(0.025)  # latest non-null latency sample

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

    async def test_exhausted_retry_error_shape_handled_gracefully(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be handled, not raised.

        getOrganizationDevicesUplinksLossAndLatency is validated via
        validate_response_format (expected_type=list); a {"errors": [...]}
        response must raise internally and be absorbed by @with_error_handling,
        not propagate or emit a metric.
        """
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        # Should not raise - validate_response_format raises internally, and
        # @with_error_handling absorbs it.
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
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert "name" not in labels

    # ------------------------------------------------------------------
    # Pydantic domain-model validation (F-029)
    # ------------------------------------------------------------------

    async def test_collect_validates_rows_via_domain_model(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Each raw row must be validated via DeviceUplinkLossLatency.model_validate."""
        row = {
            "networkId": "N_111",
            "serial": "Q2AB-1234-5678",
            "uplink": "wan1",
            "ip": "8.8.8.8",
            "timeSeries": [{"ts": "t1", "lossPercent": 1.0, "latencyMs": 10.0}],
        }
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[row]
        )

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx_uplink_health."
            "DeviceUplinkLossLatency.model_validate",
            wraps=DeviceUplinkLossLatency.model_validate,
        ) as spy:
            await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        spy.assert_called_once_with(row)

    async def test_collect_tolerates_missing_and_extra_fields(
        self,
        collector: MXUplinkHealthCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Missing optional fields and unexpected extra fields must not raise."""
        mock_api.organizations.getOrganizationDevicesUplinksLossAndLatency = MagicMock(
            return_value=[
                {
                    "networkId": "N_111",
                    "serial": "Q2AB-1234-5678",
                    "uplink": "wan1",
                    "someBrandNewField": {"nested": True},
                    "timeSeries": [
                        {
                            "ts": "t1",
                            "lossPercent": 1.0,
                            "latencyMs": 10.0,
                            "aFutureApiField": "unexpected",
                        }
                    ],
                }
            ]
        )

        await collector.collect_uplink_loss_latency("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        _, labels, loss_value, _ = mock_parent._set_metric.call_args_list[0][0]
        assert labels["interface"] == "wan1"
        assert loss_value == 1.0
