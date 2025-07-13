"""Tests for the NetworkHealthCollector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    mock = MagicMock()
    mock.organizations = MagicMock()
    mock.networks = MagicMock()
    mock.wireless = MagicMock()
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    settings = Settings()
    return settings


@pytest.fixture
def health_collector(mock_api, mock_settings, monkeypatch):
    """Create a NetworkHealthCollector instance."""
    # Use isolated registry to avoid conflicts
    from prometheus_client import CollectorRegistry

    isolated_registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)
    return NetworkHealthCollector(api=mock_api, settings=mock_settings)


class TestNetworkHealthCollector:
    """Test NetworkHealthCollector functionality."""

    @pytest.mark.asyncio
    async def test_collect_with_no_networks(self, health_collector, mock_api):
        """Test collection when no networks exist."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[])

        # Run collection
        await health_collector.collect()

        # Verify API calls
        mock_api.organizations.getOrganizations.assert_called_once()
        mock_api.organizations.getOrganizationNetworks.assert_called_once_with(
            "123", total_pages="all"
        )

    @pytest.mark.asyncio
    async def test_collect_channel_utilization(self, health_collector, mock_api):
        """Test collection of channel utilization metrics."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Test Network",
                    "productTypes": ["wireless"],
                }
            ]
        )
        mock_api.networks.getNetworkDevices = MagicMock(
            return_value=[
                {"serial": "Q2KD-XXXX", "name": "AP1", "model": "MR36"},
                {"serial": "Q2KD-YYYY", "name": "AP2", "model": "MR46"},
            ]
        )

        channel_util_data = [
            {
                "serial": "Q2KD-XXXX",
                "model": "MR36",
                "wifi0": [  # 2.4GHz
                    {"utilization": 45, "wifi": 30, "non_wifi": 15}
                ],
                "wifi1": [  # 5GHz
                    {"utilization": 25, "wifi": 20, "non_wifi": 5}
                ],
            },
            {
                "serial": "Q2KD-YYYY",
                "model": "MR46",
                "wifi0": [{"utilization": 55, "wifi": 40, "non_wifi": 15}],
                "wifi1": [{"utilization": 35, "wifi": 30, "non_wifi": 5}],
            },
        ]

        mock_api.networks.getNetworkNetworkHealthChannelUtilization = MagicMock(
            return_value=channel_util_data
        )

        # Run collection
        await health_collector.collect()

        # Verify API calls
        mock_api.networks.getNetworkDevices.assert_called_once_with("N_123")
        mock_api.networks.getNetworkNetworkHealthChannelUtilization.assert_called_once_with(
            "N_123", total_pages="all"
        )

    @pytest.mark.asyncio
    async def test_collect_connection_stats(self, health_collector, mock_api):
        """Test collection of wireless connection statistics."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Test Network",
                    "productTypes": ["wireless"],
                }
            ]
        )
        mock_api.networks.getNetworkDevices = MagicMock(return_value=[])
        mock_api.networks.getNetworkNetworkHealthChannelUtilization = MagicMock(return_value=[])

        connection_stats_data = {
            "assoc": 95,
            "auth": 98,
            "dhcp": 92,
            "dns": 99,
            "success": 90,
        }

        mock_api.wireless.getNetworkWirelessConnectionStats = MagicMock(
            return_value=connection_stats_data
        )

        # Run collection
        await health_collector.collect()

        # Verify API calls
        mock_api.wireless.getNetworkWirelessConnectionStats.assert_called_once_with(
            "N_123", timespan=1800
        )

    @pytest.mark.asyncio
    async def test_collect_data_rates(self, health_collector, mock_api):
        """Test collection of wireless data rate metrics."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Test Network",
                    "productTypes": ["wireless"],
                }
            ]
        )
        mock_api.networks.getNetworkDevices = MagicMock(return_value=[])
        mock_api.networks.getNetworkNetworkHealthChannelUtilization = MagicMock(return_value=[])
        mock_api.wireless.getNetworkWirelessConnectionStats = MagicMock(return_value={})

        data_rate_history = [
            {
                "endTs": "2024-01-01T12:00:00Z",
                "downloadKbps": 25000,
                "uploadKbps": 10000,
            },
            {
                "endTs": "2024-01-01T11:55:00Z",
                "downloadKbps": 20000,
                "uploadKbps": 8000,
            },
        ]

        mock_api.wireless.getNetworkWirelessDataRateHistory = MagicMock(
            return_value=data_rate_history
        )

        # Run collection
        await health_collector.collect()

        # Verify API calls
        mock_api.wireless.getNetworkWirelessDataRateHistory.assert_called_once_with(
            "N_123", timespan=300, resolution=300
        )

    @pytest.mark.asyncio
    async def test_collect_handles_empty_channel_util_data(self, health_collector, mock_api):
        """Test handling of empty channel utilization data."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Test Network",
                    "productTypes": ["wireless"],
                }
            ]
        )
        mock_api.networks.getNetworkDevices = MagicMock(return_value=[])

        # Return empty channel utilization
        mock_api.networks.getNetworkNetworkHealthChannelUtilization = MagicMock(return_value=[])
        mock_api.wireless.getNetworkWirelessConnectionStats = MagicMock(return_value={})
        mock_api.wireless.getNetworkWirelessDataRateHistory = MagicMock(return_value=[])

        # Run collection - should handle gracefully
        await health_collector.collect()

    @pytest.mark.asyncio
    async def test_collect_handles_api_errors(self, health_collector, mock_api):
        """Test handling of API errors."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Test Network",
                    "productTypes": ["wireless"],
                }
            ]
        )
        mock_api.networks.getNetworkDevices = MagicMock(return_value=[])

        # Mock API errors
        mock_api.networks.getNetworkNetworkHealthChannelUtilization = MagicMock(
            side_effect=Exception("400 Bad Request")
        )
        mock_api.wireless.getNetworkWirelessConnectionStats = MagicMock(
            side_effect=Exception("404 Not Found")
        )
        mock_api.wireless.getNetworkWirelessDataRateHistory = MagicMock(
            side_effect=Exception("Network error")
        )

        # Run collection - should handle errors gracefully
        await health_collector.collect()

    @pytest.mark.asyncio
    async def test_collect_handles_timeout(self, health_collector, mock_api):
        """Test handling of timeout errors."""
        import asyncio

        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Test Network",
                    "productTypes": ["wireless"],
                }
            ]
        )
        mock_api.networks.getNetworkDevices = MagicMock(return_value=[])

        # Mock timeout
        async def slow_call(*args, **kwargs):
            await asyncio.sleep(60)  # Longer than timeout

        mock_api.networks.getNetworkNetworkHealthChannelUtilization = slow_call
        mock_api.wireless.getNetworkWirelessConnectionStats = MagicMock(return_value={})
        mock_api.wireless.getNetworkWirelessDataRateHistory = MagicMock(return_value=[])

        # Run collection - should handle timeout gracefully
        await health_collector.collect()

    @pytest.mark.asyncio
    async def test_collect_non_wireless_networks_skipped(self, health_collector, mock_api):
        """Test that non-wireless networks are skipped."""
        # Mock API responses
        mock_api.organizations.getOrganizations = MagicMock(
            return_value=[{"id": "123", "name": "Test Org"}]
        )
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            return_value=[
                {
                    "id": "N_123",
                    "name": "Switch Network",
                    "productTypes": ["switch"],  # Not wireless
                },
                {
                    "id": "N_456",
                    "name": "Camera Network",
                    "productTypes": ["camera"],  # Not wireless
                },
            ]
        )

        # Run collection
        await health_collector.collect()

        # Should not call wireless-specific APIs
        mock_api.networks.getNetworkNetworkHealthChannelUtilization.assert_not_called()
        mock_api.wireless.getNetworkWirelessConnectionStats.assert_not_called()
        mock_api.wireless.getNetworkWirelessDataRateHistory.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_metric_value_handles_none(self, health_collector):
        """Test that None values are handled properly."""
        # This tests the _set_metric_value method directly
        labels = {"network_id": "N_123", "network_name": "Test"}

        # Should skip None values without error
        health_collector._set_metric_value("_network_utilization_2_4ghz", labels, None)

    def test_update_tier(self, health_collector):
        """Test that network health collector has correct update tier."""
        from meraki_dashboard_exporter.core.constants import UpdateTier

        assert health_collector.update_tier == UpdateTier.MEDIUM
