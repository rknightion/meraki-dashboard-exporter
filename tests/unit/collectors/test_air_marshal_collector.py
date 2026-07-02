"""Tests for the AirMarshalCollector (rogue AP / SSID-spoofing detection)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.network_health_collectors.air_marshal import (
    AirMarshalCollector,
)

if TYPE_CHECKING:
    pass


class TestAirMarshalCollector:
    """Test AirMarshalCollector functionality."""

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
    def collector(self, mock_parent: MagicMock) -> AirMarshalCollector:
        """Create the collector instance."""
        return AirMarshalCollector(mock_parent)

    @pytest.fixture
    def network(self) -> dict:
        """Standard network dict, already NetworkFilter-stamped by the coordinator."""
        return {
            "id": "N_1",
            "name": "Test Network",
            "orgId": "org_1",
            "orgName": "Test Org",
        }

    def test_initialization(self, collector: AirMarshalCollector, mock_parent: MagicMock) -> None:
        """Test collector initialization sets up parent/api/settings."""
        assert collector.parent == mock_parent
        assert collector.api == mock_parent.api
        assert collector.settings == mock_parent.settings

    def test_gauges_created(self, collector: AirMarshalCollector, mock_parent: MagicMock) -> None:
        """Test that all four Air Marshal gauges are created on init."""
        assert mock_parent._create_gauge.call_count == 4
        assert collector._air_marshal_ssids_total is not None
        assert collector._air_marshal_bssids_total is not None
        assert collector._air_marshal_contained_bssids_total is not None
        assert collector._air_marshal_wired_detected_total is not None

    async def test_multi_ssid_counts(
        self,
        collector: AirMarshalCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test counts across multiple SSID entries with mixed contained/wired state."""
        mock_api.wireless.getNetworkWirelessAirMarshal = MagicMock(
            return_value=[
                {
                    "ssid": "Evil Twin",
                    "bssids": [
                        {"bssid": "aa:aa:aa:aa:aa:01", "contained": True, "detectedBy": []},
                        {"bssid": "aa:aa:aa:aa:aa:02", "contained": False, "detectedBy": []},
                    ],
                    "channels": [1, 6],
                    "wiredMacs": ["aa:aa:aa:aa:aa:01"],
                    "wiredVlans": [10],
                },
                {
                    "ssid": "Free WiFi",
                    "bssids": [
                        {"bssid": "bb:bb:bb:bb:bb:01", "contained": False, "detectedBy": []},
                    ],
                    "channels": [11],
                    "wiredMacs": [],
                    "wiredVlans": [],
                },
                {
                    "ssid": "Spoofed Corp",
                    "bssids": [
                        {"bssid": "cc:cc:cc:cc:cc:01", "contained": True, "detectedBy": []},
                        {"bssid": "cc:cc:cc:cc:cc:02", "contained": True, "detectedBy": []},
                        {"bssid": "cc:cc:cc:cc:cc:03", "contained": False, "detectedBy": []},
                    ],
                    "channels": [36],
                    "wiredMacs": [],
                    "wiredVlans": [],
                },
            ]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 4
        emitted = {call[0][0]: call[0][2] for call in mock_parent._set_metric.call_args_list}
        assert emitted[collector._air_marshal_ssids_total] == 3.0
        assert emitted[collector._air_marshal_bssids_total] == 6.0
        assert emitted[collector._air_marshal_contained_bssids_total] == 3.0
        assert emitted[collector._air_marshal_wired_detected_total] == 1.0

        for call in mock_parent._set_metric.call_args_list:
            _gauge, labels, _value, _metric_name = call[0]
            assert labels["network_id"] == "N_1"
            assert labels["org_id"] == "org_1"
            assert "ssid" not in labels
            assert "bssid" not in labels

    async def test_empty_response_emits_zero_counts(
        self,
        collector: AirMarshalCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that a clean network (no rogue APs) still emits explicit zero counts."""
        mock_api.wireless.getNetworkWirelessAirMarshal = MagicMock(return_value=[])

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 4
        for call in mock_parent._set_metric.call_args_list:
            _gauge, _labels, value, _metric_name = call[0]
            assert value == 0.0

    async def test_metric_names(
        self,
        collector: AirMarshalCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that the correct metric name string is passed for each gauge."""
        mock_api.wireless.getNetworkWirelessAirMarshal = MagicMock(return_value=[])

        await collector.collect(network)

        metric_names = {call[0][3] for call in mock_parent._set_metric.call_args_list}
        assert metric_names == {
            "meraki_mr_air_marshal_ssids_count",
            "meraki_mr_air_marshal_bssids_count",
            "meraki_mr_air_marshal_contained_bssids_count",
            "meraki_mr_air_marshal_wired_detected_count",
        }

    async def test_api_error_handled_gracefully(
        self,
        collector: AirMarshalCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.wireless.getNetworkWirelessAirMarshal = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await collector.collect(network)

        mock_parent._set_metric.assert_not_called()

    async def test_missing_bssids_and_wired_macs_default_gracefully(
        self,
        collector: AirMarshalCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        network: dict,
    ) -> None:
        """Test that entries missing bssids/wiredMacs keys don't raise."""
        mock_api.wireless.getNetworkWirelessAirMarshal = MagicMock(
            return_value=[{"ssid": "No BSSIDs Field"}]
        )

        await collector.collect(network)

        assert mock_parent._set_metric.call_count == 4
        emitted = {call[0][0]: call[0][2] for call in mock_parent._set_metric.call_args_list}
        assert emitted[collector._air_marshal_ssids_total] == 1.0
        assert emitted[collector._air_marshal_bssids_total] == 0.0
        assert emitted[collector._air_marshal_contained_bssids_total] == 0.0
        assert emitted[collector._air_marshal_wired_detected_total] == 0.0
