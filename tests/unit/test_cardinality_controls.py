"""Unit tests for metric cardinality controls.

Tests verify that MetricExpirationManager.check_cardinality:
- Returns 0 when within limits
- Sheds the oldest (least-recently-updated) label sets when the limit is exceeded
- Returns the correct shed count
- Sets the alert gauge to 1 when shedding occurs and 0 when within limits
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

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
    settings.monitoring.max_cardinality_per_collector = 10000
    settings.update_intervals.fast = 60
    settings.update_intervals.medium = 300
    settings.update_intervals.slow = 900
    return settings


@pytest.fixture
def manager(mock_settings: MagicMock) -> MetricExpirationManager:
    """MetricExpirationManager instance (background loop not started)."""
    return MetricExpirationManager(settings=mock_settings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLLECTOR = "TestCollector"
_METRIC = "meraki_test_metric"


def _add_metric(
    mgr: MetricExpirationManager,
    collector: str,
    serial: str,
    timestamp: float | None = None,
) -> None:
    """Insert a tracking entry directly, optionally with a custom timestamp."""
    labels = {"org_id": "org_1", "serial": serial}
    frozen = mgr._freeze_labels(labels)
    key = (collector, _METRIC, frozen)
    ts = timestamp if timestamp is not None else time.time()
    if key not in mgr._metric_timestamps:
        mgr._metric_counts[collector] += 1
    mgr._metric_timestamps[key] = (ts, UpdateTier.MEDIUM)


# ---------------------------------------------------------------------------
# Tests: within limits
# ---------------------------------------------------------------------------


class TestWithinLimits:
    """check_cardinality with collector below or at the cap."""

    def test_empty_collector_returns_zero(self, manager: MetricExpirationManager) -> None:
        """A collector with no metrics is within limits."""
        result = manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        assert result == 0

    def test_below_limit_returns_zero(self, manager: MetricExpirationManager) -> None:
        """A collector with fewer metrics than the cap returns 0."""
        for i in range(5):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}")

        result = manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        assert result == 0

    def test_exactly_at_limit_returns_zero(self, manager: MetricExpirationManager) -> None:
        """A collector at exactly the cap is still within limits."""
        for i in range(10):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}")

        result = manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        assert result == 0

    def test_within_limits_does_not_alter_count(self, manager: MetricExpirationManager) -> None:
        """No entries are removed when the collector is within limits."""
        for i in range(5):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}")

        manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        assert len(manager._metric_timestamps) == 5

    def test_within_limits_sets_alert_gauge_to_zero(self, manager: MetricExpirationManager) -> None:
        """Alert gauge should be 0 when within limits."""
        for i in range(3):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}")

        manager.check_cardinality(_COLLECTOR, max_cardinality=10)

        # Read the gauge value directly
        gauge_val = manager._cardinality_limit_reached.labels(collector=_COLLECTOR)._value.get()
        assert gauge_val == 0


# ---------------------------------------------------------------------------
# Tests: exceeding limits
# ---------------------------------------------------------------------------


class TestExceedingLimits:
    """check_cardinality sheds oldest entries when over budget."""

    def test_shed_count_is_correct(self, manager: MetricExpirationManager) -> None:
        """shed count equals (actual - max)."""
        now = time.time()
        for i in range(15):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)

        shed = manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        assert shed == 5

    def test_remaining_count_equals_max(self, manager: MetricExpirationManager) -> None:
        """After shedding, exactly max_cardinality entries remain for the collector."""
        now = time.time()
        for i in range(20):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)

        manager.check_cardinality(_COLLECTOR, max_cardinality=10)

        remaining = [k for k in manager._metric_timestamps if k[0] == _COLLECTOR]
        assert len(remaining) == 10

    def test_oldest_entries_are_shed(self, manager: MetricExpirationManager) -> None:
        """The oldest label sets (lowest timestamps) are removed first."""
        base_time = 1_000_000.0
        serials = [f"S{i:03d}" for i in range(10)]
        for idx, serial in enumerate(serials):
            _add_metric(manager, _COLLECTOR, serial, timestamp=base_time + idx)

        # Keep only the 5 newest (S005–S009)
        manager.check_cardinality(_COLLECTOR, max_cardinality=5)

        remaining_keys = list(manager._metric_timestamps.keys())
        remaining_serials = set()
        for _col, _metric, frozen in remaining_keys:
            for part in frozen.split("|"):
                if part.startswith("serial="):
                    remaining_serials.add(part.split("=", 1)[1])

        # Oldest 5 (S000–S004) should be gone; newest 5 (S005–S009) remain
        for s in serials[:5]:
            assert s not in remaining_serials, f"Expected {s} to be shed"
        for s in serials[5:]:
            assert s in remaining_serials, f"Expected {s} to survive"

    def test_metric_count_updated_after_shedding(self, manager: MetricExpirationManager) -> None:
        """_metric_counts reflects the reduced count after shedding."""
        now = time.time()
        for i in range(15):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)

        manager.check_cardinality(_COLLECTOR, max_cardinality=10)

        assert manager._metric_counts[_COLLECTOR] == 10

    def test_other_collectors_unaffected(self, manager: MetricExpirationManager) -> None:
        """Shedding from one collector leaves other collectors intact."""
        other = "OtherCollector"
        now = time.time()
        for i in range(15):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)
        for i in range(5):
            _add_metric(manager, other, f"O{i:03d}", timestamp=now + i)

        manager.check_cardinality(_COLLECTOR, max_cardinality=10)

        other_entries = [k for k in manager._metric_timestamps if k[0] == other]
        assert len(other_entries) == 5

    def test_alert_gauge_set_to_one_when_shedding(self, manager: MetricExpirationManager) -> None:
        """Alert gauge is 1 when shedding occurs."""
        now = time.time()
        for i in range(15):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)

        manager.check_cardinality(_COLLECTOR, max_cardinality=10)

        gauge_val = manager._cardinality_limit_reached.labels(collector=_COLLECTOR)._value.get()
        assert gauge_val == 1

    def test_alert_gauge_resets_to_zero_after_recovery(
        self, manager: MetricExpirationManager
    ) -> None:
        """Alert gauge returns to 0 once the collector drops back within limits."""
        now = time.time()
        for i in range(15):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)

        # First call: over limit → shed, gauge = 1
        manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        gauge_val = manager._cardinality_limit_reached.labels(collector=_COLLECTOR)._value.get()
        assert gauge_val == 1

        # Manually remove more entries so we are back under the cap
        keys_to_remove = [k for k in list(manager._metric_timestamps.keys()) if k[0] == _COLLECTOR]
        for k in keys_to_remove[5:]:
            del manager._metric_timestamps[k]
            manager._metric_counts[_COLLECTOR] -= 1

        # Second call: now within limit → gauge = 0
        manager.check_cardinality(_COLLECTOR, max_cardinality=10)
        gauge_val = manager._cardinality_limit_reached.labels(collector=_COLLECTOR)._value.get()
        assert gauge_val == 0


# ---------------------------------------------------------------------------
# Tests: cleanup loop integration
# ---------------------------------------------------------------------------


class TestCleanupLoopIntegration:
    """Verify check_cardinality is called during _cleanup_expired_metrics."""

    @pytest.mark.asyncio
    async def test_cleanup_enforces_cardinality(
        self, manager: MetricExpirationManager, mock_settings: MagicMock
    ) -> None:
        """_cleanup_expired_metrics calls check_cardinality for each collector."""
        mock_settings.monitoring.max_cardinality_per_collector = 5
        now = time.time()

        # Add 10 entries — all fresh so none expire by TTL
        for i in range(10):
            _add_metric(manager, _COLLECTOR, f"S{i:03d}", timestamp=now + i)

        await manager._cleanup_expired_metrics()

        remaining = [k for k in manager._metric_timestamps if k[0] == _COLLECTOR]
        assert len(remaining) == 5
