"""Tests for MX (Security Appliance) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx import MXCollector

if TYPE_CHECKING:
    pass


class TestMXCollector:
    """Test MX collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.appliance = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    @pytest.fixture
    def mx_collector(
        self,
        mock_parent: MagicMock,
    ) -> MXCollector:
        """Create MX collector instance."""
        return MXCollector(mock_parent)

    async def test_collect_calls_common_metrics(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test that MX collector calls common metrics collection."""
        device = {
            "serial": "Q123",
            "name": "Test MX",
            "model": "MX100",
            "network_id": "net1",
            "organization_id": "123",
            "status_info": {
                "status": "online",
            },
        }

        mx_collector.collect_common_metrics = MagicMock()
        await mx_collector.collect(device)
        mx_collector.collect_common_metrics.assert_called_once_with(device)

    def test_mx_collector_initialization(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MX collector initialization."""
        assert mx_collector.parent == mock_parent
        assert mx_collector.api == mock_parent.api
        assert mx_collector.settings == mock_parent.settings

    def test_mx_uplink_info_metric_created(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that the MX uplink info gauge metric is created on init."""
        mock_parent._create_gauge.assert_called_once()
        assert mx_collector._mx_uplink_info is not None

    async def test_collect_uplink_statuses_basic(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test basic uplink status collection with a single appliance."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-1234-5678",
                    "networkId": "N_111",
                    "model": "MX68",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                        {"interface": "wan2", "status": "not connected"},
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

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 2

        # Verify the first call (wan1 active)
        _, labels_0, value_0 = mock_parent._set_metric.call_args_list[0][0]
        assert labels_0["serial"] == "Q2AB-1234-5678"
        assert labels_0["name"] == "Office MX"
        assert labels_0["interface"] == "wan1"
        assert labels_0["status"] == "active"
        assert labels_0["network_name"] == "Office Network"
        assert value_0 == 1

        # Verify the second call (wan2 not connected)
        _, labels_1, value_1 = mock_parent._set_metric.call_args_list[1][0]
        assert labels_1["interface"] == "wan2"
        assert labels_1["status"] == "not connected"
        assert value_1 == 1

    async def test_collect_uplink_statuses_empty_response(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(return_value=[])

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_unknown_serial(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection when serial is not in the device lookup."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-UNKNOWN",
                    "networkId": "N_999",
                    "model": "MX100",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                    ],
                }
            ]
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 1
        _, labels, _ = mock_parent._set_metric.call_args_list[0][0]
        # Falls back to serial as name when not in device_lookup
        assert labels["name"] == "Q2XX-UNKNOWN"
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert labels["model"] == "MX100"

    async def test_collect_uplink_statuses_multiple_appliances(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection across multiple MX appliances."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "networkId": "N_1",
                    "model": "MX68",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                    ],
                },
                {
                    "serial": "Q2AB-0002",
                    "networkId": "N_2",
                    "model": "MX250",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                        {"interface": "wan2", "status": "ready"},
                        {"interface": "cellular", "status": "not connected"},
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
            "Q2AB-0002": {
                "name": "HQ MX",
                "model": "MX250",
                "network_id": "N_2",
                "network_name": "HQ",
                "device_type": "MX",
            },
        }

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        # 1 uplink from first appliance + 3 from second = 4 total
        assert mock_parent._set_metric.call_count == 4

    async def test_collect_uplink_statuses_no_uplinks(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test appliance with no uplinks in response."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "networkId": "N_1",
                    "model": "MX68",
                    "uplinks": [],
                }
            ]
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_device_type_from_model(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that device_type is derived from model via create_device_labels."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-Z3",
                    "networkId": "N_1",
                    "model": "Z3",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2AB-Z3": {
                "name": "Teleworker Gateway",
                "model": "Z3",
                "network_id": "N_1",
                "network_name": "Remote",
                "device_type": "Z3",
            },
        }

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        _, labels, _ = mock_parent._set_metric.call_args_list[0][0]
        # create_device_labels derives device_type from model[:2]
        assert labels["device_type"] == "Z3"

    async def test_collect_uplink_statuses_clears_stale_labels(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that stale status label series are cleared on each collection.

        When status changes (e.g. active -> failed), the old label series
        must not persist alongside the new one.
        """
        gauge = mx_collector._mx_uplink_info

        # Simulate a stale label entry from a previous collection cycle
        gauge.labels(
            org_id="org1",
            org_name="Test Org",
            network_id="N_111",
            network_name="Office Network",
            serial="Q2AB-1234-5678",
            name="Office MX",
            model="MX68",
            device_type="MX",
            interface="wan1",
            status="active",
        ).set(1)

        # Verify the stale entry exists
        assert len(gauge._metrics) == 1

        # Now collect with the uplink having changed to "failed"
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-1234-5678",
                    "networkId": "N_111",
                    "model": "MX68",
                    "uplinks": [
                        {"interface": "wan1", "status": "failed"},
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

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        # The _metrics dict should have been cleared before re-setting,
        # so the old "active" entry should not persist.
        # parent._set_metric is mocked so no new entries are added to the Gauge,
        # but the clear should have removed the stale entry.
        assert len(gauge._metrics) == 0

    async def test_collect_uplink_statuses_api_error(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()
