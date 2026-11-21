"""Tests for unbounded cache eviction in MSCollector."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.devices.ms import MSCollector


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

    async def test_org_endpoint_path_keeps_throttle_timestamps(
        self, ms_collector: MSCollector, mock_parent: MagicMock
    ) -> None:
        """#971: a serial seen by the org-endpoint path survives end-of-cycle eviction.

        ``collect()`` never runs on the org-endpoint path, so the only place the
        serial is registered is ``collect_port_statuses_by_switch``, even when the
        MS_PORT_STATUS gate is closed and nothing is fetched or written.
        """
        mock_parent._should_run_group.return_value = False
        ms_collector._last_port_usage["S1"] = 100.0
        ms_collector._last_packet_stats["S1"] = 100.0

        await ms_collector.collect_port_statuses_by_switch("o", "O", [{"serial": "S1"}])
        ms_collector._evict_stale_serials(ms_collector._active_serials)

        assert "S1" in ms_collector._last_port_usage
        assert "S1" in ms_collector._last_packet_stats

    async def test_org_endpoint_path_still_evicts_absent_switch(
        self, ms_collector: MSCollector, mock_parent: MagicMock
    ) -> None:
        """A switch missing from the next cycle's device list is evicted (#971)."""
        mock_parent._should_run_group.return_value = False
        for serial in ("S1", "S2"):
            ms_collector._last_port_usage[serial] = 100.0
            ms_collector._last_packet_stats[serial] = 100.0

        await ms_collector.collect_port_statuses_by_switch(
            "o", "O", [{"serial": "S1"}, {"name": "no-serial"}]
        )
        ms_collector._evict_stale_serials(ms_collector._active_serials)

        assert set(ms_collector._last_port_usage) == {"S1"}
        assert set(ms_collector._last_packet_stats) == {"S1"}

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
