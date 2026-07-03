"""Integration tests for metric expiration / TTL-based cleanup.

Tests verify that MetricExpirationManager correctly:
- Expires metric tracking entries after their TTL has elapsed
- Retains tracking entries before the TTL expires
- Accurately maintains hit/miss accounting
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> MagicMock:
    """Minimal mock Settings for MetricExpirationManager."""
    settings = MagicMock()
    settings.monitoring.metric_ttl_multiplier = 2.0
    settings.monitoring.max_cardinality_per_collector = 10000
    # Tiers are gone (#631): the fallback TTL is now
    # scheduler.resolve_interval_seconds * metric_ttl_multiplier. 300 * 2.0 = 600s,
    # matching the default TTL these tests assert against.
    settings.scheduler.resolve_interval_seconds = 300
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
# Tests: per-series ttl_seconds override (#617 §1f / #541 flap fix)
# ---------------------------------------------------------------------------


class TestPerSeriesTTLOverride:
    """A per-series ttl_seconds overrides the cadence-derived fallback TTL (#617 §1f)."""

    def _track_with_ttl(
        self,
        manager: MetricExpirationManager,
        *,
        ttl_seconds: float | None,
        serial: str = "Q2KD-XXXX",
    ) -> None:
        manager.track_metric_update(
            collector_name=_COLLECTOR,
            metric_name=_METRIC,
            label_values={**_LABELS, "serial": serial},
            ttl_seconds=ttl_seconds,
        )

    async def test_ttl_override_survives_past_fallback_ttl(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Flap regression (#541).

        A series pinned to ttl_seconds=900 must SURVIVE cleanup at t=700s (would
        expire under the 600s fallback TTL) and expire only after 900s.
        """
        base_time = 30_000_000.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            self._track_with_ttl(expiration_manager, ttl_seconds=900.0)

        # t = 700s: past the 600s fallback TTL but under the per-series 900s TTL
        # — the series must still be tracked.
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + 700.0
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 1, (
            "Series gated slower than the fallback TTL must not flap (survives to 900s)"
        )
        assert expiration_manager._metric_counts[_COLLECTOR] == 1

        # t = 901s: past the per-series TTL — now it expires.
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + 901.0
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 0
        assert expiration_manager._metric_counts[_COLLECTOR] == 0

    async def test_no_ttl_seconds_uses_fallback_ttl(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """ttl_seconds=None ⇒ series expires at the cadence-derived fallback TTL (600s)."""
        base_time = 31_000_000.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            self._track_with_ttl(expiration_manager, ttl_seconds=None)

        # Just before the fallback TTL boundary — survives.
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + 599.0
            await expiration_manager._cleanup_expired_metrics()
        assert len(expiration_manager._metric_timestamps) == 1

        # Just past the fallback TTL boundary — expires.
        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + 601.0
            await expiration_manager._cleanup_expired_metrics()
        assert len(expiration_manager._metric_timestamps) == 0

    async def test_ttl_override_shorter_than_fallback_ttl_expires_early(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """A ttl_seconds shorter than the fallback TTL expires the series early."""
        base_time = 32_000_000.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            # Fallback TTL would be 600s; pin to 120s instead.
            self._track_with_ttl(expiration_manager, ttl_seconds=120.0)

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + 121.0
            await expiration_manager._cleanup_expired_metrics()

        assert len(expiration_manager._metric_timestamps) == 0

    async def test_ttl_override_survives_cardinality_pass(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """The cardinality enforcement pass must read the new NamedTuple store."""
        base_time = 33_000_000.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            self._track_with_ttl(expiration_manager, ttl_seconds=900.0)

        # A very high budget so nothing sheds; this exercises the timestamp
        # unpacking in _enforce_cardinality_budgets / check_family_cardinality.
        shed = expiration_manager.check_family_cardinality(_METRIC, max_series=1000)
        assert shed == 0
        assert len(expiration_manager._metric_timestamps) == 1


# ---------------------------------------------------------------------------
# Tests: TTL calculation per tier
# ---------------------------------------------------------------------------


class TestFallbackTTL:
    """Verify _fallback_ttl resolves a series' TTL post-de-tiering (#631)."""

    def test_default_fallback_ttl(self, expiration_manager: MetricExpirationManager) -> None:
        """With no resolver installed, fallback = resolve_interval * multiplier (300*2=600)."""
        assert expiration_manager._fallback_ttl("AnyCollector") == 600.0

    def test_installed_resolver_wins(self, expiration_manager: MetricExpirationManager) -> None:
        """A resolver installed by the manager overrides the default fallback."""
        expiration_manager.set_ttl_resolver(lambda _name: 450.0)
        assert expiration_manager._fallback_ttl("AnyCollector") == 450.0

    def test_resolver_declining_falls_back_to_default(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """A resolver that returns None falls through to the default fallback TTL."""
        expiration_manager.set_ttl_resolver(lambda _name: None)
        assert expiration_manager._fallback_ttl("AnyCollector") == 600.0


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


# ---------------------------------------------------------------------------
# Tests: real Prometheus series removal
# ---------------------------------------------------------------------------


class TestRealSeriesRemoval:
    """Expiration must remove the actual Prometheus series, not just tracking."""

    async def test_expired_series_removed_from_registry(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """When a tracked metric expires, its Gauge child series must be removed."""
        gauge = Gauge(
            "meraki_test_expiry_removal",
            "test gauge for expiry removal",
            labelnames=["org_id", "serial"],
        )
        base_time = 20_000_000.0
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            gauge.labels(org_id="o1", serial="s1").set(5)
            expiration_manager.track_metric_update(
                collector_name=_COLLECTOR,
                metric_name="meraki_test_expiry_removal",
                label_values={"org_id": "o1", "serial": "s1"},
                metric=gauge,
            )

        # Series exists before expiry.
        assert ("o1", "s1") in gauge._metrics

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + medium_ttl + 1.0
            await expiration_manager._cleanup_expired_metrics()

        # Series is actually gone from the Gauge — not just untracked.
        assert ("o1", "s1") not in gauge._metrics
        assert len(expiration_manager._metric_timestamps) == 0

    async def test_fresh_series_survives_removal(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Only the stale series is removed; a fresh series stays in the registry."""
        gauge = Gauge(
            "meraki_test_expiry_partial",
            "test gauge",
            labelnames=["org_id", "serial"],
        )
        base_time = 21_000_000.0
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            gauge.labels(org_id="o1", serial="stale").set(1)
            expiration_manager.track_metric_update(
                collector_name=_COLLECTOR,
                metric_name="meraki_test_expiry_partial",
                label_values={"org_id": "o1", "serial": "stale"},
                metric=gauge,
            )

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + medium_ttl - 10.0
            gauge.labels(org_id="o1", serial="fresh").set(1)
            expiration_manager.track_metric_update(
                collector_name=_COLLECTOR,
                metric_name="meraki_test_expiry_partial",
                label_values={"org_id": "o1", "serial": "fresh"},
                metric=gauge,
            )

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + medium_ttl + 1.0
            await expiration_manager._cleanup_expired_metrics()

        assert ("o1", "stale") not in gauge._metrics
        assert ("o1", "fresh") in gauge._metrics

    async def test_cardinality_shed_removes_series(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Cardinality shedding must also remove the underlying series."""
        gauge = Gauge(
            "meraki_test_cardinality_shed",
            "test gauge",
            labelnames=["org_id", "serial"],
        )
        base_time = 22_000_000.0

        for i in range(5):
            with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
                mock_time.return_value = base_time + i  # distinct timestamps
                gauge.labels(org_id="o1", serial=f"s{i}").set(1)
                expiration_manager.track_metric_update(
                    collector_name=_COLLECTOR,
                    metric_name="meraki_test_cardinality_shed",
                    label_values={"org_id": "o1", "serial": f"s{i}"},
                    metric=gauge,
                )

        # Shed down to 2 — the 3 oldest series should be removed from the Gauge.
        shed = expiration_manager.check_family_cardinality(
            "meraki_test_cardinality_shed", max_series=2, action="drop"
        )
        assert shed == 3
        assert ("o1", "s0") not in gauge._metrics
        assert ("o1", "s1") not in gauge._metrics
        assert ("o1", "s2") not in gauge._metrics
        assert ("o1", "s3") in gauge._metrics
        assert ("o1", "s4") in gauge._metrics

    async def test_removal_survives_already_removed_series(
        self, expiration_manager: MetricExpirationManager
    ) -> None:
        """Removing a series that was already removed elsewhere must not raise."""
        gauge = Gauge(
            "meraki_test_double_removal",
            "test gauge",
            labelnames=["org_id", "serial"],
        )
        base_time = 23_000_000.0
        medium_ttl = 600.0

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time
            gauge.labels(org_id="o1", serial="s1").set(1)
            expiration_manager.track_metric_update(
                collector_name=_COLLECTOR,
                metric_name="meraki_test_double_removal",
                label_values={"org_id": "o1", "serial": "s1"},
                metric=gauge,
            )

        # Externally remove the series before cleanup runs.
        gauge.remove("o1", "s1")

        with patch("meraki_dashboard_exporter.core.metric_expiration.time.time") as mock_time:
            mock_time.return_value = base_time + medium_ttl + 1.0
            await expiration_manager._cleanup_expired_metrics()  # must not raise

        assert len(expiration_manager._metric_timestamps) == 0
