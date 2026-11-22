"""Tests for the SSIDPerformanceCollector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors import network_health
from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.collectors.network_health_collectors.ssid_performance import (
    SSIDPerformanceCollector,
)
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory


class TestSSIDPerformanceCollector(BaseCollectorTest):
    """Tests for SSIDPerformanceCollector via NetworkHealthCollector."""

    collector_class = NetworkHealthCollector

    def _update_all_subcollector_apis(
        self, collector: NetworkHealthCollector, api: MagicMock
    ) -> None:
        """Update API references on all sub-collectors."""
        collector.api = api
        collector.rf_health_collector.api = api
        collector.connection_stats_collector.api = api
        collector.data_rates_collector.api = api
        collector.bluetooth_collector.api = api
        collector.ssid_performance_collector.api = api

    async def test_collect_failed_connections_by_ssid_and_step(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """Test that failed connections are aggregated by SSID and failure step."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        # The API returns one row per failure EVENT (spec shape: ssidNumber, vlan,
        # clientMac, serial, radio, failureStep, type, ts) — there is no `failures`
        # count field. Aggregation is by counting rows: SSID0/auth=5, SSID1/dhcp=5,
        # SSID0/assoc=1.
        failed_connections_data = [
            {
                "ssidNumber": 0,
                "vlan": 100,
                "clientMac": "aa:bb:cc:00:00:01",
                "serial": "Q2XX-0001",
                "radio": 0,
                "failureStep": "auth",
                "type": "802.1X auth fail",
                "ts": "2024-01-01T12:00:00Z",
            },
            {
                "ssidNumber": 0,
                "vlan": 100,
                "clientMac": "aa:bb:cc:00:00:02",
                "serial": "Q2XX-0001",
                "radio": 1,
                "failureStep": "auth",
                "type": "802.1X auth fail",
                "ts": "2024-01-01T12:00:05Z",
            },
            {
                "ssidNumber": 0,
                "vlan": 100,
                "clientMac": "aa:bb:cc:00:00:03",
                "serial": "Q2XX-0002",
                "radio": 0,
                "failureStep": "auth",
                "type": "802.1X auth fail",
                "ts": "2024-01-01T12:00:10Z",
            },
            {
                "ssidNumber": 0,
                "vlan": 100,
                "clientMac": "aa:bb:cc:00:00:04",
                "serial": "Q2XX-0002",
                "radio": 1,
                "failureStep": "auth",
                "type": "802.1X auth fail",
                "ts": "2024-01-01T12:00:15Z",
            },
            {
                "ssidNumber": 0,
                "vlan": 100,
                "clientMac": "aa:bb:cc:00:00:05",
                "serial": "Q2XX-0002",
                "radio": 0,
                "failureStep": "auth",
                "type": "802.1X auth fail",
                "ts": "2024-01-01T12:00:20Z",
            },
            {
                "ssidNumber": 1,
                "vlan": 200,
                "clientMac": "aa:bb:cc:00:00:06",
                "serial": "Q2XX-0001",
                "radio": 0,
                "failureStep": "dhcp",
                "type": "dhcp timeout",
                "ts": "2024-01-01T12:01:00Z",
            },
            {
                "ssidNumber": 1,
                "vlan": 200,
                "clientMac": "aa:bb:cc:00:00:07",
                "serial": "Q2XX-0001",
                "radio": 1,
                "failureStep": "dhcp",
                "type": "dhcp timeout",
                "ts": "2024-01-01T12:01:05Z",
            },
            {
                "ssidNumber": 1,
                "vlan": 200,
                "clientMac": "aa:bb:cc:00:00:08",
                "serial": "Q2XX-0002",
                "radio": 0,
                "failureStep": "dhcp",
                "type": "dhcp timeout",
                "ts": "2024-01-01T12:01:10Z",
            },
            {
                "ssidNumber": 1,
                "vlan": 200,
                "clientMac": "aa:bb:cc:00:00:09",
                "serial": "Q2XX-0002",
                "radio": 1,
                "failureStep": "dhcp",
                "type": "dhcp timeout",
                "ts": "2024-01-01T12:01:15Z",
            },
            {
                "ssidNumber": 1,
                "vlan": 200,
                "clientMac": "aa:bb:cc:00:00:10",
                "serial": "Q2XX-0002",
                "radio": 0,
                "failureStep": "dhcp",
                "type": "dhcp timeout",
                "ts": "2024-01-01T12:01:20Z",
            },
            {
                "ssidNumber": 0,
                "vlan": 100,
                "clientMac": "aa:bb:cc:00:00:11",
                "serial": "Q2XX-0001",
                "radio": 0,
                "failureStep": "assoc",
                "type": "assoc timeout",
                "ts": "2024-01-01T12:02:00Z",
            },
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessBluetoothClients", [])
            .with_custom_response("getNetworkWirelessFailedConnections", failed_connections_data)
            .build()
        )
        api.wireless.getNetworkWirelessFailedConnections = MagicMock(
            return_value=failed_connections_data
        )
        self._update_all_subcollector_apis(collector, api)

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # SSID 0, auth: 3 + 2 = 5 (ID-only; org_name/network_name dropped per #534)
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count",
            5,
            org_id=org["id"],
            network_id=network["id"],
            ssid="0",
            failure_step="auth",
        )
        # SSID 1, dhcp: 5
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count",
            5,
            org_id=org["id"],
            network_id=network["id"],
            ssid="1",
            failure_step="dhcp",
        )
        # SSID 0, assoc: 1
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count",
            1,
            org_id=org["id"],
            network_id=network["id"],
            ssid="0",
            failure_step="assoc",
        )

    async def test_collect_empty_failed_connections(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """A first-pass empty response is handled gracefully and writes no series.

        Nothing was emitted before, so there is no key to zero; see
        test_failed_connections_zeroed_when_window_is_empty for the two-pass case.
        """
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessBluetoothClients", [])
            .with_custom_response("getNetworkWirelessFailedConnections", [])
            .build()
        )
        api.wireless.getNetworkWirelessFailedConnections = MagicMock(return_value=[])
        self._update_all_subcollector_apis(collector, api)

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # No failed connections metrics should be set
        self.verify_no_metrics_set(metrics, ["meraki_mr_ssid_failed_connections_count"])

    def _failed_connections_api(self, mock_api_builder, org, network, rows) -> MagicMock:
        """Build a mock API whose failed-connections call returns ``rows``."""
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessBluetoothClients", [])
            .build()
        )
        api.wireless.getNetworkWirelessFailedConnections = MagicMock(return_value=rows)
        return api

    @pytest.fixture
    def advance_failed_connections_window(self, collector, monkeypatch):
        """Advance the network-health cursor clock to the next collection window."""
        now = 100.0
        monkeypatch.setattr(network_health, "monotonic", lambda: now)

        def advance() -> None:
            nonlocal now
            now += collector._group_interval(EndpointGroupName.NH_FAILED_CONNECTIONS)

        return advance

    async def test_failed_connections_zeroed_when_window_is_empty(
        self, collector, mock_api_builder, metrics, advance_failed_connections_window
    ) -> None:
        """A burst followed by a successful empty window reads 0 for that network (#992)."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        rows = [
            {"ssidNumber": 0, "failureStep": "auth", "ts": "2024-01-01T12:00:00Z"},
            {"ssidNumber": 0, "failureStep": "auth", "ts": "2024-01-01T12:00:05Z"},
            {"ssidNumber": 1, "failureStep": "dhcp", "ts": "2024-01-01T12:00:10Z"},
        ]
        api = self._failed_connections_api(mock_api_builder, org, network, rows)
        self._update_all_subcollector_apis(collector, api)

        await self.run_collector(collector)
        labels = {"org_id": org["id"], "network_id": network["id"]}
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 2, ssid="0", failure_step="auth", **labels
        )
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 1, ssid="1", failure_step="dhcp", **labels
        )

        api.wireless.getNetworkWirelessFailedConnections.return_value = []
        advance_failed_connections_window()
        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 0, ssid="0", failure_step="auth", **labels
        )
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 0, ssid="1", failure_step="dhcp", **labels
        )

    async def test_failed_connections_zeroes_only_pairs_that_disappeared(
        self, collector, mock_api_builder, metrics, advance_failed_connections_window
    ) -> None:
        """A smaller successful window keeps present pairs and zeroes the missing one (#992)."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        api = self._failed_connections_api(
            mock_api_builder,
            org,
            network,
            [
                {"ssidNumber": 0, "failureStep": "auth", "ts": "2024-01-01T12:00:00Z"},
                {"ssidNumber": 1, "failureStep": "dhcp", "ts": "2024-01-01T12:00:10Z"},
            ],
        )
        self._update_all_subcollector_apis(collector, api)
        await self.run_collector(collector)

        api.wireless.getNetworkWirelessFailedConnections.return_value = [
            {"ssidNumber": 0, "failureStep": "auth", "ts": "2024-01-01T13:00:00Z"}
        ]
        advance_failed_connections_window()
        await self.run_collector(collector)

        labels = {"org_id": org["id"], "network_id": network["id"]}
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 1, ssid="0", failure_step="auth", **labels
        )
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 0, ssid="1", failure_step="dhcp", **labels
        )

    async def test_failed_fetch_does_not_zero(self, collector, mock_api_builder, metrics) -> None:
        """A failed fetch writes nothing, keeps earlier values and the seen keys (#992)."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        api = self._failed_connections_api(
            mock_api_builder,
            org,
            network,
            [{"ssidNumber": 0, "failureStep": "auth", "ts": "2024-01-01T12:00:00Z"}],
        )
        self._update_all_subcollector_apis(collector, api)
        await self.run_collector(collector)

        labels = {"org_id": org["id"], "network_id": network["id"]}
        fetch = api.wireless.getNetworkWirelessFailedConnections
        sub = collector.ssid_performance_collector
        network_row = {**network, "orgId": org["id"], "orgName": org["name"]}

        # A "not available" 404 and a generic failure both leave the value untouched.
        for error in (Exception("404 Not Found"), Exception("Connection error")):
            fetch.side_effect = error
            try:
                await sub.collect(network_row)
            except Exception:
                pass
            metrics.assert_gauge_value(
                "meraki_mr_ssid_failed_connections_count",
                1,
                ssid="0",
                failure_step="auth",
                **labels,
            )

        # The failures did not consume the stored pair: a later empty success zeroes it.
        fetch.side_effect = None
        fetch.return_value = []
        await sub.collect(network_row)
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count", 0, ssid="0", failure_step="auth", **labels
        )

    async def test_collect_failed_connections_api_error_handled(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """Test that API errors are handled gracefully without crashing."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessBluetoothClients", [])
            .build()
        )
        # Simulate a 404 error for getNetworkWirelessFailedConnections
        api.wireless.getNetworkWirelessFailedConnections = MagicMock(
            side_effect=Exception("404 Not Found")
        )
        self._update_all_subcollector_apis(collector, api)

        await self.run_collector(collector)
        # Collector should still succeed overall despite sub-collector error
        self.assert_collector_success(collector, metrics)

    async def test_collect_failed_connections_missing_fields_handled(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """Test that entries with missing fields default gracefully."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Wireless Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        # Entries with None/missing values (one row per failure event, no `failures` field)
        failed_connections_data = [
            {"ssidNumber": None, "failureStep": None, "ts": "2024-01-01T12:00:00Z"},
            {"ts": "2024-01-01T12:00:05Z"},  # Missing ssidNumber and failureStep entirely
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessBluetoothClients", [])
            .with_custom_response("getNetworkWirelessFailedConnections", failed_connections_data)
            .build()
        )
        api.wireless.getNetworkWirelessFailedConnections = MagicMock(
            return_value=failed_connections_data
        )
        self._update_all_subcollector_apis(collector, api)

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # Should use "unknown" as fallback for missing fields; both rows aggregate to 2
        # (ID-only; org_name/network_name dropped per #534)
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_count",
            2,
            org_id=org["id"],
            network_id=network["id"],
            ssid="unknown",
            failure_step="unknown",
        )

    def test_ssid_performance_collector_instantiated(self, collector) -> None:
        """Test that SSIDPerformanceCollector is instantiated on NetworkHealthCollector."""
        assert hasattr(collector, "ssid_performance_collector")
        assert isinstance(collector.ssid_performance_collector, SSIDPerformanceCollector)

    async def test_non_wireless_networks_do_not_call_ssid_api(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """Test that non-wireless networks skip per-SSID collection."""
        org = OrganizationFactory.create(org_id="org_1", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1",
            name="Switch-Only Network",
            product_types=["switch"],  # Not wireless
            org_id=org["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .build()
        )
        mock_failed = MagicMock(return_value=[])
        api.wireless.getNetworkWirelessFailedConnections = mock_failed
        self._update_all_subcollector_apis(collector, api)

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # getNetworkWirelessFailedConnections should NOT have been called
        mock_failed.assert_not_called()
