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
        }

        # Mock port statuses response
        mock_api.switch.getDeviceSwitchPortsStatuses = MagicMock(
            return_value=[
                {
                    "portId": "1",
                    "name": "Uplink Port",
                    "status": "Connected",
                }
            ]
        )

        # Run collection
        await ms_collector.collect(device)

        # Verify API call was made
        mock_api.switch.getDeviceSwitchPortsStatuses.assert_called_once_with("Q123-456-789")

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
