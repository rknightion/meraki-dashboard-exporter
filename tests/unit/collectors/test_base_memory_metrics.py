"""Tests for BaseDeviceCollector.collect_memory_metrics pagination (F-007, #548).

The org-wide ``getOrganizationDevicesSystemMemoryUsageHistoryByInterval`` fetch
must pass ``total_pages="all"`` — otherwise the SDK's default ``perPage`` (10)
silently truncates memory metrics to the first 10 devices per organization.

It must also request ``perPage=20`` — the documented endpoint maximum (spec:
"Acceptable range is 3 - 20. Default is 10.") — so each page carries as many
devices as possible, minimizing the number of pages fetched per cycle (#548).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mg import MGCollector


class TestCollectMemoryMetricsPagination:
    """Verify the org-wide memory-history fetch pages through every device."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock API whose memory-history call returns an empty list."""
        api = MagicMock()
        api.organizations = MagicMock()
        # SDK call returns an empty list — we only assert how it is invoked.
        api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval = MagicMock(
            return_value=[]
        )
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Mock parent DeviceCollector wiring the API + a gauge factory."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None  # no NetworkFilter resolution

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    async def test_memory_fetch_requests_all_pages(self, mock_parent: MagicMock) -> None:
        """The memory-history fetch must page through every device, not just 10."""
        collector = MGCollector(mock_parent)

        await collector.collect_memory_metrics("org-1", "Org One")

        fetch = (
            mock_parent.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval
        )
        fetch.assert_called_once()
        _, kwargs = fetch.call_args
        assert kwargs.get("total_pages") == "all", (
            "memory fetch must pass total_pages='all' to avoid the default perPage=10 truncation"
        )
        assert kwargs.get("perPage") == 20, (
            "memory fetch must request perPage=20 (the endpoint maximum) to minimize "
            "page count per cycle (#548)"
        )
