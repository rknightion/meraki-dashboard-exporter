"""Tests for MV (Security Camera) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.devices.mv import MVCollector

if TYPE_CHECKING:
    pass


class TestMVCollector:
    """Test MV collector functionality."""

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
    def mv_collector(
        self,
        mock_parent: MagicMock,
    ) -> MVCollector:
        """Create MV collector instance."""
        return MVCollector(mock_parent)

    async def test_collect_calls_common_metrics(
        self,
        mv_collector: MVCollector,
    ) -> None:
        """Test that MV collector calls common metrics collection."""
        # Create a mock device
        device = {
            "serial": "Q123",
            "name": "Test Camera",
            "model": "MV12",
            "network_id": "net1",
            "organization_id": "123",
            "status_info": {
                "status": "online",
            },
        }

        # Mock the collect_common_metrics method to verify it's called
        mv_collector.collect_common_metrics = MagicMock()

        # Call collect
        await mv_collector.collect(device)

        # Verify only common metrics were collected
        mv_collector.collect_common_metrics.assert_called_once_with(device)

    def test_mv_collector_initialization(
        self,
        mv_collector: MVCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MV collector initialization."""
        # Verify collector is properly initialized with parent
        assert mv_collector.parent == mock_parent
        assert mv_collector.api == mock_parent.api
        assert mv_collector.settings == mock_parent.settings

    async def test_future_mv_specific_metrics_placeholder(
        self,
        mv_collector: MVCollector,
    ) -> None:
        """Test placeholder for future MV-specific metrics implementation."""
        # This test documents expected future MV-specific metrics
        # Currently, the MV collector only implements common metrics

        # Future MV-specific metrics might include:
        # - Video quality metrics (resolution, bitrate, frame rate)
        # - Storage usage (local and cloud)
        # - Recording status
        # - Motion detection events count
        # - Analytics data (people counting, heat maps)
        # - Camera health (lens obstruction, tampering)
        # - Network bandwidth usage
        # - Retention days remaining
        # - Snapshot API usage
        # - RTSP stream connections

        # For now, verify the collector exists and can be instantiated
        assert mv_collector is not None
        assert hasattr(mv_collector, "collect")
        assert hasattr(mv_collector, "collect_common_metrics")
