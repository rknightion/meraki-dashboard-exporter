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
        parent.rate_limiter = None
        return parent

    @pytest.fixture
    def mg_collector(
        self,
        mock_parent: MagicMock,
    ) -> MGCollector:
        """Create MG collector instance."""
        return MGCollector(mock_parent)

    async def test_collect_does_not_set_common_metrics(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """Test that MG collector does not redundantly set common metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before collect() is called.
        """
        device = {
            "serial": "Q123",
            "name": "Test MG",
            "model": "MG21",
            "network_id": "net1",
            "organization_id": "123",
        }

        # collect() should complete without touching parent's device_up metric
        await mg_collector.collect(device)
        mg_collector.parent._device_up.labels.assert_not_called()

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
        assert hasattr(mg_collector, "collect")
