"""Tests for the device collector using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, NetworkFactory, OrganizationFactory


class TestDeviceCollector(BaseCollectorTest):
    """Test DeviceCollector functionality."""

    collector_class = DeviceCollector
    update_tier = UpdateTier.MEDIUM

    def test_packet_metric_value_retention(self, collector):
        """Test that packet metrics retain last known values."""
        labels = {
            "serial": "Q2KD-XXXX",
            "name": "AP1",
            "network_id": "N_123",
            "network_name": "Test Network",
        }

        # Set initial value for total packet metric
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            1000,
        )

        # Verify value was cached
        cache_key = "_mr_packets_downstream_total:name=AP1:network_id=N_123:network_name=Test Network:serial=Q2KD-XXXX"
        assert cache_key in collector._packet_metrics_cache
        assert collector._packet_metrics_cache[cache_key] == 1000

        # Try to set value to 0 (should use cached value)
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            0,
        )

        # Value should still be cached as 1000
        assert collector._packet_metrics_cache[cache_key] == 1000

        # Try to set value to None (should use cached value)
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            None,
        )

        # Value should still be cached as 1000
        assert collector._packet_metrics_cache[cache_key] == 1000

        # Set a new valid value
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            2000,
        )

        # Cache should be updated
        assert collector._packet_metrics_cache[cache_key] == 2000

    def test_packet_loss_metric_allows_zero(self, collector):
        """Test that packet loss metrics allow 0 as a valid value."""
        labels = {
            "serial": "Q2KD-XXXX",
            "name": "AP1",
            "network_id": "N_123",
            "network_name": "Test Network",
        }

        # Set initial value for lost packets
        collector._set_packet_metric_value(
            "_mr_packets_downstream_lost",
            labels,
            10,
        )

        # Setting to 0 should be allowed for "lost" metrics
        collector._set_packet_metric_value(
            "_mr_packets_downstream_lost",
            labels,
            0,
        )

        # Cache should be updated to 0
        cache_key = "_mr_packets_downstream_lost:name=AP1:network_id=N_123:network_name=Test Network:serial=Q2KD-XXXX"
        assert collector._packet_metrics_cache[cache_key] == 0

    async def test_ssid_status_collection(self, collector, mock_api_builder, metrics):
        """Test SSID status metric collection."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Create SSID status response
        ssid_status_response = [
            {
                "serial": "Q2KD-XXXX",
                "name": "AP1",
                "network": {
                    "id": network["id"],
                    "name": network["name"],
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

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()

        # Manually configure this method because it uses asyncio.to_thread
        # and the mock builder has trouble with wireless organization methods
        api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=ssid_status_response
        )

        collector.api = api
        # Also update the MR collector's API reference since it was initialized with the old API
        collector.mr_collector.api = api

        # Collect SSID status
        await collector.mr_collector.collect_ssid_status(org["id"])

        # Verify API was called correctly
        api.wireless.getOrganizationWirelessSsidsStatusesByDevice.assert_called_once_with(
            org["id"],
            perPage=500,
            total_pages="all",
        )

    async def test_device_name_lookup(self, collector, mock_api_builder, metrics):
        """Test that device names are correctly looked up from cache."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123")
        devices = [
            DeviceFactory.create_mr(
                serial="Q2KD-XXXX",
                name="Office AP",
                model="MR36",
                network_id=network["id"],
            ),
            DeviceFactory.create_ms(
                serial="Q2SW-XXXX",
                name="Main Switch",
                model="MS120",
                network_id=network["id"],
            ),
        ]

        # Create client overview response
        client_overview_response = [
            {
                "serial": "Q2KD-XXXX",
                "network": {"id": network["id"]},
                "counts": {"byStatus": {"online": 5}},
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_devices(devices, org_id=org["id"])
            .with_device_statuses([], org_id=org["id"])
            .with_custom_response(
                "getOrganizationWirelessClientsOverviewByDevice", client_overview_response
            )
            .build()
        )
        collector.api = api
        # Update MR collector's API reference
        collector.mr_collector.api = api

        # Collect devices to populate lookup
        await collector._collect_org_devices(org["id"])

        # Verify device lookup was populated
        assert "Q2KD-XXXX" in collector._device_lookup
        assert collector._device_lookup["Q2KD-XXXX"]["name"] == "Office AP"
        assert collector._device_lookup["Q2KD-XXXX"]["model"] == "MR36"

        # Collect wireless clients
        await collector.mr_collector.collect_wireless_clients(org["id"], collector._device_lookup)

        # Verify API was called
        api.wireless.getOrganizationWirelessClientsOverviewByDevice.assert_called()

    def test_get_device_type(self, collector):
        """Test device type extraction from model."""
        assert collector._get_device_type({"model": "MR36"}) == "MR"
        assert collector._get_device_type({"model": "MS120-8"}) == "MS"
        assert collector._get_device_type({"model": "MT10"}) == "MT"
        assert collector._get_device_type({"model": "MX64"}) == "MX"
        assert collector._get_device_type({"model": "Z"}) == "Unknown"
        assert collector._get_device_type({}) == "Unknown"

    async def test_ssid_status_with_duplicate_radios(self, collector, mock_api_builder, metrics):
        """Test that SSID status handles duplicate radios correctly."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Create SSID status response with multiple SSIDs on same radio
        ssid_status_response = [
            {
                "serial": "Q2KD-XXXX",
                "name": "AP1",
                "network": {
                    "id": network["id"],
                    "name": network["name"],
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

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()

        # Manually configure wireless method
        api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=ssid_status_response
        )

        collector.api = api
        collector.mr_collector.api = api

        # Collect SSID status
        await collector.mr_collector.collect_ssid_status(org["id"])

        # The collector should only process each radio once
        # This test verifies the method completes without duplicate processing

    async def test_device_collection_basic(self, collector, mock_api_builder, metrics):
        """Test basic device collection functionality."""
        # Set up standard test data
        test_data = self.setup_standard_test_data(mock_api_builder)
        collector.api = mock_api_builder.build()

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Verify API calls were tracked
        self.assert_api_call_tracked(collector, metrics, "getOrganizationDevices", count=1)
