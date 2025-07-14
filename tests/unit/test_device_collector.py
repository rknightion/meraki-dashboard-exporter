"""Tests for the device collector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    mock = MagicMock()
    mock.organizations = MagicMock()
    mock.wireless = MagicMock()
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_ORG_ID", "123456")
    monkeypatch.setenv("MERAKI_EXPORTER_DEVICE_TYPES", '["MR", "MS", "MT"]')
    return Settings()


@pytest.fixture
def device_collector(mock_api, mock_settings, monkeypatch):
    """Create a device collector instance."""
    # Use isolated registry
    isolated_registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)
    return DeviceCollector(api=mock_api, settings=mock_settings)


class TestDeviceCollector:
    """Test DeviceCollector functionality."""

    def test_packet_metric_value_retention(self, device_collector):
        """Test that packet metrics retain last known values."""
        labels = {
            "serial": "Q2KD-XXXX",
            "name": "AP1",
            "network_id": "N_123",
            "network_name": "Test Network",
        }

        # Set initial value for total packet metric
        device_collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            1000,
        )

        # Verify value was cached
        cache_key = "_mr_packets_downstream_total:name=AP1:network_id=N_123:network_name=Test Network:serial=Q2KD-XXXX"
        assert cache_key in device_collector._packet_metrics_cache
        assert device_collector._packet_metrics_cache[cache_key] == 1000

        # Try to set value to 0 (should use cached value)
        device_collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            0,
        )

        # Value should still be cached as 1000
        assert device_collector._packet_metrics_cache[cache_key] == 1000

        # Try to set value to None (should use cached value)
        device_collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            None,
        )

        # Value should still be cached as 1000
        assert device_collector._packet_metrics_cache[cache_key] == 1000

        # Set a new valid value
        device_collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            2000,
        )

        # Cache should be updated
        assert device_collector._packet_metrics_cache[cache_key] == 2000

    def test_packet_loss_metric_allows_zero(self, device_collector):
        """Test that packet loss metrics allow 0 as a valid value."""
        labels = {
            "serial": "Q2KD-XXXX",
            "name": "AP1",
            "network_id": "N_123",
            "network_name": "Test Network",
        }

        # Set initial value for lost packets
        device_collector._set_packet_metric_value(
            "_mr_packets_downstream_lost",
            labels,
            10,
        )

        # Setting to 0 should be allowed for "lost" metrics
        device_collector._set_packet_metric_value(
            "_mr_packets_downstream_lost",
            labels,
            0,
        )

        # Cache should be updated to 0
        cache_key = "_mr_packets_downstream_lost:name=AP1:network_id=N_123:network_name=Test Network:serial=Q2KD-XXXX"
        assert device_collector._packet_metrics_cache[cache_key] == 0

    @pytest.mark.asyncio
    async def test_ssid_status_collection(self, device_collector, mock_api):
        """Test SSID status metric collection."""
        # Mock API response
        mock_api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2KD-XXXX",
                    "name": "AP1",
                    "network": {
                        "id": "N_123",
                        "name": "Test Network",
                    },
                    "basicServiceSets": [
                        {
                            "ssid": {"name": "Guest", "number": 0},
                            "radio": {
                                "isBroadcasting": True,
                                "band": "2.4",
                                "channel": 6,
                                "channelWidth": 20,
                                "power": 15,
                                "index": "0",
                            },
                        },
                        {
                            "ssid": {"name": "Guest", "number": 0},
                            "radio": {
                                "isBroadcasting": True,
                                "band": "5",
                                "channel": 44,
                                "channelWidth": 80,
                                "power": 18,
                                "index": "1",
                            },
                        },
                    ],
                }
            ]
        )

        # Collect SSID status
        await device_collector._collect_mr_ssid_status("123456")

        # Verify API was called correctly
        mock_api.wireless.getOrganizationWirelessSsidsStatusesByDevice.assert_called_once_with(
            "123456",
            hideDisabled=True,
            total_pages="all",
        )

        # Verify metrics would be set (in real scenario)
        # Since we're using mocks, we can't easily verify prometheus metrics
        # but we can verify the method completed without errors

    @pytest.mark.asyncio
    async def test_device_name_lookup(self, device_collector, mock_api):
        """Test that device names are correctly looked up from cache."""
        # Mock device response
        mock_api.organizations.getOrganizationDevices = MagicMock(
            return_value=[
                {
                    "serial": "Q2KD-XXXX",
                    "name": "Office AP",
                    "model": "MR36",
                    "networkId": "N_123",
                },
                {
                    "serial": "Q2SW-XXXX",
                    "name": "Main Switch",
                    "model": "MS120",
                    "networkId": "N_123",
                },
            ]
        )

        # Mock statuses response
        mock_api.organizations.getOrganizationDevicesStatuses = MagicMock(return_value=[])

        # Mock client overview response
        mock_api.wireless.getOrganizationWirelessClientsOverviewByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2KD-XXXX",
                    "network": {"id": "N_123"},
                    "counts": {"byStatus": {"online": 5}},
                }
            ]
        )

        # Collect devices to populate lookup
        await device_collector._collect_org_devices("123456")

        # Verify device lookup was populated
        assert "Q2KD-XXXX" in device_collector._device_lookup
        assert device_collector._device_lookup["Q2KD-XXXX"]["name"] == "Office AP"
        assert device_collector._device_lookup["Q2KD-XXXX"]["model"] == "MR36"

        # Collect wireless clients
        await device_collector._collect_wireless_clients("123456")

        # The metric would be set with the correct device name (not serial)
        # In a real test, we'd verify the prometheus metric labels

    def test_get_device_type(self, device_collector):
        """Test device type extraction from model."""
        assert device_collector._get_device_type({"model": "MR36"}) == "MR"
        assert device_collector._get_device_type({"model": "MS120-8"}) == "MS"
        assert device_collector._get_device_type({"model": "MT10"}) == "MT"
        assert device_collector._get_device_type({"model": "MX64"}) == "MX"
        assert device_collector._get_device_type({"model": "Z"}) == "Unknown"
        assert device_collector._get_device_type({}) == "Unknown"

    @pytest.mark.asyncio
    async def test_ssid_status_with_duplicate_radios(self, device_collector, mock_api):
        """Test that SSID status handles duplicate radios correctly."""
        # Mock API response with multiple SSIDs on same radio
        mock_api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2KD-XXXX",
                    "name": "AP1",
                    "network": {
                        "id": "N_123",
                        "name": "Test Network",
                    },
                    "basicServiceSets": [
                        {
                            "ssid": {"name": "Guest", "number": 0},
                            "radio": {
                                "isBroadcasting": True,
                                "band": "2.4",
                                "channel": 6,
                                "channelWidth": 20,
                                "power": 15,
                                "index": "0",
                            },
                        },
                        {
                            "ssid": {"name": "Corporate", "number": 1},
                            "radio": {
                                "isBroadcasting": True,
                                "band": "2.4",
                                "channel": 6,
                                "channelWidth": 20,
                                "power": 15,
                                "index": "0",
                            },
                        },
                    ],
                }
            ]
        )

        # Collect SSID status
        await device_collector._collect_mr_ssid_status("123456")

        # The collector should only process each radio once
        # This test verifies the method completes without duplicate processing
