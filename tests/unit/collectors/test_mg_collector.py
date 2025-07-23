"""Tests for MG (Cellular Gateway) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.devices.mg import MGCollector

if TYPE_CHECKING:
    pass


class TestMGCollector:
    """Test MG collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        return MagicMock()

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        return parent

    @pytest.fixture
    def mg_collector(
        self,
        mock_parent: MagicMock,
    ) -> MGCollector:
        """Create MG collector instance."""
        return MGCollector(mock_parent)

    async def test_collect_calls_common_metrics(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """Test that MG collector calls common metrics collection."""
        # Create a mock device
        device = {
            "serial": "Q123",
            "name": "Test MG",
            "model": "MG21",
            "network_id": "net1",
            "organization_id": "123",
            "status_info": {
                "status": "online",
            },
        }

        # Mock the collect_common_metrics method to verify it's called
        mg_collector.collect_common_metrics = MagicMock()

        # Call collect
        await mg_collector.collect(device)

        # Verify only common metrics were collected
        mg_collector.collect_common_metrics.assert_called_once_with(device)

    def test_mg_collector_initialization(
        self,
        mg_collector: MGCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MG collector initialization."""
        # Verify collector is properly initialized with parent
        assert mg_collector.parent == mock_parent
        assert mg_collector.api == mock_parent.api
        assert mg_collector.settings == mock_parent.settings

    async def test_future_mg_specific_metrics_placeholder(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """Test placeholder for future MG-specific metrics implementation."""
        # This test documents expected future MG-specific metrics
        # Currently, the MG collector only implements common metrics

        # Future MG-specific metrics might include:
        # - Cellular signal strength (RSSI, RSRP, RSRQ)
        # - Cellular carrier information
        # - Data usage (current month, daily, hourly)
        # - Connection uptime
        # - Failover status (primary/backup)
        # - SIM card status
        # - Network type (4G, 5G, etc.)
        # - Roaming status
        # - Data plan limits and usage percentage

        # For now, verify the collector exists and can be instantiated
        assert mg_collector is not None
        assert hasattr(mg_collector, "collect")
        assert hasattr(mg_collector, "collect_common_metrics")
