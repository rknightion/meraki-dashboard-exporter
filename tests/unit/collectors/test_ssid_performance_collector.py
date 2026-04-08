"""Tests for the SSIDPerformanceCollector."""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.collectors.network_health_collectors.ssid_performance import (
    SSIDPerformanceCollector,
)
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory


class TestSSIDPerformanceCollector(BaseCollectorTest):
    """Tests for SSIDPerformanceCollector via NetworkHealthCollector."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

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

        # API returns one entry per failed client connection
        failed_connections_data = [
            {"ssidNumber": 0, "failureStep": "auth", "failures": 3},
            {"ssidNumber": 0, "failureStep": "auth", "failures": 2},
            {"ssidNumber": 1, "failureStep": "dhcp", "failures": 5},
            {"ssidNumber": 0, "failureStep": "assoc", "failures": 1},
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

        # SSID 0, auth: 3 + 2 = 5
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_total",
            5,
            org_id=org["id"],
            org_name=org["name"],
            network_id=network["id"],
            network_name=network["name"],
            ssid="0",
            failure_step="auth",
        )
        # SSID 1, dhcp: 5
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_total",
            5,
            org_id=org["id"],
            org_name=org["name"],
            network_id=network["id"],
            network_name=network["name"],
            ssid="1",
            failure_step="dhcp",
        )
        # SSID 0, assoc: 1
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_total",
            1,
            org_id=org["id"],
            org_name=org["name"],
            network_id=network["id"],
            network_name=network["name"],
            ssid="0",
            failure_step="assoc",
        )

    async def test_collect_empty_failed_connections(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """Test that empty API response is handled gracefully."""
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
        self.verify_no_metrics_set(metrics, ["meraki_mr_ssid_failed_connections_total"])

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

        # Entries with None/missing values
        failed_connections_data = [
            {"ssidNumber": None, "failureStep": None, "failures": 2},
            {"failures": 1},  # Missing ssidNumber and failureStep entirely
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

        # Should use "unknown" as fallback for missing fields; count aggregated: 2 + 1 = 3
        metrics.assert_gauge_value(
            "meraki_mr_ssid_failed_connections_total",
            3,
            org_id=org["id"],
            org_name=org["name"],
            network_id=network["id"],
            network_name=network["name"],
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
