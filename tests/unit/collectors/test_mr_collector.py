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

    async def test_collect_is_noop(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that per-device collect() is a no-op.

        Client counts and connection stats are now collected at org/network level
        for better API efficiency:
        - Client counts: collect_wireless_clients() uses org-wide endpoint
        - Connection stats: collect_connection_stats() uses network-level endpoint
        """
        # Mock device data
        device = {
            "serial": "Q123-456-789",
            "name": "Test MR",
            "model": "MR46",
            "networkId": "net1",
        }

        # Run collection for device (should be a no-op)
        await mr_collector.collect(device)

        # Verify NO per-device API calls were made (they're now org/network level)
        mock_api.wireless.getDeviceWirelessStatus.assert_not_called()
        mock_api.wireless.getDeviceWirelessConnectionStats.assert_not_called()

        # Metrics are still initialized (but set at org/network level)
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

    async def test_collect_connection_stats_network_level(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test network-level connection stats collection."""
        org_id = "123"
        org_name = "Test Org"
        networks = [
            {"id": "net1", "name": "Network 1", "productTypes": ["wireless"]},
            {"id": "net2", "name": "Network 2", "productTypes": ["wireless"]},
        ]
        device_lookup = {
            "Q123": {"serial": "Q123", "name": "AP1", "model": "MR46"},
            "Q456": {"serial": "Q456", "name": "AP2", "model": "MR46"},
        }

        # Mock network-level connection stats response
        mock_api.wireless.getNetworkWirelessDevicesConnectionStats = MagicMock(
            return_value=[
                {
                    "serial": "Q123",
                    "connectionStats": {
                        "assoc": 100,
                        "auth": 98,
                        "dhcp": 95,
                        "dns": 94,
                        "success": 90,
                    },
                },
                {
                    "serial": "Q456",
                    "connectionStats": {
                        "assoc": 50,
                        "auth": 48,
                        "dhcp": 45,
                        "dns": 44,
                        "success": 40,
                    },
                },
            ]
        )

        # Run collection
        await mr_collector.collect_connection_stats(org_id, org_name, networks, device_lookup)

        # Verify network-level API calls (one per wireless network)
        assert mock_api.wireless.getNetworkWirelessDevicesConnectionStats.call_count == 2

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
