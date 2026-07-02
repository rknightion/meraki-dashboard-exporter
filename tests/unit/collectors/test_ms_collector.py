"""Tests for MS (Switch) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import REGISTRY, Gauge

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
        parent.settings.api.ms_packet_stats_interval = 0
        parent.settings.api.ms_port_usage_interval = 0
        parent.settings.api.concurrency_limit = 5
        parent.settings.update_intervals.slow = 900
        parent.rate_limiter = None

        # Mock the _create_gauge method to return actual Gauge objects
        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        # Mock _set_metric to behave like the real MetricCollector helper (minus
        # expiration tracking, which is exercised elsewhere) so gauge values set
        # via parent._set_metric are actually observable in the registry.
        def set_metric(metric, labels, value, metric_name=None):
            metric.labels(**labels).set(value)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock(side_effect=set_metric)
        return parent

    @pytest.fixture
    def ms_collector(
        self,
        mock_parent: MagicMock,
    ) -> MSCollector:
        """Create MS collector instance."""
        return MSCollector(mock_parent)

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
        """Test STP priority collection.

        F-157: this now uses the 3-arg ``collect_stp_priorities(org_id,
        org_name, device_lookup)`` signature -- the previous 2-arg form bound
        ``device_lookup`` as ``org_name`` and never exercised real metric
        emission. Also resets the F-037 interval gate so the call isn't
        skipped, and asserts actual ``meraki_ms_stp_priority`` gauge samples
        via the registry instead of only call counts.
        """
        # The collector now fetches networks via parent.inventory.get_networks
        # rather than the SDK directly, so the network filter applies.
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_networks = AsyncMock(
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

        # Reset the F-037 interval gate so this call isn't skipped.
        ms_collector._last_stp_collection = 0.0

        # Run collection (3-arg form: org_id, org_name, device_lookup)
        await ms_collector.collect_stp_priorities("org123", "Org 123", device_lookup)

        # Verify network fetch went through inventory (filter applies),
        # not directly to the SDK.
        mock_parent.inventory.get_networks.assert_awaited_once_with("org123")
        assert mock_api.switch.getNetworkSwitchStp.call_count == 2  # Only for net1 and net2

        # Verify metrics were actually set on the real Gauge/registry.
        #
        # NOTE: production's device_info = devices.get(switch_serial, {...})
        # (ms.py collect_stp_priorities) returns the device_lookup entry as-is
        # when a match is found, and that entry (as built by DeviceCollector's
        # real _device_lookup, and in this fixture) does not itself carry a
        # "serial" key -- only "name"/"model" -- so create_device_labels()
        # falls back to serial="" for switches resolved via the lookup. This
        # is a pre-existing behavior (unrelated to F-157/F-037) reflected here
        # rather than fixed, since it is out of this finding's scope; flagged
        # separately in the bug-bash brief.
        net1_labels = {
            "org_id": "org123",
            "org_name": "Org 123",
            "network_id": "net1",
            "network_name": "Network 1",
            "model": "MS250",
            "device_type": "MS",
            "serial": "",
        }
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net1_labels, "name": "Switch 1"},
            )
            == 8192.0
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net1_labels, "name": "Switch 2"},
            )
            == 32768.0
        )

        net2_labels = {
            "org_id": "org123",
            "org_name": "Org 123",
            "network_id": "net2",
            "network_name": "Network 2",
            "model": "MS350",
            "device_type": "MS",
            "serial": "",
        }
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net2_labels, "name": "Switch 3"},
            )
            == 32768.0
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net2_labels, "name": "Switch 4"},
            )
            == 32768.0
        )

    async def test_collect_stp_handles_api_errors(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test STP collection handles API errors gracefully.

        F-157: previously this mocked ``api.organizations.getOrganizationNetworks``,
        which production no longer calls (it goes through
        ``parent.inventory.get_networks``); ``inventory`` was a plain
        ``MagicMock`` so the ``await`` raised ``TypeError`` before
        ``getNetworkSwitchStp`` was ever reached, and the test asserted
        nothing. Now ``inventory.get_networks`` is a real ``AsyncMock`` and we
        assert the STP call was actually attempted.
        """
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_networks = AsyncMock(
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

        # Reset the F-037 interval gate so this call isn't skipped.
        ms_collector._last_stp_collection = 0.0

        # Should not raise due to error handling
        await ms_collector.collect_stp_priorities("org123", "Org 123", {})

        # The STP call must actually have been attempted (previously this
        # test never reached it because inventory.get_networks was un-awaited).
        mock_api.switch.getNetworkSwitchStp.assert_called_once_with("net1")

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

    async def test_collect_emits_port_errors_and_warnings(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that collect() surfaces active per-port errors/warnings.

        A port with active errors/warnings must emit
        meraki_ms_port_errors_total/meraki_ms_port_warnings_total with the raw
        Meraki error/warning string as error_type/warning_type; a clean port
        must emit no series at all for either metric.
        """
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
            "orgId": "org1",
            "orgName": "Org One",
        }

        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "name": "Port 1",
                    "status": "Connected",
                    "errors": ["PoE overload"],
                    "warnings": ["Port flapping"],
                },
                {
                    "portId": "2",
                    "name": "Port 2",
                    "status": "Connected",
                    "errors": [],
                    "warnings": [],
                },
            ]
        )

        await ms_collector.collect(device)

        base_labels = {
            "org_id": "org1",
            "org_name": "Org One",
            "network_id": "net1",
            "network_name": "Test Network",
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "device_type": "MS",
        }

        error_labels = {
            **base_labels,
            "port_id": "1",
            "port_name": "Port 1",
            "error_type": "PoE overload",
        }
        warning_labels = {
            **base_labels,
            "port_id": "1",
            "port_name": "Port 1",
            "warning_type": "Port flapping",
        }

        assert REGISTRY.get_sample_value("meraki_ms_port_errors_total", error_labels) == 1.0
        assert REGISTRY.get_sample_value("meraki_ms_port_warnings_total", warning_labels) == 1.0

        # The clean port must not have emitted any error/warning series.
        clean_error_labels = {
            **base_labels,
            "port_id": "2",
            "port_name": "Port 2",
            "error_type": "PoE overload",
        }
        clean_warning_labels = {
            **base_labels,
            "port_id": "2",
            "port_name": "Port 2",
            "warning_type": "Port flapping",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_errors_total", clean_error_labels) is None
        assert (
            REGISTRY.get_sample_value("meraki_ms_port_warnings_total", clean_warning_labels) is None
        )

    async def test_collect_port_statuses_by_switch_emits_errors_and_warnings(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that the org-level status collection also surfaces errors/warnings."""
        devices = [
            {
                "serial": "Q2XX-XXXX-XXXX",
                "networkId": "net1",
                "networkName": "Test Network",
                "name": "Test Switch",
                "model": "MS250-48",
            }
        ]

        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-XXXX-XXXX",
                    "name": "Test Switch",
                    "model": "MS250-48",
                    "network": {"id": "net1", "name": "Test Network"},
                    "ports": [
                        {
                            "portId": "1",
                            "name": "Port 1",
                            "status": "Connected",
                            "errors": ["Duplex mismatch"],
                            "warnings": [],
                        },
                        {
                            "portId": "2",
                            "name": "Port 2",
                            "status": "Connected",
                            "errors": [],
                            "warnings": [],
                        },
                    ],
                }
            ]
        )

        result = await ms_collector.collect_port_statuses_by_switch("org1", "Org One", devices)

        assert result is True

        labels = {
            "org_id": "org1",
            "org_name": "Org One",
            "network_id": "net1",
            "network_name": "Test Network",
            "serial": "Q2XX-XXXX-XXXX",
            "name": "Test Switch",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
            "port_name": "Port 1",
            "error_type": "Duplex mismatch",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_errors_total", labels) == 1.0

        clean_labels = {**labels, "port_id": "2", "port_name": "Port 2"}
        assert REGISTRY.get_sample_value("meraki_ms_port_errors_total", clean_labels) is None

    async def test_collect_emits_stp_and_8021x_metrics(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that collect() surfaces STP state and 802.1X auth status per port.

        A port with a ``spanningTree`` status must emit
        ``meraki_ms_port_stp_state`` with a ``state`` label per reported state;
        a port with a ``securePort`` block must emit both
        ``meraki_ms_port_8021x_active`` (0/1) and, when an
        ``authenticationStatus`` is present, ``meraki_ms_port_8021x_status``
        with a ``status`` label.
        """
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
            "orgId": "org1",
            "orgName": "Org One",
        }

        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "name": "Port 1",
                    "status": "Connected",
                    "spanningTree": {"statuses": ["forwarding"]},
                    "securePort": {
                        "enabled": True,
                        "active": True,
                        "authenticationStatus": "Authentication successful",
                    },
                },
                {
                    "portId": "2",
                    "name": "Port 2",
                    "status": "Connected",
                    "securePort": {
                        "enabled": True,
                        "active": False,
                    },
                },
                {
                    "portId": "3",
                    "name": "Port 3",
                    "status": "Connected",
                    # No spanningTree/securePort at all.
                },
            ]
        )

        await ms_collector.collect(device)

        base_labels = {
            "org_id": "org1",
            "org_name": "Org One",
            "network_id": "net1",
            "network_name": "Test Network",
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "device_type": "MS",
        }

        stp_labels = {
            **base_labels,
            "port_id": "1",
            "port_name": "Port 1",
            "state": "forwarding",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels) == 1.0

        active_labels_port1 = {**base_labels, "port_id": "1", "port_name": "Port 1"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels_port1) == 1.0

        status_labels = {
            **base_labels,
            "port_id": "1",
            "port_name": "Port 1",
            "status": "Authentication successful",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_status", status_labels) == 1.0

        # Port 2: active=False -> 0, and no authenticationStatus -> no status series.
        active_labels_port2 = {**base_labels, "port_id": "2", "port_name": "Port 2"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels_port2) == 0.0
        status_labels_port2 = {
            **base_labels,
            "port_id": "2",
            "port_name": "Port 2",
            "status": "Authentication successful",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_status", status_labels_port2) is None
        stp_labels_port2 = {
            **base_labels,
            "port_id": "2",
            "port_name": "Port 2",
            "state": "forwarding",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels_port2) is None

        # Port 3: no spanningTree/securePort at all -> nothing emitted for any of these.
        active_labels_port3 = {**base_labels, "port_id": "3", "port_name": "Port 3"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels_port3) is None
        stp_labels_port3 = {
            **base_labels,
            "port_id": "3",
            "port_name": "Port 3",
            "state": "forwarding",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels_port3) is None

    async def test_collect_port_statuses_by_switch_emits_stp_and_8021x(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that the org-level status collection also surfaces STP/802.1X."""
        devices = [
            {
                "serial": "Q2XX-XXXX-XXXX",
                "networkId": "net1",
                "networkName": "Test Network",
                "name": "Test Switch",
                "model": "MS250-48",
            }
        ]

        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-XXXX-XXXX",
                    "name": "Test Switch",
                    "model": "MS250-48",
                    "network": {"id": "net1", "name": "Test Network"},
                    "ports": [
                        {
                            "portId": "1",
                            "name": "Port 1",
                            "status": "Connected",
                            "spanningTree": {"statuses": ["blocking"]},
                            "securePort": {
                                "enabled": True,
                                "active": True,
                                "authenticationStatus": "Authentication successful",
                            },
                        },
                        {
                            "portId": "2",
                            "name": "Port 2",
                            "status": "Connected",
                        },
                    ],
                }
            ]
        )

        result = await ms_collector.collect_port_statuses_by_switch("org1", "Org One", devices)

        assert result is True

        base_labels = {
            "org_id": "org1",
            "org_name": "Org One",
            "network_id": "net1",
            "network_name": "Test Network",
            "serial": "Q2XX-XXXX-XXXX",
            "name": "Test Switch",
            "model": "MS250-48",
            "device_type": "MS",
        }

        stp_labels = {
            **base_labels,
            "port_id": "1",
            "port_name": "Port 1",
            "state": "blocking",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels) == 1.0

        active_labels = {**base_labels, "port_id": "1", "port_name": "Port 1"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels) == 1.0

        status_labels = {
            **base_labels,
            "port_id": "1",
            "port_name": "Port 1",
            "status": "Authentication successful",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_status", status_labels) == 1.0

        # Port 2 had no spanningTree/securePort -> nothing emitted.
        clean_active_labels = {**base_labels, "port_id": "2", "port_name": "Port 2"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", clean_active_labels) is None

    async def test_collect_port_overview_error_shape_does_not_zero_counts(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that an error-shaped overview response does not zero counts.

        F-083: collect_port_overview must wrap the response in
        validate_response_format so the SDK exhausted-retry error dict shape
        ({"errors": [...]}) raises (and is swallowed by with_error_handling)
        instead of being silently interpreted as zero active/inactive counts.
        """
        # Establish a baseline with a normal, successful response.
        mock_api.switch.getOrganizationSwitchPortsOverview = MagicMock(
            return_value={
                "counts": {
                    "byStatus": {
                        "active": {"total": 42, "byMediaAndLinkSpeed": {}},
                        "inactive": {"total": 7, "byMedia": {}},
                    }
                }
            }
        )
        await ms_collector.collect_port_overview("org1", "Org One")

        org_labels = {"org_id": "org1", "org_name": "Org One"}
        assert REGISTRY.get_sample_value("meraki_ms_ports_active_total", org_labels) == 42.0
        assert REGISTRY.get_sample_value("meraki_ms_ports_inactive_total", org_labels) == 7.0

        # Now simulate the SDK exhausted-retry error shape.
        mock_api.switch.getOrganizationSwitchPortsOverview = MagicMock(
            return_value={"errors": ["exhausted retries"]}
        )
        await ms_collector.collect_port_overview("org1", "Org One")

        # Values must be untouched (NOT reset to 0): validate_response_format
        # raises DataValidationError and with_error_handling(continue_on_error=True)
        # swallows it before .set() is ever reached.
        assert REGISTRY.get_sample_value("meraki_ms_ports_active_total", org_labels) == 42.0
        assert REGISTRY.get_sample_value("meraki_ms_ports_inactive_total", org_labels) == 7.0

    async def test_collect_sets_port_status_metric_via_set_metric(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that port_status is routed through parent._set_metric.

        F-084: port_status (and the other per-port/per-device gauges) must
        be routed through ``parent._set_metric`` -- not a bare
        ``.labels().set()`` call -- so expiration tracking covers removed
        switches and stale link_speed/duplex series on renegotiation.
        """
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
            "orgId": "org1",
            "orgName": "Org One",
        }

        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "name": "Port 1",
                    "status": "Connected",
                    "speed": "1 Gbps",
                    "duplex": "full",
                }
            ]
        )

        await ms_collector.collect(device)

        labels = {
            "org_id": "org1",
            "org_name": "Org One",
            "network_id": "net1",
            "network_name": "Test Network",
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
            "port_name": "Port 1",
            "link_speed": "1 Gbps",
            "duplex": "full",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_status", labels) == 1.0

        # Confirm emission actually went through the expiration-tracking
        # helper (mock_parent._set_metric), not a direct .labels().set().
        tracked_metric_names = {
            call.args[3] for call in mock_parent._set_metric.call_args_list if len(call.args) > 3
        }
        assert "meraki_ms_port_status" in tracked_metric_names

    async def test_stp_state_transition_removes_stale_series(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that an STP state transition clears the stale series.

        F-070: a port transitioning STP state must not leave the old
        state's series lingering at 1 alongside the new one for the TTL
        expiration window.
        """
        device = {
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "networkId": "net1",
            "networkName": "Test Network",
            "orgId": "org1",
            "orgName": "Org One",
        }

        def ports_with_state(state: str) -> list[dict]:
            return [
                {
                    "portId": "1",
                    "name": "Port 1",
                    "status": "Connected",
                    "spanningTree": {"statuses": [state]},
                }
            ]

        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=ports_with_state("forwarding")
        )
        await ms_collector.collect(device)

        base_labels = {
            "org_id": "org1",
            "org_name": "Org One",
            "network_id": "net1",
            "network_name": "Test Network",
            "serial": "Q123-456-789",
            "name": "Test Switch",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
            "port_name": "Port 1",
        }
        forwarding_labels = {**base_labels, "state": "forwarding"}
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", forwarding_labels) == 1.0

        # Transition to blocking on the same port.
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=ports_with_state("blocking")
        )
        await ms_collector.collect(device)

        blocking_labels = {**base_labels, "state": "blocking"}
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", blocking_labels) == 1.0
        # The stale forwarding series must be gone, not merely left at 1.
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", forwarding_labels) is None

    async def test_collect_stp_priorities_interval_gated(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that STP priority collection is interval-gated.

        F-037: a second immediate call within the SLOW interval must be
        skipped entirely (no additional getNetworkSwitchStp calls), since STP
        bridge priority is near-static configuration collected at the SLOW
        cadence even though DeviceCollector dispatches this at MEDIUM tier.
        """
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_networks = AsyncMock(
            return_value=[{"id": "net1", "name": "Network 1", "productTypes": ["switch"]}]
        )
        mock_api.switch.getNetworkSwitchStp = MagicMock(
            return_value={"rstpEnabled": True, "stpBridgePriority": []}
        )

        ms_collector._last_stp_collection = 0.0
        await ms_collector.collect_stp_priorities("org123", "Org One", {})
        assert mock_api.switch.getNetworkSwitchStp.call_count == 1

        # Immediately call again: the SLOW-interval gate should skip it.
        await ms_collector.collect_stp_priorities("org123", "Org One", {})
        assert mock_api.switch.getNetworkSwitchStp.call_count == 1
