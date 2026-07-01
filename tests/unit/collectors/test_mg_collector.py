"""Tests for MG (Cellular Gateway) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mg import MGCollector

if TYPE_CHECKING:
    pass


class TestMGCollector:
    """Test MG collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.cellularGateway = MagicMock()
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
        return parent

    @pytest.fixture
    def mg_collector(
        self,
        mock_parent: MagicMock,
    ) -> MGCollector:
        """Create MG collector instance."""
        return MGCollector(mock_parent)

    async def test_collect_does_not_set_common_metrics(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """Test that MG collector does not redundantly set common metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before collect() is called.
        MG's per-device collect() remains a no-op — uplink metrics are
        collected org-wide via collect_uplink_statuses().
        """
        device = {
            "serial": "Q123",
            "name": "Test MG",
            "model": "MG21",
            "network_id": "net1",
            "organization_id": "123",
        }

        await mg_collector.collect(device)
        mg_collector.parent._device_up.labels.assert_not_called()

    def test_mg_collector_initialization(
        self,
        mg_collector: MGCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MG collector initialization."""
        assert mg_collector.parent == mock_parent
        assert mg_collector.api == mock_parent.api
        assert mg_collector.settings == mock_parent.settings

    def test_mg_gauges_created_on_init(
        self,
        mg_collector: MGCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that all MG gauges are created on init."""
        mock_parent._create_gauge.assert_called()
        assert mg_collector._mg_uplink_status_info is not None
        assert mg_collector._mg_uplink_signal_rsrp is not None
        assert mg_collector._mg_uplink_signal_rsrq is not None
        assert mg_collector._mg_uplink_roaming is not None

    async def test_collect_uplink_statuses_basic(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test basic uplink status collection with a single gateway."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "ip": "10.0.0.1",
                            "provider": "Verizon",
                            "connectionType": "lte",
                            "signalType": "4G",
                            "apn": "vzwinternet",
                            "signalStat": {"rsrp": "-90", "rsrq": "-10"},
                            "roaming": {"status": "home"},
                        }
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2XX-1": {
                "name": "Gateway 1",
                "model": "MG21",
                "network_id": "N_1",
                "network_name": "Main Network",
                "device_type": "MG",
            }
        }

        await mg_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        # 1 info + 1 rsrp + 1 rsrq + 1 roaming = 4 _set_metric calls
        assert mock_parent._set_metric.call_count == 4

        calls = mock_parent._set_metric.call_args_list

        info_call = calls[0]
        info_metric, info_labels, info_value, *_ = info_call[0]
        assert info_metric is mg_collector._mg_uplink_status_info
        assert info_labels["serial"] == "Q2XX-1"
        assert info_labels["name"] == "Gateway 1"
        assert info_labels["network_name"] == "Main Network"
        assert info_labels["interface"] == "cellular"
        assert info_labels["status"] == "active"
        assert info_labels["provider"] == "Verizon"
        assert info_labels["connection_type"] == "lte"
        assert info_labels["signal_type"] == "4G"
        assert info_labels["roaming_status"] == "home"
        assert info_labels["apn"] == "vzwinternet"
        assert info_labels["ip"] == "10.0.0.1"
        assert info_value == 1

        rsrp_call = calls[1]
        rsrp_metric, rsrp_labels, rsrp_value, *_ = rsrp_call[0]
        assert rsrp_metric is mg_collector._mg_uplink_signal_rsrp
        assert rsrp_labels["interface"] == "cellular"
        assert rsrp_value == -90.0

        rsrq_call = calls[2]
        rsrq_metric, rsrq_labels, rsrq_value, *_ = rsrq_call[0]
        assert rsrq_metric is mg_collector._mg_uplink_signal_rsrq
        assert rsrq_value == -10.0

        roaming_call = calls[3]
        roaming_metric, roaming_labels, roaming_value, *_ = roaming_call[0]
        assert roaming_metric is mg_collector._mg_uplink_roaming
        assert roaming_value == 0.0  # status is "home", not "roaming"

    async def test_collect_uplink_statuses_roaming_true(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that roaming status of 'roaming' emits value 1.0."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "roaming": {"status": "roaming"},
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        roaming_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_roaming
        ]
        assert len(roaming_calls) == 1
        assert roaming_calls[0][0][2] == 1.0

    async def test_collect_uplink_statuses_no_roaming_object_skips_roaming_metric(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that no roaming object in uplink means no roaming metric is emitted."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        roaming_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_roaming
        ]
        assert len(roaming_calls) == 0

    async def test_collect_uplink_statuses_signal_string_parsing(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test rsrp/rsrq string->float parsing, including empty/non-numeric skipped."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "signalStat": {"rsrp": "", "rsrq": "not-a-number"},
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        rsrp_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_signal_rsrp
        ]
        rsrq_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_signal_rsrq
        ]
        assert len(rsrp_calls) == 0
        assert len(rsrq_calls) == 0

    async def test_collect_uplink_statuses_empty_response(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_unknown_serial(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection when serial is not in the device lookup."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_999",
                    "serial": "Q2XX-UNKNOWN",
                    "model": "MG21",
                    "uplinks": [
                        {"interface": "cellular", "status": "active"},
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_status_info
        ]
        assert len(info_calls) == 1
        _, labels, _, *_rest = info_calls[0][0]
        # Falls back to serial as name when not in device_lookup
        assert labels["name"] == "Q2XX-UNKNOWN"
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert labels["model"] == "MG21"

    async def test_collect_uplink_statuses_respects_network_filter(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit uplink metrics."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "serial": "Q-IN",
                    "model": "MG21",
                    "uplinks": [{"interface": "cellular", "status": "active"}],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "serial": "Q-OUT",
                    "model": "MG21",
                    "uplinks": [{"interface": "cellular", "status": "active"}],
                },
            ]
        )
        # Wire an inventory that allows only N_INCLUDED.
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_status_info
        ]
        assert len(info_calls) == 1
        _, labels, _, *_rest = info_calls[0][0]
        assert labels["network_id"] == "N_INCLUDED"
        assert labels["serial"] == "Q-IN"

    async def test_collect_uplink_statuses_api_error(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_clears_stale_labels(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that stale label series are cleared on each collection."""
        info_gauge = mg_collector._mg_uplink_status_info
        roaming_gauge = mg_collector._mg_uplink_roaming

        # Simulate stale entries from a previous collection cycle.
        info_gauge.labels(
            org_id="org1",
            org_name="Test Org",
            network_id="N_1",
            network_name="Main Network",
            serial="Q2XX-1",
            name="Gateway 1",
            model="MG21",
            device_type="MG",
            interface="cellular",
            status="active",
            provider="Verizon",
            connection_type="lte",
            signal_type="4G",
            roaming_status="home",
            apn="vzwinternet",
            ip="10.0.0.1",
        ).set(1)
        roaming_gauge.labels(
            org_id="org1",
            org_name="Test Org",
            network_id="N_1",
            network_name="Main Network",
            serial="Q2XX-1",
            name="Gateway 1",
            model="MG21",
            device_type="MG",
            interface="cellular",
        ).set(0)

        assert len(info_gauge._metrics) == 1
        assert len(roaming_gauge._metrics) == 1

        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        # Empty response returns early, before clearing — so simulate a real cycle
        # with data to confirm the clear-then-repopulate behavior separately.
        assert len(info_gauge._metrics) == 1
        assert len(roaming_gauge._metrics) == 1

        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {"interface": "cellular", "status": "failed"},
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        # The stale entries should have been cleared before parent._set_metric
        # (mocked, so it doesn't repopulate the real Gauge) was invoked.
        assert len(info_gauge._metrics) == 0
        assert len(roaming_gauge._metrics) == 0
