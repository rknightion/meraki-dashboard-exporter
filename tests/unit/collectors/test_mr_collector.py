"""Tests for MR (Wireless Access Point) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

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
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collectors emit all rows.
        parent.inventory = None

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
        mock_parent: MagicMock,
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

        # Verify the online client count was actually emitted for the AP.
        ap_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mr_collector._ap_clients
        ]
        assert len(ap_calls) == 1
        _, labels, value = ap_calls[0][0]
        assert value == 25
        assert labels["serial"] == "Q123"
        assert labels["network_id"] == "net1"

    async def test_collect_wireless_clients_list_response(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
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

        # Verify the online client count was emitted with the parsed value.
        ap_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mr_collector._ap_clients
        ]
        assert len(ap_calls) == 1
        _, labels, value = ap_calls[0][0]
        assert value == 30
        assert labels["serial"] == "Q123"

    def test_packet_metric_value_retention(self, mr_collector: MRCollector) -> None:
        """Test that packet metrics have a cache for retaining values."""
        # Simply verify the collector has the packet value cache initialized
        assert hasattr(mr_collector, "_packet_value_cache")
        assert isinstance(mr_collector._packet_value_cache, dict)

    async def test_collect_connection_stats_network_level(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
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

        # Verify each stat_type value was emitted per device per network.
        stat_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._ap_connection_stats
        ]
        # 2 networks * 2 devices * 5 stat types
        assert len(stat_calls) == 20
        # Q123 "success" stat over both networks carries the parsed value 90.
        q123_success = [
            c[0][2]
            for c in stat_calls
            if c[0][1]["serial"] == "Q123" and c[0][1]["stat_type"] == "success"
        ]
        assert q123_success == [90, 90]

    async def test_collect_ssid_usage(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """SSID usage emits one org-level series per SSID from the spec shape.

        The API returns one org-wide row per SSID name with nested
        ``usage.{total,downstream,upstream,percentage}`` and
        ``clients.counts.total`` (not the flat fields an earlier mock invented),
        and the exporter must label at org+SSID level only (no per-network
        replication — F-082) and request the top 50 (F-114).
        """
        org_id = "123"
        org_name = "Test Org"

        mock_api.organizations.getOrganizationSummaryTopSsidsByUsage = MagicMock(
            return_value=[
                {
                    "name": "Guest WiFi",
                    "usage": {
                        "total": 1536.75,
                        "downstream": 1024.5,
                        "upstream": 512.25,
                        "percentage": 45.5,
                    },
                    "clients": {"counts": {"total": 150}},
                },
                {
                    "name": "Corporate WiFi",
                    "usage": {
                        "total": 3072.0,
                        "downstream": 2048.0,
                        "upstream": 1024.0,
                        "percentage": 54.5,
                    },
                    "clients": {"counts": {"total": 200}},
                },
            ]
        )

        # Run collection
        await mr_collector.collect_ssid_usage(org_id, org_name)

        # Verify API call requests the top 50 SSIDs (endpoint default is only 10).
        mock_api.organizations.getOrganizationSummaryTopSsidsByUsage.assert_called_once_with(
            org_id, quantity=50
        )

        # Total-usage series: exactly one per SSID, org+SSID labels only, correct value.
        total_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._ssid_usage_total_mb
        ]
        assert len(total_calls) == 2
        by_ssid = {c[0][1]["ssid"]: c[0] for c in total_calls}
        assert set(by_ssid) == {"Guest WiFi", "Corporate WiFi"}
        for _, labels, _ in by_ssid.values():
            assert set(labels) == {"org_id", "org_name", "ssid"}
        # Values are converted from MB (decimal) to bytes at the emit site
        # (×1,000,000) per issue #531 APIDEV-03.
        assert by_ssid["Guest WiFi"][2] == 1536.75 * 1_000_000
        assert by_ssid["Corporate WiFi"][2] == 3072.0 * 1_000_000

        # Client-count series carries the nested clients.counts.total value.
        client_calls = {
            c[0][1]["ssid"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._ssid_client_count
        }
        assert client_calls == {"Guest WiFi": 150, "Corporate WiFi": 200}

    async def test_collect_ethernet_status_power_modes(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Ethernet status parses the nested power object and paginates.

        Production reads ``power.mode`` / ``power.ac.isConnected`` /
        ``power.poe.isConnected`` (not the flat ``powerMode``/``isConnected`` an
        earlier mock invented), and must paginate the org-wide endpoint
        (default perPage is only 100, so >100 APs were dropped — F-012).
        """
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
                    "power": {"mode": "poe", "poe": {"isConnected": True}},
                },
                {
                    "serial": "Q456",
                    "name": "AP2",
                    "network": {"id": "net1", "name": "Network 1"},
                    "power": {"mode": "ac", "ac": {"isConnected": True}},
                },
            ]
        )

        # Run collection
        await mr_collector.collect_ethernet_status(org_id, "Test Org", device_lookup)

        # Verify API was called with full pagination (all pages, max perPage).
        mock_api.wireless.getOrganizationWirelessDevicesEthernetStatuses.assert_called_once_with(
            org_id, total_pages="all", perPage=1000
        )

        # power_info emitted once per AP (mode is truthy for both).
        power_info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._mr_power_info
        ]
        modes = {c[0][1]["serial"]: c[0][1]["mode"] for c in power_info_calls}
        assert modes == {"Q123": "poe", "Q456": "ac"}

        # AC-connected gauge: Q456 (ac) is 1, Q123 (poe, no ac block) is 0.
        ac_calls = {
            c[0][1]["serial"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._mr_power_ac_connected
        }
        assert ac_calls["Q456"] == 1
        assert ac_calls["Q123"] == 0

        # PoE-connected gauge: Q123 (poe) is 1, Q456 (ac, no poe block) is 0.
        poe_calls = {
            c[0][1]["serial"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._mr_power_poe_connected
        }
        assert poe_calls["Q123"] == 1
        assert poe_calls["Q456"] == 0

    async def test_collect_cpu_load_paginates_and_emits(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """CPU-load fetch paginates (perPage default 10 dropped half each batch).

        getOrganizationWirelessDevicesSystemCpuLoadHistory defaults to
        total_pages=1, perPage=10 — with batches of up to 20 serials only ~10
        rows came back per call (F-081). We now pass total_pages='all', perPage=20.
        """
        mock_parent.settings.api.batch_size = 20
        devices = [
            {"serial": "Q123", "name": "AP1", "model": "MR46", "networkId": "net1"},
        ]

        mock_api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory = MagicMock(
            return_value=[
                {"serial": "Q123", "history": [{"load": 12.0}, {"load": 37.5}]},
            ]
        )

        await mr_collector.collect_cpu_load("org1", "Test Org", devices)

        _, kwargs = mock_api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory.call_args
        assert kwargs["total_pages"] == "all"
        assert kwargs["perPage"] == 20
        assert kwargs["serials"] == ["Q123"]

        cpu_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mr_collector._mr_cpu_load_5min
        ]
        assert len(cpu_calls) == 1
        # Most-recent history reading is used.
        assert cpu_calls[0][0][2] == 37.5

    async def test_collect_wireless_clients_respects_network_filter(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Wireless client metrics for excluded networks must be skipped."""
        mock_api.wireless.getOrganizationWirelessClientsOverviewByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "network": {"id": "N_INCLUDED", "name": "Prod"},
                    "counts": {"byStatus": {"online": 5}},
                },
                {
                    "serial": "Q-OUT",
                    "network": {"id": "N_EXCLUDED", "name": "Lab"},
                    "counts": {"byStatus": {"online": 7}},
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mr_collector.collect_wireless_clients("org1", "Test Org", {})

        ap_clients_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mr_collector._ap_clients
        ]
        assert len(ap_clients_calls) == 1
        _, labels, value = ap_clients_calls[0][0]
        assert labels["network_id"] == "N_INCLUDED"
        assert value == 5

    async def test_collect_ssid_status_respects_network_filter(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """SSID radio metrics for excluded networks must be skipped."""
        mock_api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "network": {"id": "N_INCLUDED", "name": "Prod"},
                    "basicServiceSets": [
                        {"radio": {"band": "5", "index": 0, "isBroadcasting": True}},
                    ],
                },
                {
                    "serial": "Q-OUT",
                    "network": {"id": "N_EXCLUDED", "name": "Lab"},
                    "basicServiceSets": [
                        {"radio": {"band": "5", "index": 0, "isBroadcasting": True}},
                    ],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mr_collector.collect_ssid_status("org1", "Test Org", {})

        for call in mock_parent._set_metric.call_args_list:
            _, labels, _ = call[0]
            assert labels.get("network_id") != "N_EXCLUDED"

    async def test_collect_packet_loss_respects_network_filter(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Packet-loss rows outside the filter are skipped (both endpoints).

        The response nests the network under ``network.{id,name}`` (there is no
        flat networkId/networkName and no ``devices`` array); per-device rows come
        from the separate ...PacketLossByDevice op. Both are filtered by network.
        """
        # Network-level endpoint: nested "network" object per the spec.
        mock_api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork = MagicMock(
            return_value=[
                {
                    "network": {"id": "N_INCLUDED", "name": "Prod"},
                    "downstream": {"total": 1000, "lost": 5, "lossPercentage": 0.5},
                    "upstream": {"total": 800, "lost": 4, "lossPercentage": 0.5},
                },
                {
                    "network": {"id": "N_EXCLUDED", "name": "Lab"},
                    "downstream": {"total": 999, "lost": 99, "lossPercentage": 9.9},
                    "upstream": {"total": 999, "lost": 99, "lossPercentage": 9.9},
                },
            ]
        )
        # Device-level endpoint: nested "network" + "device" per the spec.
        mock_api.wireless.getOrganizationWirelessDevicesPacketLossByDevice = MagicMock(
            return_value=[
                {
                    "network": {"id": "N_INCLUDED", "name": "Prod"},
                    "device": {"serial": "Q-IN"},
                    "downstream": {"total": 500, "lost": 2, "lossPercentage": 0.4},
                    "upstream": {"total": 400, "lost": 2, "lossPercentage": 0.5},
                },
                {
                    "network": {"id": "N_EXCLUDED", "name": "Lab"},
                    "device": {"serial": "Q-OUT"},
                    "downstream": {"total": 999, "lost": 99, "lossPercentage": 9.9},
                    "upstream": {"total": 999, "lost": 99, "lossPercentage": 9.9},
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mr_collector.collect_packet_loss("org1", "Test Org", {})

        # Included rows must actually emit (proves the nested parse works), and
        # no N_EXCLUDED / Q-OUT rows may appear.
        emitted_networks = set()
        emitted_serials = set()
        for call in mock_parent._set_metric.call_args_list:
            _, labels, _ = call[0]
            assert labels.get("network_id") != "N_EXCLUDED"
            assert labels.get("serial") != "Q-OUT"
            if labels.get("network_id"):
                emitted_networks.add(labels["network_id"])
            if labels.get("serial"):
                emitted_serials.add(labels["serial"])
        assert emitted_networks == {"N_INCLUDED"}
        assert emitted_serials == {"Q-IN"}

    async def test_collect_ethernet_status_respects_network_filter(
        self,
        mr_collector: MRCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Ethernet status rows for excluded networks must be skipped."""
        mock_api.wireless.getOrganizationWirelessDevicesEthernetStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "name": "AP-IN",
                    "network": {"id": "N_INCLUDED", "name": "Prod"},
                    "power": {"mode": "ac", "ac": {"isConnected": True}},
                },
                {
                    "serial": "Q-OUT",
                    "name": "AP-OUT",
                    "network": {"id": "N_EXCLUDED", "name": "Lab"},
                    "power": {"mode": "ac", "ac": {"isConnected": True}},
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mr_collector.collect_ethernet_status("org1", "Test Org", {})

        for call in mock_parent._set_metric.call_args_list:
            _, labels, _ = call[0]
            assert labels.get("network_id") != "N_EXCLUDED"
            assert labels.get("serial") != "Q-OUT"
