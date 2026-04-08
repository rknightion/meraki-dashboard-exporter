"""Integration tests for metric expiration / TTL-based cleanup.

Tests verify that MetricExpirationManager correctly:
- Expires metric tracking entries after their TTL has elapsed
- Retains tracking entries before the TTL expires
- Accurately maintains hit/miss accounting
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> MagicMock:
    """Minimal mock Settings for MetricExpirationManager."""
    settings = MagicMock()
    settings.monitoring.metric_ttl_multiplier = 2.0
    # MEDIUM tier: 300 s * 2.0 = 600 s TTL (default used by cleanup logic)
    settings.update_intervals.fast = 60
    settings.update_intervals.medium = 300
    settings.update_intervals.slow = 900
    return settings


@pytest.fixture
def expiration_manager(mock_settings: MagicMock) -> MetricExpirationManager:
    """MetricExpirationManager instance (background loop not started)."""
    return MetricExpirationManager(settings=mock_settings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLLECTOR = "TestCollector"
_METRIC = "meraki_test_metric"
_LABELS = {"org_id": "org_123", "serial": "Q2KD-XXXX"}


def _track(manager: MetricExpirationManager, **label_overrides: str) -> None:
    labels = {**_LABELS, **label_overrides}
    manager.track_metric_update(
        collector_name=_COLLECTOR,
        metric_name=_METRIC,
        label_values=labels,
    )


# ---------------------------------------------------------------------------
# Tests: basic tracking
# ---------------------------------------------------------------------------


class TestMetricTracking:
    """Basic track_metric_update bookkeeping."""

    def test_track_records_new_entry(self, expiration_manager: MetricExpirationManager) -> None:
        """A fresh metric entry should appear in the timestamp map."""
        assert len(expiration_manager._metric_timestamps) == 0

        _track(expiration_manager)

        assert len(expiration_manager._metric_timestamps) == 1
        assert expiration_manager._metric_counts[_COLLECTOR] == 1

    def test_track_updates_existing_entry(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Tracking the same metric twice must not duplicate the counter."""
        _track(expiration_manager)
        _track(expiration_manager)  # same labels

        assert len(expiration_manager._metric_timestamps) == 1
        # Count still 1 — second call updates timestamp, does not add a new entry
        assert expiration_manager._metric_counts[_COLLECTOR] == 1

    def test_different_label_sets_tracked_separately(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Each unique label combination is a distinct tracking entry."""
        _track(expiration_manager, serial="SERIAL-1")
        _track(expiration_manager, serial="SERIAL-2")
        _track(expiration_manager, serial="SERIAL-3")

        assert len(expiration_manager._metric_timestamps) == 3
        assert expiration_manager._metric_counts[_COLLECTOR] == 3

    def test_get_stats_reflects_tracked_entries(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """get_stats() must report accurate totals."""
        _track(expiration_manager, serial="S1")
        _track(expiration_manager, serial="S2")

        stats = expiration_manager.get_stats()
        assert stats["total_tracked"] == 2
        assert stats["by_collector"][_COLLECTOR] == 2
        assert stats["ttl_multiplier"] == 2.0


# ---------------------------------------------------------------------------
# Tests: expiry after TTL
# ---------------------------------------------------------------------------


class TestMetricExpiresAfterTTL:
    """Metrics must be removed from tracking once their TTL elapses."""

    async def test_metric_expires_after_ttl(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """After cleaning up with current_time well past TTL, entry is removed."""
        base_time = 1_000_000.0
        # MEDIUM TTL = 300 * 2.0 = 600 s
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            _track(expiration_manager)

        # Advance time beyond TTL
        future_time = base_time + medium_ttl + 1.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = future_time
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 0
        assert expiration_manager._metric_counts[_COLLECTOR] == 0

    async def test_multiple_metrics_all_expire(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """All stale entries across multiple series should be removed in one cleanup."""
        base_time = 2_000_000.0
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            for i in range(5):
                _track(expiration_manager, serial=f"SERIAL-{i}")

        assert expiration_manager._metric_counts[_COLLECTOR] == 5

        future_time = base_time + medium_ttl + 1.0
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = future_time
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 0
        assert expiration_manager._metric_counts[_COLLECTOR] == 0

    async def test_only_stale_metrics_are_expired(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Fresh metrics must survive; only stale ones should be removed."""
        base_time = 3_000_000.0
        medium_ttl = 600.0

        # Track an entry at base_time (will become stale)
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            _track(expiration_manager, serial="STALE-SERIAL")

        # Track a fresh entry just before cleanup runs (within TTL)
        fresh_time = base_time + medium_ttl - 10.0  # 10 s before TTL boundary
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = fresh_time
            _track(expiration_manager, serial="FRESH-SERIAL")

        # Cleanup runs at base_time + TTL + 1 — stale entry expired, fresh one not yet
        cleanup_time = base_time + medium_ttl + 1.0
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = cleanup_time
            await expiration_manager._cleanup_expired_metrics()

        remaining = list(expiration_manager._metric_timestamps.keys())
        remaining_labels = [key[2] for key in remaining]

        assert any("FRESH-SERIAL" in label for label in remaining_labels), (
            "Fresh metric should still be tracked"
        )
        assert not any("STALE-SERIAL" in label for label in remaining_labels), (
            "Stale metric should have been removed"
        )
        assert expiration_manager._metric_counts[_COLLECTOR] == 1


# ---------------------------------------------------------------------------
# Tests: metric NOT expired before TTL
# ---------------------------------------------------------------------------


class TestMetricNotExpiredBeforeTTL:
    """Metrics within their TTL window must not be removed."""

    async def test_metric_not_expired_before_ttl(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Entry must still exist when cleanup runs before TTL has elapsed."""
        base_time = 4_000_000.0
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            _track(expiration_manager)

        # Cleanup at exactly TTL boundary minus 1 second — should NOT expire
        early_cleanup_time = base_time + medium_ttl - 1.0
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = early_cleanup_time
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 1
        assert expiration_manager._metric_counts[_COLLECTOR] == 1

    async def test_metric_not_expired_immediately_after_tracking(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """A metric tracked and cleaned up at the same time must not be expired."""
        now = 5_000_000.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = now
            _track(expiration_manager)
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 1

    async def test_re_tracked_metric_resets_ttl(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Re-tracking before TTL expiry should extend the effective TTL."""
        base_time = 6_000_000.0
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            _track(expiration_manager)

        # Re-track at just before the original TTL — timestamp is refreshed
        refresh_time = base_time + medium_ttl - 10.0
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = refresh_time
            _track(expiration_manager)  # same labels

        # Run cleanup at the time that would have expired the original entry
        would_have_expired = base_time + medium_ttl + 1.0
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = would_have_expired
            await expiration_manager._cleanup_expired_metrics()

        # Entry should still be alive because its timestamp was refreshed
        assert len(expiration_manager._metric_timestamps) == 1, (
            "Re-tracked metric should not have been expired"
        )


# ---------------------------------------------------------------------------
# Tests: TTL calculation per tier
# ---------------------------------------------------------------------------


class TestTTLCalculation:
    """Verify _get_ttl_for_tier returns interval * multiplier."""

    def test_fast_tier_ttl(self, expiration_manager: MetricExpirationManager) -> None:
        """FAST TTL is fast_interval * multiplier (60 * 2.0 = 120 s)."""
        ttl = expiration_manager._get_ttl_for_tier(UpdateTier.FAST)
        assert ttl == 120.0

    def test_medium_tier_ttl(self, expiration_manager: MetricExpirationManager) -> None:
        """MEDIUM TTL is medium_interval * multiplier (300 * 2.0 = 600 s)."""
        ttl = expiration_manager._get_ttl_for_tier(UpdateTier.MEDIUM)
        assert ttl == 600.0

    def test_slow_tier_ttl(self, expiration_manager: MetricExpirationManager) -> None:
        """SLOW TTL is slow_interval * multiplier (900 * 2.0 = 1800 s)."""
        ttl = expiration_manager._get_ttl_for_tier(UpdateTier.SLOW)
        assert ttl == 1800.0


# ---------------------------------------------------------------------------
# Tests: background task lifecycle
# ---------------------------------------------------------------------------


class TestExpirationManagerLifecycle:
    """start/stop the background cleanup task cleanly."""

    async def test_start_and_stop(self, expiration_manager: MetricExpirationManager) -> None:
        """Manager must start and stop without errors."""
        await expiration_manager.start()
        assert expiration_manager._running is True
        assert expiration_manager._cleanup_task is not None

        await expiration_manager.stop()
        assert expiration_manager._running is False

    async def test_double_start_is_safe(self, expiration_manager: MetricExpirationManager) -> None:
        """Calling start() twice must not create a second background task."""
        await expiration_manager.start()
        first_task = expiration_manager._cleanup_task

        await expiration_manager.start()
        assert expiration_manager._cleanup_task is first_task

        await expiration_manager.stop()

    async def test_stop_before_start_is_safe(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Calling stop() when never started must not raise."""
        await expiration_manager.stop()  # Should be a no-op
        assert expiration_manager._running is False
