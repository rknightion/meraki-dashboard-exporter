"""Tests for MR (Wireless Access Point) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr import MRCollector

if TYPE_CHECKING:
    pass


class TestMRCollector:
    """Test MR collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.wireless = MagicMock()
        api.organizations = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()

        # Create actual gauges for metrics
        gauges = {}

        def create_gauge(name, description, labelnames):
            gauge = Gauge(name.value, description, labelnames)
            gauges[name.value] = gauge
            return gauge

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._gauges = gauges  # Store for test access
        return parent

    @pytest.fixture
    def mr_collector(self, mock_parent: MagicMock) -> MRCollector:
        """Create MR collector instance."""
        return MRCollector(mock_parent)

    async def test_collect_basic_device_metrics(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test collection of basic MR metrics (client count and connection stats)."""
        # Mock device data
        device = {
            "serial": "Q123-456-789",
            "name": "Test MR",
            "model": "MR46",
            "networkId": "net1",
        }

        # Mock wireless status
        mock_api.wireless.getDeviceWirelessStatus = MagicMock(return_value={"clientCount": 42})

        # Mock connection stats
        mock_api.wireless.getDeviceWirelessConnectionStats = MagicMock(
            return_value={
                "assoc": 100,
                "auth": 98,
                "dhcp": 95,
                "dns": 94,
                "success": 90,
            }
        )

        # Run collection for device
        await mr_collector.collect(device)

        # Verify API calls were made
        mock_api.wireless.getDeviceWirelessStatus.assert_called_once_with("Q123-456-789")
        mock_api.wireless.getDeviceWirelessConnectionStats.assert_called_once()

        # Verify metrics were set
        assert mr_collector._ap_clients is not None
        assert mr_collector._ap_connection_stats is not None

    async def test_collect_wireless_clients_dict_response(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test wireless client collection with dict response format."""
        org_id = "123"
        device_lookup = {
            "Q123": {
                "serial": "Q123",
                "name": "AP1",
                "networkId": "net1",
                "network_name": "Network 1",
            }
        }

        # Mock dict response with "items" key
        mock_api.wireless.getOrganizationWirelessClientsOverviewByDevice = MagicMock(
            return_value={
                "items": [
                    {
                        "network": {"id": "net1", "name": "Network 1"},
                        "serial": "Q123",
                        "name": "AP1",
                        "counts": {"byStatus": {"online": 25}},
                    }
                ]
            }
        )

        # Run collection
        await mr_collector.collect_wireless_clients(org_id, "Test Org", device_lookup)

        # Verify API call
        mock_api.wireless.getOrganizationWirelessClientsOverviewByDevice.assert_called_once_with(
            org_id, total_pages="all"
        )

    async def test_collect_wireless_clients_list_response(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test wireless client collection with list response format."""
        org_id = "123"
        device_lookup = {
            "Q123": {
                "serial": "Q123",
                "name": "AP1",
                "networkId": "net1",
                "network_name": "Network 1",
            }
        }

        # Mock list response
        mock_api.wireless.getOrganizationWirelessClientsOverviewByDevice = MagicMock(
            return_value=[
                {
                    "network": {"id": "net1", "name": "Network 1"},
                    "serial": "Q123",
                    "name": "AP1",
                    "counts": {"byStatus": {"online": 30}},
                }
            ]
        )

        # Run collection
        await mr_collector.collect_wireless_clients(org_id, "Test Org", device_lookup)

        # Verify metrics were processed
        assert mr_collector._ap_clients is not None

    def test_packet_metric_value_retention(self, mr_collector: MRCollector) -> None:
        """Test that packet metrics have a cache for retaining values."""
        # Simply verify the collector has the packet value cache initialized
        assert hasattr(mr_collector, "_packet_value_cache")
        assert isinstance(mr_collector._packet_value_cache, dict)

    async def test_collect_handles_missing_data(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test handling of missing or None values in API responses."""
        # Mock device
        device = {
            "serial": "Q123",
            "name": "Test AP",
            "model": "MR46",
            "networkId": "net1",
        }

        # Mock wireless status with missing clientCount
        mock_api.wireless.getDeviceWirelessStatus = MagicMock(
            return_value={}  # No clientCount field
        )

        # Mock connection stats with None values
        mock_api.wireless.getDeviceWirelessConnectionStats = MagicMock(
            return_value={
                "assoc": None,
                "auth": 98,
                "dhcp": None,
                "dns": 94,
                "success": 90,
            }
        )

        # Should not raise errors
        await mr_collector.collect(device)

    async def test_collect_ssid_usage(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test SSID usage metrics collection."""
        org_id = "123"
        org_name = "Test Org"

        mock_api.organizations.getOrganizationSummaryTopSsidsByUsage = MagicMock(
            return_value=[
                {
                    "name": "Guest WiFi",
                    "usageDownstreamMb": 1024.5,
                    "usageUpstreamMb": 512.25,
                    "usageTotalMb": 1536.75,
                    "percentUsage": 45.5,
                    "clientCount": 150,
                },
                {
                    "name": "Corporate WiFi",
                    "usageDownstreamMb": 2048.0,
                    "usageUpstreamMb": 1024.0,
                    "usageTotalMb": 3072.0,
                    "percentUsage": 54.5,
                    "clientCount": 200,
                },
            ]
        )

        # Run collection
        await mr_collector.collect_ssid_usage(org_id, org_name)

        # Verify API call
        mock_api.organizations.getOrganizationSummaryTopSsidsByUsage.assert_called_once_with(org_id)

    async def test_collect_ethernet_status_power_modes(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test ethernet status collection with different power modes."""
        org_id = "123"
        device_lookup = {
            "Q123": {"serial": "Q123", "name": "AP1"},
            "Q456": {"serial": "Q456", "name": "AP2"},
        }

        mock_api.wireless.getOrganizationWirelessDevicesEthernetStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q123",
                    "name": "AP1",
                    "network": {"id": "net1", "name": "Network 1"},
                    "powerMode": "802.3at",  # PoE mode
                    "isConnected": True,
                },
                {
                    "serial": "Q456",
                    "name": "AP2",
                    "network": {"id": "net1", "name": "Network 1"},
                    "powerMode": "AC",  # AC power
                    "isConnected": True,
                },
            ]
        )

        # Run collection
        await mr_collector.collect_ethernet_status(org_id, "Test Org", device_lookup)

        # Verify API was called
        mock_api.wireless.getOrganizationWirelessDevicesEthernetStatuses.assert_called_once_with(
            org_id
        )
