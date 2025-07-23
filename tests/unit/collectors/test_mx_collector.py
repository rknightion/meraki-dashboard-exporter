"""Tests for MX (Security Appliance) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.devices.mx import MXCollector

if TYPE_CHECKING:
    pass


class TestMXCollector:
    """Test MX collector functionality."""

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
    def mx_collector(
        self,
        mock_parent: MagicMock,
    ) -> MXCollector:
        """Create MX collector instance."""
        return MXCollector(mock_parent)

    async def test_collect_calls_common_metrics(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test that MX collector calls common metrics collection."""
        # Create a mock device
        device = {
            "serial": "Q123",
            "name": "Test MX",
            "model": "MX100",
            "network_id": "net1",
            "organization_id": "123",
            "status_info": {
                "status": "online",
            },
        }

        # Mock the collect_common_metrics method to verify it's called
        mx_collector.collect_common_metrics = MagicMock()

        # Call collect
        await mx_collector.collect(device)

        # Verify only common metrics were collected
        mx_collector.collect_common_metrics.assert_called_once_with(device)

    def test_mx_collector_initialization(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MX collector initialization."""
        # Verify collector is properly initialized with parent
        assert mx_collector.parent == mock_parent
        assert mx_collector.api == mock_parent.api
        assert mx_collector.settings == mock_parent.settings

    async def test_future_mx_specific_metrics_placeholder(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test placeholder for future MX-specific metrics implementation."""
        # This test documents expected future MX-specific metrics
        # Currently, the MX collector only implements common metrics

        # Future MX-specific metrics might include:
        # - VPN tunnel status and performance
        # - WAN uplink health and utilization
        # - Firewall rule hit counts
        # - Content filtering statistics
        # - Advanced malware protection stats
        # - Site-to-site VPN throughput
        # - Client VPN connections

        # For now, verify the collector exists and can be instantiated
        assert mx_collector is not None
        assert hasattr(mx_collector, "collect")
        assert hasattr(mx_collector, "collect_common_metrics")
