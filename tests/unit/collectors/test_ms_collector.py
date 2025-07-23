"""Tests for MS (Switch) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.ms import MSCollector

if TYPE_CHECKING:
    pass


class TestMSCollector:
    """Test MS collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.switch = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()

        # Mock the _create_gauge method to return actual Gauge objects
        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    @pytest.fixture
    def ms_collector(
        self,
        mock_parent: MagicMock,
    ) -> MSCollector:
        """Create MS collector instance."""
        collector = MSCollector(mock_parent)
        # Initialize metrics manually since we're using a mock parent
        collector._initialize_metrics()
        return collector

    async def test_collect_basic_api_call(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that collection makes the correct API call."""
        # Mock device data
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock port statuses response
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "name": "Uplink Port",
                    "status": "Connected",
                    "speed": "1 Gbps",
                    "duplex": "full",
                    "clientCount": 5,
                    "trafficInKbps": {
                        "recv": 1000,
                        "sent": 500,
                    },
                    "usageInKb": {
                        "recv": 3600000,
                        "sent": 1800000,
                        "total": 5400000,
                    },
                }
            ]
        )

        # Run collection
        await ms_collector.collect(device)

        # Verify API call was made with timespan
        mock_api.switch.getDeviceSwitchPortsStatuses.assert_called_once_with(
            "Q123-456-789", timespan=3600
        )

    async def test_handles_missing_fields_gracefully(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test handling of missing fields in API response."""
        # Mock device data
        device = {
            "serial": "Q123",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock response with various missing fields
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    # Missing: name, trafficInKbps, poe, powerUsageInWh
                    "status": "Connected",
                },
                {
                    "portId": "2",
                    "name": "Port 2",
                    "status": "Connected",
                    # trafficInKbps present but missing fields
                    "trafficInKbps": {},
                },
                {
                    "portId": "3",
                    "status": "Connected",
                    # poe present but missing isAllocated
                    "poe": {},
                },
            ]
        )

        # Should not raise errors
        await ms_collector.collect(device)

    async def test_error_handling_continues_collection(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that errors are handled gracefully."""
        # Mock device
        device = {
            "serial": "Q111",
            "name": "Switch 1",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Make API call fail
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(side_effect=Exception("API Error"))

        # Should not raise due to error handling decorator
        await ms_collector.collect(device)

    async def test_empty_port_list(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test handling of switches with no ports (empty response)."""
        # Mock device data
        device = {
            "serial": "Q123",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock empty port list
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(return_value=[])

        # Should not raise errors
        await ms_collector.collect(device)

    def test_ms_collector_initialization(
        self,
        ms_collector: MSCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MS collector initialization."""
        # Verify collector is properly initialized with parent
        assert ms_collector.parent == mock_parent
        assert ms_collector.api == mock_parent.api
        assert ms_collector.settings == mock_parent.settings

    async def test_collect_stp_priorities(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test STP priority collection."""
        # Mock organization networks response
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "net1",
                    "name": "Network 1",
                    "productTypes": ["switch", "wireless"],
                },
                {
                    "id": "net2",
                    "name": "Network 2",
                    "productTypes": ["switch"],
                },
                {
                    "id": "net3",
                    "name": "Network 3",
                    "productTypes": ["wireless"],  # No switch, should be skipped
                },
            ]
        )

        # Mock device lookup
        device_lookup = {
            "Q2MW-42Z2-JE5T": {"name": "Switch 1", "model": "MS250"},
            "Q2BX-Q43Y-RR5C": {"name": "Switch 2", "model": "MS250"},
            "Q2HP-F6VX-M24J": {"name": "Switch 3", "model": "MS350"},
            "Q2HP-K4VW-87YT": {"name": "Switch 4", "model": "MS350"},
        }

        # Mock STP responses for each network
        stp_responses = {
            "net1": {
                "rstpEnabled": True,
                "stpBridgePriority": [
                    {"switches": ["Q2MW-42Z2-JE5T"], "stpPriority": 8192},
                    {"switches": ["Q2BX-Q43Y-RR5C"], "stpPriority": 32768},
                ],
            },
            "net2": {
                "rstpEnabled": True,
                "stpBridgePriority": [
                    {"switches": ["Q2HP-F6VX-M24J", "Q2HP-K4VW-87YT"], "stpPriority": 32768}
                ],
            },
        }

        def get_network_stp(network_id):
            return stp_responses.get(network_id, {})

        mock_api.switch.getNetworkSwitchStp = MagicMock(side_effect=get_network_stp)

        # Run collection
        await ms_collector.collect_stp_priorities("org123", device_lookup)

        # Verify API calls
        mock_api.organizations.getOrganizationNetworks.assert_called_once_with(
            "org123", total_pages="all"
        )
        assert mock_api.switch.getNetworkSwitchStp.call_count == 2  # Only for net1 and net2

        # Verify metrics were set correctly
        # Note: In real tests, you'd want to verify the actual metric values
        # This would require accessing the Prometheus metrics registry

    async def test_collect_stp_handles_api_errors(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test STP collection handles API errors gracefully."""
        # Mock organization networks response
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "net1",
                    "name": "Network 1",
                    "productTypes": ["switch"],
                }
            ]
        )

        # Make STP API call fail
        mock_api.switch.getNetworkSwitchStp = MagicMock(side_effect=Exception("API Error"))

        # Should not raise due to error handling
        await ms_collector.collect_stp_priorities("org123", {})

    async def test_new_metrics_collection(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test collection of new metrics: usage bytes and client count."""
        # Mock device data
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock port statuses response with full data
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "name": "Port 1",
                    "status": "Connected",
                    "speed": "1 Gbps",
                    "duplex": "full",
                    "clientCount": 10,
                    "usageInKb": {
                        "recv": 1000000,  # 1GB
                        "sent": 500000,  # 500MB
                        "total": 1500000,  # 1.5GB
                    },
                    "trafficInKbps": {
                        "recv": 125.5,
                        "sent": 62.3,
                    },
                },
                {
                    "portId": "2",
                    "name": "Port 2",
                    "status": "Disconnected",
                    "speed": "",
                    "duplex": "",
                    "clientCount": 0,
                    "usageInKb": {
                        "recv": 0,
                        "sent": 0,
                        "total": 0,
                    },
                },
            ]
        )

        # Run collection
        await ms_collector.collect(device)

        # Verify API was called with timespan
        mock_api.switch.getDeviceSwitchPortsStatuses.assert_called_once_with(
            "Q123-456-789", timespan=3600
        )

        # In a real test with actual metrics registry, you would verify:
        # - Port status metric has speed and duplex labels
        # - Usage bytes metric is set with correct values
        # - Client count metric is set correctly
        # - All metrics have network_id and network_name labels

    async def test_packet_statistics_collection(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test collection of packet statistics metrics."""
        # Mock device data
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock packet statistics response
        mock_api.switch.getDeviceSwitchPortsStatusesPackets = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "packets": [
                        {
                            "desc": "Total",
                            "total": 1000000,
                            "sent": 600000,
                            "recv": 400000,
                            "ratePerSec": {
                                "total": 3333,
                                "sent": 2000,
                                "recv": 1333,
                            },
                        },
                        {
                            "desc": "Broadcast",
                            "total": 50000,
                            "sent": 30000,
                            "recv": 20000,
                            "ratePerSec": {
                                "total": 166,
                                "sent": 100,
                                "recv": 66,
                            },
                        },
                        {
                            "desc": "Multicast",
                            "total": 10000,
                            "sent": 6000,
                            "recv": 4000,
                            "ratePerSec": {
                                "total": 33,
                                "sent": 20,
                                "recv": 13,
                            },
                        },
                        {
                            "desc": "CRC align errors",
                            "total": 0,
                            "sent": 0,
                            "recv": 0,
                            "ratePerSec": {
                                "total": 0,
                                "sent": 0,
                                "recv": 0,
                            },
                        },
                        {
                            "desc": "Fragments",
                            "total": 0,
                            "sent": 0,
                            "recv": 0,
                            "ratePerSec": {
                                "total": 0,
                                "sent": 0,
                                "recv": 0,
                            },
                        },
                        {
                            "desc": "Collisions",
                            "total": 0,
                            "sent": 0,
                            "recv": 0,
                            "ratePerSec": {
                                "total": 0,
                                "sent": 0,
                                "recv": 0,
                            },
                        },
                        {
                            "desc": "Topology changes",
                            "total": 0,
                            "sent": 0,
                            "recv": 0,
                            "ratePerSec": {
                                "total": 0,
                                "sent": 0,
                                "recv": 0,
                            },
                        },
                    ],
                },
                {
                    "portId": "2",
                    "packets": [
                        {
                            "desc": "Total",
                            "total": 0,
                            "sent": 0,
                            "recv": 0,
                            "ratePerSec": {
                                "total": 0,
                                "sent": 0,
                                "recv": 0,
                            },
                        },
                        # Other packet types with 0 values
                    ],
                },
            ]
        )

        # Mock getDeviceSwitchPortsStatuses to succeed
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(return_value=[])

        # Run collection
        await ms_collector.collect(device)

        # Verify packet API was called with correct timespan
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.assert_called_once_with(
            "Q123-456-789", timespan=300
        )

    async def test_packet_statistics_handles_missing_data(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test packet statistics handles missing or malformed data."""
        # Mock device data
        device = {
            "serial": "Q123",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock response with missing fields
        mock_api.switch.getDeviceSwitchPortsStatusesPackets = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "packets": [
                        {
                            "desc": "Total",
                            # Missing some fields
                            "total": 1000,
                            # Missing sent, recv, ratePerSec
                        },
                        {
                            "desc": "Unknown Type",  # Unknown packet type
                            "total": 100,
                            "sent": 50,
                            "recv": 50,
                        },
                    ],
                },
                {
                    # Missing packets array
                    "portId": "2",
                },
            ]
        )

        # Mock getDeviceSwitchPortsStatuses to succeed
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(return_value=[])

        # Should not raise errors
        await ms_collector.collect(device)

    async def test_packet_statistics_api_error(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test packet statistics handles API errors gracefully."""
        # Mock device
        device = {
            "serial": "Q111",
            "name": "Switch 1",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
        }

        # Mock getDeviceSwitchPortsStatuses to succeed
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(return_value=[])

        # Make packet API call fail
        mock_api.switch.getDeviceSwitchPortsStatusesPackets = MagicMock(
            side_effect=Exception("API Error")
        )

        # Should not raise due to error handling decorator
        await ms_collector.collect(device)

        # Verify the packet API was attempted
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.assert_called_once_with(
            "Q111", timespan=300
        )
