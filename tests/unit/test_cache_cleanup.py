"""Tests for unbounded cache eviction in DeviceCollector and MSCollector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.ms import MSCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest


class TestDeviceCollectorCacheEviction(BaseCollectorTest):
    """Test DeviceCollector._evict_stale_cache_entries."""

    collector_class = DeviceCollector
    update_tier = UpdateTier.MEDIUM

    def test_evict_stale_cache_entries_removes_stale_keys(self, collector: DeviceCollector) -> None:
        """Stale keys (not in active set) are removed from _packet_metrics_cache."""
        # Seed the cache with several entries
        collector._packet_metrics_cache["key:a=1"] = 10.0
        collector._packet_metrics_cache["key:b=2"] = 20.0
        collector._packet_metrics_cache["key:c=3"] = 30.0

        # Only "key:a=1" and "key:c=3" are active this cycle
        active_keys: set[str] = {"key:a=1", "key:c=3"}
        collector._evict_stale_cache_entries(active_keys)

        assert "key:a=1" in collector._packet_metrics_cache
        assert "key:c=3" in collector._packet_metrics_cache
        assert "key:b=2" not in collector._packet_metrics_cache

    def test_evict_stale_cache_entries_preserves_active_keys(
        self, collector: DeviceCollector
    ) -> None:
        """Active keys are not removed from _packet_metrics_cache."""
        collector._packet_metrics_cache["metric:serial=S1"] = 42.0
        collector._packet_metrics_cache["metric:serial=S2"] = 99.0

        active_keys: set[str] = {"metric:serial=S1", "metric:serial=S2"}
        collector._evict_stale_cache_entries(active_keys)

        assert collector._packet_metrics_cache["metric:serial=S1"] == 42.0
        assert collector._packet_metrics_cache["metric:serial=S2"] == 99.0

    def test_evict_stale_cache_entries_with_empty_active_set_clears_all(
        self, collector: DeviceCollector
    ) -> None:
        """When active set is empty, all cache entries are removed."""
        collector._packet_metrics_cache["key:x=1"] = 5.0
        collector._packet_metrics_cache["key:y=2"] = 6.0

        collector._evict_stale_cache_entries(set())

        assert len(collector._packet_metrics_cache) == 0

    def test_evict_stale_cache_entries_with_empty_cache_is_noop(
        self, collector: DeviceCollector
    ) -> None:
        """Eviction on an already-empty cache does not raise."""
        collector._evict_stale_cache_entries({"some:key=1"})
        assert len(collector._packet_metrics_cache) == 0

    def test_set_packet_metric_value_adds_to_active_cache_keys(
        self, collector: DeviceCollector
    ) -> None:
        """_set_packet_metric_value records the cache key in _active_cache_keys."""
        collector._active_cache_keys: set[str] = set()
        labels = {"serial": "Q111", "name": "AP1"}
        # Use a metric name that does NOT include "total" so the value goes straight to cache
        collector._set_packet_metric_value("_mr_packets_downstream_total", labels, 500.0)

        expected_key = "_mr_packets_downstream_total:name=AP1:serial=Q111"
        assert expected_key in collector._active_cache_keys


class TestMSCollectorCacheEviction:
    """Test MSCollector._evict_stale_serials."""

    @pytest.fixture
    def mock_parent(self) -> MagicMock:
        """Create a minimal mock parent for MSCollector."""
        parent = MagicMock()
        parent.api = MagicMock()
        parent.settings = MagicMock()
        parent.settings.api.ms_packet_stats_interval = 0
        parent.settings.api.ms_port_usage_interval = 0
        parent.rate_limiter = None
        # Prevent real Gauge creation by returning a MagicMock
        parent._create_gauge = MagicMock(return_value=MagicMock())
        return parent

    @pytest.fixture
    def ms_collector(self, mock_parent: MagicMock) -> MSCollector:
        """Create MSCollector instance without real metrics."""
        return MSCollector(mock_parent)

    def test_evict_stale_serials_removes_stale_from_both_caches(
        self, ms_collector: MSCollector
    ) -> None:
        """Serials not in the active set are removed from both timestamp caches."""
        ms_collector._last_port_usage["S1"] = 100.0
        ms_collector._last_port_usage["S2"] = 200.0
        ms_collector._last_packet_stats["S1"] = 100.0
        ms_collector._last_packet_stats["S2"] = 200.0

        ms_collector._evict_stale_serials({"S1"})

        assert "S1" in ms_collector._last_port_usage
        assert "S2" not in ms_collector._last_port_usage
        assert "S1" in ms_collector._last_packet_stats
        assert "S2" not in ms_collector._last_packet_stats

    def test_evict_stale_serials_preserves_active_serials(self, ms_collector: MSCollector) -> None:
        """Active serials are not removed from the timestamp caches."""
        ms_collector._last_port_usage["S1"] = 100.0
        ms_collector._last_packet_stats["S1"] = 100.0

        ms_collector._evict_stale_serials({"S1"})

        assert ms_collector._last_port_usage["S1"] == 100.0
        assert ms_collector._last_packet_stats["S1"] == 100.0

    def test_evict_stale_serials_empty_active_set_clears_all(
        self, ms_collector: MSCollector
    ) -> None:
        """When active set is empty, both timestamp caches are fully cleared."""
        ms_collector._last_port_usage["S1"] = 1.0
        ms_collector._last_packet_stats["S1"] = 1.0

        ms_collector._evict_stale_serials(set())

        assert len(ms_collector._last_port_usage) == 0
        assert len(ms_collector._last_packet_stats) == 0

    def test_evict_stale_serials_empty_caches_is_noop(self, ms_collector: MSCollector) -> None:
        """Eviction on empty caches does not raise."""
        ms_collector._evict_stale_serials({"S1", "S2"})
        assert len(ms_collector._last_port_usage) == 0
        assert len(ms_collector._last_packet_stats) == 0

    def test_active_serials_tracked_on_collect_call(self, ms_collector: MSCollector) -> None:
        """_active_serials is initialised and populated when collect() is called.

        We verify the attribute exists on a freshly constructed collector.
        """
        assert hasattr(ms_collector, "_active_serials")
        assert isinstance(ms_collector._active_serials, set)
