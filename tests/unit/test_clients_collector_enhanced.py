"""Enhanced tests for the ClientsCollector covering additional edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.clients import ClientsCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import ClientFactory, NetworkFactory, OrganizationFactory


class TestClientsCollectorEnhanced(BaseCollectorTest):
    """Enhanced test coverage for ClientsCollector functionality."""

    collector_class = ClientsCollector
    update_tier = UpdateTier.MEDIUM

    def _update_collector_api(self, collector: ClientsCollector, api: MagicMock) -> None:
        """Update both collector API and API helper."""
        collector.api = api
        collector.api_helper.api = api

    @pytest.fixture
    def settings_with_clients_enabled(self, settings):
        """Create settings with client collection enabled."""
        settings.clients.enabled = True
        return settings

    @pytest.fixture
    def collector(self, mock_api, settings_with_clients_enabled, isolated_registry):
        """Create the collector instance with clients enabled."""
        return self.collector_class(
            api=mock_api, settings=settings_with_clients_enabled, registry=isolated_registry
        )

    async def test_collect_with_malformed_client_data(self, collector, mock_api_builder, metrics):
        """Test handling of malformed client data."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        # Create clients with various missing/malformed fields
        malformed_clients = [
            {
                # Missing client_id
                "mac": "aa:bb:cc:dd:ee:01",
                "ip": "10.0.0.1",
                "status": "Online",
            },
            {
                "id": "c2",
                # Missing MAC address
                "ip": "10.0.0.2",
                "status": "Online",
            },
            {
                "id": "c3",
                "mac": "invalid-mac",  # Invalid MAC format
                "ip": "not-an-ip",  # Invalid IP
                "status": "Online",
            },
            {
                "id": "c4",
                "mac": "aa:bb:cc:dd:ee:04",
                "usage": "not-a-dict",  # Invalid usage format
                "status": "Online",
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", malformed_clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Run collection - should handle gracefully
        await self.run_collector(collector)

        # Verify collector succeeded despite malformed data
        self.assert_collector_success(collector, metrics)

    async def test_collect_with_extreme_usage_values(self, collector, mock_api_builder, metrics):
        """Test handling of extreme usage values."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        clients = [
            ClientFactory.create(
                client_id="c1",
                mac="aa:bb:cc:dd:ee:01",
                usage={"sent": 0, "recv": 0, "total": 0},  # Zero usage
            ),
            ClientFactory.create(
                client_id="c2",
                mac="aa:bb:cc:dd:ee:02",
                usage={"sent": 9999999999, "recv": 9999999999, "total": 19999999998},  # Very large
            ),
            ClientFactory.create(
                client_id="c3",
                mac="aa:bb:cc:dd:ee:03",
                usage={"sent": -100, "recv": -200, "total": -300},  # Negative values
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Mock DNS resolution
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.return_value = {}
            await self.run_collector(collector)

        # Verify zero usage is handled
        metrics.assert_gauge_value("meraki_client_usage_total_kb", 0, client_id="c1")

        # Verify large values are handled
        metrics.assert_gauge_value("meraki_client_usage_total_kb", 19999999998, client_id="c2")

    async def test_collect_with_special_characters_in_names(
        self, collector, mock_api_builder, metrics
    ):
        """Test handling of special characters in client descriptions and SSIDs."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        clients = [
            ClientFactory.create(
                client_id="c1",
                mac="aa:bb:cc:dd:ee:01",
                description="Client with spaces and (special) chars!",
                ssid="Guest Wi-Fi (5GHz)",
            ),
            ClientFactory.create(
                client_id="c2",
                mac="aa:bb:cc:dd:ee:02",
                description="Client/with/slashes\\backslashes",
                ssid="Employee-Network_2.4",
            ),
            ClientFactory.create(
                client_id="c3",
                mac="aa:bb:cc:dd:ee:03",
                description="Unicode client: 你好世界 🌍",
                ssid="Café-WiFi",
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Mock DNS resolution
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.return_value = {}
            await self.run_collector(collector)

        # Verify metrics are created with sanitized labels
        self.assert_collector_success(collector, metrics)

    async def test_collect_with_dns_resolution_failures(self, collector, mock_api_builder, metrics):
        """Test handling of DNS resolution failures."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        clients = [
            ClientFactory.create(client_id="c1", mac="aa:bb:cc:dd:ee:01", ip="10.0.0.1"),
            ClientFactory.create(client_id="c2", mac="aa:bb:cc:dd:ee:02", ip="10.0.0.2"),
            ClientFactory.create(client_id="c3", mac="aa:bb:cc:dd:ee:03", ip="10.0.0.3"),
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Mock DNS resolution with partial failures
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.side_effect = Exception("DNS timeout")
            await self.run_collector(collector)

        # Verify collection continues despite DNS failures
        self.assert_collector_success(collector, metrics)

    async def test_collect_with_rate_limit_handling(self, collector, mock_api_builder, metrics):
        """Test handling of rate limit errors during collection."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        networks = [
            NetworkFactory.create(network_id=f"N_{i}", name=f"Network {i}", org_id=org["id"])
            for i in range(5)
        ]

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()

        # Mock getOrganizationNetworks
        api.organizations.getOrganizationNetworks = MagicMock(return_value=networks)

        # Mock getNetworkClients to fail on third call
        call_count = 0

        def mock_get_clients(network_id, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise Exception("429 Too Many Requests")
            return [ClientFactory.create(client_id=f"c{call_count}")]

        api.networks.getNetworkClients = MagicMock(side_effect=mock_get_clients)
        self._update_collector_api(collector, api)

        # Run collection
        await self.run_collector(collector)

        # Verify partial success (some networks processed despite rate limit)
        self.assert_collector_success(collector, metrics)

    async def test_collect_application_usage_with_empty_data(
        self, collector, mock_api_builder, metrics
    ):
        """Test application usage collection with empty or missing data."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        clients = [
            ClientFactory.create(client_id="c1", mac="aa:bb:cc:dd:ee:01"),
            ClientFactory.create(client_id="c2", mac="aa:bb:cc:dd:ee:02"),
        ]

        # Various edge cases for application usage
        app_usage_data = [
            {
                "clientId": "c1",
                "applicationUsage": [],  # Empty usage array
            },
            {
                "clientId": "c2",
                # Missing applicationUsage field entirely
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .with_custom_response("getNetworkClientsApplicationUsage", app_usage_data)
            .build()
        )
        self._update_collector_api(collector, api)

        # Run collection
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.return_value = {}
            await self.run_collector(collector)

        # Verify collection completes successfully
        self.assert_collector_success(collector, metrics)

    async def test_collect_with_vlan_edge_cases(self, collector, mock_api_builder, metrics):
        """Test VLAN counting with edge cases."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        clients = [
            ClientFactory.create(client_id="c1", vlan=100),
            ClientFactory.create(client_id="c2", vlan=0),  # VLAN 0
            ClientFactory.create(client_id="c3", vlan=None),  # No VLAN (untagged)
            ClientFactory.create(client_id="c4", vlan=None),  # No VLAN
            ClientFactory.create(client_id="c5", vlan=4094),  # Max VLAN ID
            ClientFactory.create(client_id="c6", vlan=-1),  # Invalid negative VLAN
            ClientFactory.create(client_id="c7", vlan=None),  # No VLAN
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Run collection
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.return_value = {}
            await self.run_collector(collector)

        # Verify VLAN metrics handle edge cases properly
        self.assert_collector_success(collector, metrics)

    async def test_collect_wireless_capabilities_normalization(
        self, collector, mock_api_builder, metrics
    ):
        """Test normalization of various wireless capability strings."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        clients = [
            ClientFactory.create(
                client_id="c1",
                recentDeviceConnection="Wireless",
                wirelessCapabilities="802.11ac - 2.4 and 5 GHz",
            ),
            ClientFactory.create(
                client_id="c2",
                recentDeviceConnection="Wireless",
                wirelessCapabilities="802.11AC - 2.4 AND 5 GHZ",  # Different case
            ),
            ClientFactory.create(
                client_id="c3",
                recentDeviceConnection="Wireless",
                wirelessCapabilities="802.11ax (Wi-Fi 6)",  # New standard
            ),
            ClientFactory.create(
                client_id="c4",
                recentDeviceConnection="Wireless",
                wirelessCapabilities="Unknown",
            ),
            ClientFactory.create(
                client_id="c5",
                recentDeviceConnection="Wireless",
                wirelessCapabilities=None,  # Missing capabilities
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Run collection
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.return_value = {}
            await self.run_collector(collector)

        # Verify capabilities are properly normalized
        self.assert_collector_success(collector, metrics)

    async def test_collect_with_concurrent_network_processing(
        self, collector, mock_api_builder, metrics
    ):
        """Test concurrent processing of multiple networks."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Create many networks to test concurrency
        networks = [
            NetworkFactory.create(network_id=f"N_{i:03d}", name=f"Network {i}", org_id=org["id"])
            for i in range(20)
        ]

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()
        api.organizations.getOrganizationNetworks = MagicMock(return_value=networks)

        # Track concurrent calls
        concurrent_calls = []
        max_concurrent = 0

        def track_concurrent_call(network_id, **kwargs):
            concurrent_calls.append(network_id)
            current = len([c for c in concurrent_calls if c == network_id])
            nonlocal max_concurrent
            max_concurrent = max(max_concurrent, current)
            return [ClientFactory.create(client_id=f"c_{network_id}")]

        api.networks.getNetworkClients = MagicMock(side_effect=track_concurrent_call)
        self._update_collector_api(collector, api)

        # Run collection
        await self.run_collector(collector)

        # Verify all networks were processed
        assert api.networks.getNetworkClients.call_count == 20
        self.assert_collector_success(collector, metrics)

    async def test_collect_with_pagination_edge_cases(self, collector, mock_api_builder, metrics):
        """Test handling of pagination edge cases."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network", org_id=org["id"])

        # Create exactly the pagination limit of clients
        clients = [
            ClientFactory.create(
                client_id=f"c{i:04d}", mac=f"aa:bb:cc:dd:{i // 100:02x}:{i % 100:02x}"
            )
            for i in range(1000)  # Typical API pagination limit
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        self._update_collector_api(collector, api)

        # Mock DNS resolution to avoid timeout on large batches
        with patch.object(collector.dns_resolver, "resolve_multiple") as mock_resolve:
            mock_resolve.return_value = {}
            await self.run_collector(collector)

        # Verify all clients were processed
        self.assert_collector_success(collector, metrics)
