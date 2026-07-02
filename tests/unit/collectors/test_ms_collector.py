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
        # F-174: every meraki_ms_stp_priority series must carry the switch's
        # REAL serial (the key of the STP switch_priorities map), not serial=""
        # -- device_lookup entries carry name/model but no "serial" key, so the
        # collector now always stamps the real serial before building labels.
        net1_labels = {
            "org_id": "org123",
            "network_id": "net1",
            "model": "MS250",
            "device_type": "MS",
        }
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net1_labels, "serial": "Q2MW-42Z2-JE5T"},
            )
            == 8192.0
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net1_labels, "serial": "Q2BX-Q43Y-RR5C"},
            )
            == 32768.0
        )

        net2_labels = {
            "org_id": "org123",
            "network_id": "net2",
            "model": "MS350",
            "device_type": "MS",
        }
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net2_labels, "serial": "Q2HP-F6VX-M24J"},
            )
            == 32768.0
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority",
                {**net2_labels, "serial": "Q2HP-K4VW-87YT"},
            )
            == 32768.0
        )

    async def test_collect_stp_priorities_same_name_distinct_serials(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """F-174 regression: two same-named switches in a network keep distinct series.

        Previously lookup-matched switches emitted serial="" so two switches
        sharing a name (or a blank name) in the same network collapsed onto a
        single (network, name) series and overwrote each other. With the real
        serial always present, each switch has its own series.
        """
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_networks = AsyncMock(
            return_value=[{"id": "net1", "name": "Network 1", "productTypes": ["switch"]}]
        )

        # Two switches that share the SAME name in the same network.
        device_lookup = {
            "Q2AA-1111-1111": {"name": "access-sw", "model": "MS120"},
            "Q2BB-2222-2222": {"name": "access-sw", "model": "MS120"},
        }

        mock_api.switch.getNetworkSwitchStp = MagicMock(
            return_value={
                "rstpEnabled": True,
                "stpBridgePriority": [
                    {"switches": ["Q2AA-1111-1111"], "stpPriority": 4096},
                    {"switches": ["Q2BB-2222-2222"], "stpPriority": 8192},
                ],
            }
        )

        ms_collector._last_stp_collection = 0.0
        await ms_collector.collect_stp_priorities("org123", "Org 123", device_lookup)

        base = {
            "org_id": "org123",
            "network_id": "net1",
            "model": "MS120",
            "device_type": "MS",
        }
        # Distinct series keyed by real serial, no collision/overwrite.
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority", {**base, "serial": "Q2AA-1111-1111"}
            )
            == 4096.0
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_stp_priority", {**base, "serial": "Q2BB-2222-2222"}
            )
            == 8192.0
        )
        # The empty-serial collision series must not exist.
        assert REGISTRY.get_sample_value("meraki_ms_stp_priority", {**base, "serial": ""}) is None

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
        meraki_ms_port_error_active/meraki_ms_port_warning_active with the raw
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
            "network_id": "net1",
            "serial": "Q123-456-789",
            "model": "MS250-48",
            "device_type": "MS",
        }

        error_labels = {
            **base_labels,
            "port_id": "1",
            "error_type": "PoE overload",
        }
        warning_labels = {
            **base_labels,
            "port_id": "1",
            "warning_type": "Port flapping",
        }

        assert REGISTRY.get_sample_value("meraki_ms_port_error_active", error_labels) == 1.0
        assert REGISTRY.get_sample_value("meraki_ms_port_warning_active", warning_labels) == 1.0

        # The clean port must not have emitted any error/warning series.
        clean_error_labels = {
            **base_labels,
            "port_id": "2",
            "error_type": "PoE overload",
        }
        clean_warning_labels = {
            **base_labels,
            "port_id": "2",
            "warning_type": "Port flapping",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_error_active", clean_error_labels) is None
        assert (
            REGISTRY.get_sample_value("meraki_ms_port_warning_active", clean_warning_labels) is None
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
            "network_id": "net1",
            "serial": "Q2XX-XXXX-XXXX",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
            "error_type": "Duplex mismatch",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_error_active", labels) == 1.0

        clean_labels = {**labels, "port_id": "2"}
        assert REGISTRY.get_sample_value("meraki_ms_port_error_active", clean_labels) is None

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
            "network_id": "net1",
            "serial": "Q123-456-789",
            "model": "MS250-48",
            "device_type": "MS",
        }

        stp_labels = {
            **base_labels,
            "port_id": "1",
            "state": "forwarding",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels) == 1.0

        active_labels_port1 = {**base_labels, "port_id": "1"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels_port1) == 1.0

        status_labels = {
            **base_labels,
            "port_id": "1",
            "status": "Authentication successful",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_status", status_labels) == 1.0

        # Port 2: active=False -> 0, and no authenticationStatus -> no status series.
        active_labels_port2 = {**base_labels, "port_id": "2"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels_port2) == 0.0
        status_labels_port2 = {
            **base_labels,
            "port_id": "2",
            "status": "Authentication successful",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_status", status_labels_port2) is None
        stp_labels_port2 = {
            **base_labels,
            "port_id": "2",
            "state": "forwarding",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels_port2) is None

        # Port 3: no spanningTree/securePort at all -> nothing emitted for any of these.
        active_labels_port3 = {**base_labels, "port_id": "3"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels_port3) is None
        stp_labels_port3 = {
            **base_labels,
            "port_id": "3",
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
            "network_id": "net1",
            "serial": "Q2XX-XXXX-XXXX",
            "model": "MS250-48",
            "device_type": "MS",
        }

        stp_labels = {
            **base_labels,
            "port_id": "1",
            "state": "blocking",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_stp_state", stp_labels) == 1.0

        active_labels = {**base_labels, "port_id": "1"}
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_active", active_labels) == 1.0

        status_labels = {
            **base_labels,
            "port_id": "1",
            "status": "Authentication successful",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_8021x_status", status_labels) == 1.0

        # Port 2 had no spanningTree/securePort -> nothing emitted.
        clean_active_labels = {**base_labels, "port_id": "2"}
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

        org_labels = {"org_id": "org1"}
        assert REGISTRY.get_sample_value("meraki_ms_ports_active", org_labels) == 42.0
        assert REGISTRY.get_sample_value("meraki_ms_ports_inactive", org_labels) == 7.0

        # Now simulate the SDK exhausted-retry error shape.
        mock_api.switch.getOrganizationSwitchPortsOverview = MagicMock(
            return_value={"errors": ["exhausted retries"]}
        )
        await ms_collector.collect_port_overview("org1", "Org One")

        # Values must be untouched (NOT reset to 0): validate_response_format
        # raises DataValidationError and with_error_handling(continue_on_error=True)
        # swallows it before .set() is ever reached.
        assert REGISTRY.get_sample_value("meraki_ms_ports_active", org_labels) == 42.0
        assert REGISTRY.get_sample_value("meraki_ms_ports_inactive", org_labels) == 7.0

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
            "network_id": "net1",
            "serial": "Q123-456-789",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
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
            "network_id": "net1",
            "serial": "Q123-456-789",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
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

    async def test_collect_port_usage_by_switch_emits_usage_poe_clients(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """F-168: org-wide usage/PoE path emits identical usage/traffic/PoE/client metrics.

        Fetches the org-wide usage-history endpoint (per-port ``data.usage`` KB,
        ``bandwidth.usage`` kbps, ``energy.usage.total`` Wh) plus the org-wide
        clients-overview endpoint, aggregates the interval series, and emits the
        same six metrics the per-device loop does.
        """
        devices = [
            {
                "serial": "Q2XX-0001",
                "networkId": "net1",
                "networkName": "Net One",
                "name": "SW1",
                "model": "MS250-48",
            }
        ]

        mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-0001",
                    "name": "SW1",
                    "model": "MS250-48",
                    "network": {"id": "net1", "name": "Net One"},
                    "ports": [
                        {
                            "portId": "1",
                            "intervals": [
                                {
                                    "data": {
                                        "usage": {
                                            "total": 100,
                                            "upstream": 40,
                                            "downstream": 60,
                                        }
                                    },
                                    "bandwidth": {
                                        "usage": {
                                            "total": 8.0,
                                            "upstream": 3.0,
                                            "downstream": 5.0,
                                        }
                                    },
                                    "energy": {"usage": {"total": 2.0}},
                                },
                                {
                                    "data": {
                                        "usage": {
                                            "total": 200,
                                            "upstream": 60,
                                            "downstream": 140,
                                        }
                                    },
                                    "bandwidth": {
                                        "usage": {
                                            "total": 12.0,
                                            "upstream": 5.0,
                                            "downstream": 7.0,
                                        }
                                    },
                                    "energy": {"usage": {"total": 3.0}},
                                },
                            ],
                        }
                    ],
                }
            ]
        )
        mock_api.switch.getOrganizationSwitchPortsClientsOverviewByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-0001",
                    "ports": [
                        {"portId": "1", "counts": {"byStatus": {"online": 7}}},
                    ],
                }
            ]
        )

        result = await ms_collector.collect_port_usage_by_switch("org1", "Org One", devices)
        assert result is True

        # Scoped the org query to the requested serials.
        mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval.assert_called_once()
        _, kwargs = (
            mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval.call_args
        )
        assert kwargs["serials"] == ["Q2XX-0001"]

        base = {
            "org_id": "org1",
            "network_id": "net1",
            "serial": "Q2XX-0001",
            "model": "MS250-48",
            "device_type": "MS",
            "port_id": "1",
        }

        # Usage bytes: sum of interval decimal KB * 1000 (D5: not KiB x1024).
        assert (
            REGISTRY.get_sample_value("meraki_ms_port_usage_bytes", {**base, "direction": "total"})
            == 300 * 1000
        )
        assert (
            REGISTRY.get_sample_value("meraki_ms_port_usage_bytes", {**base, "direction": "tx"})
            == 100 * 1000
        )
        assert (
            REGISTRY.get_sample_value("meraki_ms_port_usage_bytes", {**base, "direction": "rx"})
            == 200 * 1000
        )

        # Traffic rate: averaged bandwidth kbps * 1000 / 8. up=(3+5)/2=4, down=(5+7)/2=6.
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_port_traffic_bytes_per_second", {**base, "direction": "tx"}
            )
            == 4.0 * 1000 / 8
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_port_traffic_bytes_per_second", {**base, "direction": "rx"}
            )
            == 6.0 * 1000 / 8
        )

        # PoE joules: sum of interval energy (5.0 Wh) converted x3600 (D3).
        assert REGISTRY.get_sample_value("meraki_ms_poe_port_energy_joules", base) == 5.0 * 3600

        # Client count from the clients-overview lookup.
        assert REGISTRY.get_sample_value("meraki_ms_port_client_count", base) == 7.0

        # Switch-level PoE total (Wh sum x3600 = joules) + total power draw
        # (deliberately unconverted Wh-as-watts approximation, out of scope for #531).
        device_labels = {
            "org_id": "org1",
            "network_id": "net1",
            "serial": "Q2XX-0001",
            "model": "MS250-48",
            "device_type": "MS",
        }
        assert (
            REGISTRY.get_sample_value("meraki_ms_poe_total_energy_joules", device_labels)
            == 5.0 * 3600
        )
        assert REGISTRY.get_sample_value("meraki_ms_power_usage_watts", device_labels) == 5.0

    async def test_collect_port_usage_by_switch_defaults_absent_client_count_to_zero(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """F-168: ports absent from clients-overview emit client_count=0."""
        devices = [{"serial": "Q2XX-0002", "networkId": "net1", "name": "SW2", "model": "MS120-8"}]
        mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-0002",
                    "name": "SW2",
                    "model": "MS120-8",
                    "network": {"id": "net1", "name": "net1"},
                    "ports": [{"portId": "3", "intervals": [{"energy": {"usage": {"total": 0}}}]}],
                }
            ]
        )
        # clients-overview lists no ports for this switch.
        mock_api.switch.getOrganizationSwitchPortsClientsOverviewByDevice = MagicMock(
            return_value=[]
        )

        result = await ms_collector.collect_port_usage_by_switch("org1", "Org One", devices)
        assert result is True

        base = {
            "org_id": "org1",
            "network_id": "net1",
            "serial": "Q2XX-0002",
            "model": "MS120-8",
            "device_type": "MS",
            "port_id": "3",
        }
        assert REGISTRY.get_sample_value("meraki_ms_port_client_count", base) == 0.0

    async def test_collect_port_usage_by_switch_unsupported_returns_false(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """F-168: missing SDK endpoint -> returns False so caller falls back."""
        # Use a spec-limited switch mock lacking the usage-history method so the
        # hasattr() probe fails (a bare MagicMock auto-creates every attribute).
        mock_api.switch = MagicMock(spec=["getOrganizationSwitchPortsClientsOverviewByDevice"])

        devices = [{"serial": "Q2XX-0003", "networkId": "net1", "name": "SW3", "model": "MS120"}]
        result = await ms_collector.collect_port_usage_by_switch("org1", "Org One", devices)
        assert result is False

    async def test_collect_emits_ms_port_info_per_device_path(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """#534: the per-device fallback emits meraki_ms_port_info (value 1).

        The info series is keyed on the stable ``(serial, port_id)`` and carries
        the mutable ``port_name`` so the numeric per-port series can stay
        id-only. A port lacking a ``name`` defaults to ``"Port {port_id}"``.
        Exactly one info series per port, and no name-family labels leak onto it.
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
                {"portId": "1", "name": "Uplink Port", "status": "Connected"},
                {"portId": "2", "status": "Connected"},  # no name -> "Port 2"
            ]
        )

        await ms_collector.collect(device)

        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_port_info",
                {
                    "org_id": "org1",
                    "network_id": "net1",
                    "serial": "Q123-456-789",
                    "port_id": "1",
                    "port_name": "Uplink Port",
                },
            )
            == 1.0
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_port_info",
                {
                    "org_id": "org1",
                    "network_id": "net1",
                    "serial": "Q123-456-789",
                    "port_id": "2",
                    "port_name": "Port 2",
                },
            )
            == 1.0
        )

        # Exactly one info series per port (2 ports -> 2 series).
        info_samples = [
            s
            for mf in REGISTRY.collect()
            if mf.name == "meraki_ms_port_info"
            for s in mf.samples
            if s.name == "meraki_ms_port_info"
        ]
        assert len(info_samples) == 2

    async def test_collect_port_statuses_by_switch_emits_ms_port_info(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
    ) -> None:
        """#534: the org-wide status path also emits meraki_ms_port_info."""
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
                        {"portId": "1", "name": "Port 1", "status": "Connected"},
                    ],
                }
            ]
        )

        result = await ms_collector.collect_port_statuses_by_switch("org1", "Org One", devices)
        assert result is True

        assert (
            REGISTRY.get_sample_value(
                "meraki_ms_port_info",
                {
                    "org_id": "org1",
                    "network_id": "net1",
                    "serial": "Q2XX-XXXX-XXXX",
                    "port_id": "1",
                    "port_name": "Port 1",
                },
            )
            == 1.0
        )

    async def test_ms_port_info_routes_through_set_metric_for_expiration(
        self,
        ms_collector: MSCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """#534: meraki_ms_port_info must emit via parent._set_metric.

        Routing through ``_set_metric`` (with the metric name as the 4th arg)
        is what registers the series with the MetricExpirationManager so a
        removed port's info series expires instead of lingering forever (same
        class as the F-084/F-175 routing guarantees for the other MS series).
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
            return_value=[{"portId": "1", "name": "Port 1", "status": "Connected"}]
        )

        await ms_collector.collect(device)

        tracked_metric_names = {
            call.args[3] for call in mock_parent._set_metric.call_args_list if len(call.args) > 3
        }
        assert "meraki_ms_port_info" in tracked_metric_names
