"""Unit tests for per-family metric cardinality budgets (#540).

The old design keyed one shared ``max_cardinality_per_collector`` budget
(default 10,000) by parent collector class name, so ALL device sub-collectors
shared a single "DeviceCollector" bucket and the limiter removed LIVE series
via ``Gauge.remove()`` at scale. The new design:

- budgets are keyed per metric family (metric name), not per collector
- default budget is ``cardinality.max_series_per_family`` (50,000)
- with ``cardinality.action="warn"`` (the default) an over-budget family
  ALARMS (``meraki_exporter_cardinality_limit_reached_total`` counter + log)
  and NO live series are removed
- ``cardinality.action="drop"`` preserves the old shedding behaviour
  (oldest-first, scoped to the offending family)
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.core.cardinality import CardinalityConfig
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.metric_expiration import (
    MetricExpirationManager,
    _TrackedSeries,  # noqa: PLC2701 - internal store record; tests seed entries directly
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.monitoring.metric_ttl_multiplier = 2.0
    settings.update_intervals.fast = 60
    settings.update_intervals.medium = 300
    settings.update_intervals.slow = 900
    return settings


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock Settings with an explicit small per-family budget (warn action)."""
    settings = _base_mock_settings()
    settings.cardinality = SimpleNamespace(
        max_series_per_family=10,
        action="warn",
        disabled_metrics=set(),
        monitor_interval_seconds=300,
        monitor_max_label_values=100,
    )
    return settings


@pytest.fixture
def manager(mock_settings: MagicMock) -> MetricExpirationManager:
    """MetricExpirationManager instance (background loop not started)."""
    return MetricExpirationManager(settings=mock_settings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLLECTOR = "DeviceCollector"
_METRIC = "meraki_test_metric"


def _add_series(
    mgr: MetricExpirationManager,
    serial: str,
    *,
    collector: str = _COLLECTOR,
    metric: str = _METRIC,
    timestamp: float | None = None,
) -> None:
    """Insert a tracking entry directly, optionally with a custom timestamp."""
    labels = {"org_id": "org_1", "serial": serial}
    frozen = mgr._freeze_labels(labels)
    key = (collector, metric, frozen)
    ts = timestamp if timestamp is not None else time.time()
    if key not in mgr._metric_timestamps:
        mgr._metric_counts[collector] += 1
    mgr._metric_timestamps[key] = _TrackedSeries(ts, UpdateTier.MEDIUM, None)


def _limit_counter_value(mgr: MetricExpirationManager, metric: str) -> float:
    """Read the cardinality_limit_reached counter for a metric family."""
    return mgr._cardinality_limit_reached_total.labels(metric=metric)._value.get()


# ---------------------------------------------------------------------------
# Tests: defensive config resolution (frozen CFG3 seam)
# ---------------------------------------------------------------------------


class TestCardinalityConfigResolution:
    """CardinalityConfig.from_settings copes with any settings shape."""

    def test_defaults_when_cardinality_attr_missing(self) -> None:
        """Real pre-CFG3 Settings (no .cardinality attr) yields seam defaults."""
        config = CardinalityConfig.from_settings(SimpleNamespace())
        assert config.max_series_per_family == 50000
        assert config.action == "warn"
        assert config.disabled_metrics == frozenset()
        assert config.monitor_interval_seconds == 300
        assert config.monitor_max_label_values == 100

    def test_defaults_when_settings_none(self) -> None:
        """None settings resolve to seam defaults."""
        config = CardinalityConfig.from_settings(None)
        assert config.max_series_per_family == 50000
        assert config.action == "warn"

    def test_defaults_when_values_are_mocks(self) -> None:
        """Bare MagicMock settings (attrs are MagicMocks) coerce to defaults."""
        config = CardinalityConfig.from_settings(MagicMock())
        assert config.max_series_per_family == 50000
        assert config.action == "warn"
        assert config.disabled_metrics == frozenset()
        assert config.monitor_interval_seconds == 300
        assert config.monitor_max_label_values == 100

    def test_configured_values_pass_through(self) -> None:
        """Well-typed configured values are used as-is (names normalized)."""
        settings = SimpleNamespace(
            cardinality=SimpleNamespace(
                max_series_per_family=1234,
                action="drop",
                disabled_metrics={"meraki_foo", "meraki_bar_total"},
                monitor_interval_seconds=600,
                monitor_max_label_values=25,
            )
        )
        config = CardinalityConfig.from_settings(settings)
        assert config.max_series_per_family == 1234
        assert config.action == "drop"
        # disabled names are normalized (trailing _total stripped)
        assert config.disabled_metrics == frozenset({"meraki_foo", "meraki_bar"})
        assert config.monitor_interval_seconds == 600
        assert config.monitor_max_label_values == 25

    def test_invalid_action_falls_back_to_warn(self) -> None:
        """Unknown action strings resolve to the safe default (warn)."""
        settings = SimpleNamespace(cardinality=SimpleNamespace(action="explode"))
        assert CardinalityConfig.from_settings(settings).action == "warn"


# ---------------------------------------------------------------------------
# Tests: warn action (default) — alarm, never delete
# ---------------------------------------------------------------------------


class TestWarnAction:
    """action='warn' alarms without touching live series."""

    def test_over_budget_family_keeps_all_series(self, manager: MetricExpirationManager) -> None:
        """No tracked series are removed when a family exceeds its budget."""
        now = time.time()
        for i in range(15):
            _add_series(manager, f"S{i:03d}", timestamp=now + i)

        shed = manager.check_family_cardinality(_METRIC, max_series=10, action="warn")

        assert shed == 0
        assert len(manager._metric_timestamps) == 15
        assert manager._metric_counts[_COLLECTOR] == 15

    def test_over_budget_family_increments_limit_counter(
        self, manager: MetricExpirationManager
    ) -> None:
        """The cardinality_limit_reached counter increments per over-budget check."""
        now = time.time()
        for i in range(15):
            _add_series(manager, f"S{i:03d}", timestamp=now + i)

        manager.check_family_cardinality(_METRIC, max_series=10, action="warn")
        assert _limit_counter_value(manager, _METRIC) == 1

        manager.check_family_cardinality(_METRIC, max_series=10, action="warn")
        assert _limit_counter_value(manager, _METRIC) == 2

    def test_within_budget_family_does_not_alarm(self, manager: MetricExpirationManager) -> None:
        """A family within budget neither sheds nor alarms."""
        for i in range(5):
            _add_series(manager, f"S{i:03d}")

        shed = manager.check_family_cardinality(_METRIC, max_series=10, action="warn")

        assert shed == 0
        assert _limit_counter_value(manager, _METRIC) == 0

    def test_warn_preserves_live_gauge_series(self, manager: MetricExpirationManager) -> None:
        """Gauge-backed series survive an over-budget warn check untouched."""
        gauge = Gauge(
            "meraki_test_warn_survivors",
            "test gauge",
            labelnames=["org_id", "serial"],
        )
        for i in range(8):
            labels = {"org_id": "o1", "serial": f"s{i}"}
            gauge.labels(**labels).set(1)
            manager.track_metric_update(
                collector_name=_COLLECTOR,
                metric_name="meraki_test_warn_survivors",
                label_values=labels,
                metric=gauge,
            )

        shed = manager.check_family_cardinality(
            "meraki_test_warn_survivors", max_series=3, action="warn"
        )

        assert shed == 0
        assert len(gauge._metrics) == 8


# ---------------------------------------------------------------------------
# Tests: drop action — legacy shedding, scoped to the family
# ---------------------------------------------------------------------------


class TestDropAction:
    """action='drop' sheds oldest series within the offending family only."""

    def test_shed_count_and_remaining(self, manager: MetricExpirationManager) -> None:
        """Drop mode sheds exactly (actual - budget) series from the family."""
        now = time.time()
        for i in range(15):
            _add_series(manager, f"S{i:03d}", timestamp=now + i)

        shed = manager.check_family_cardinality(_METRIC, max_series=10, action="drop")

        assert shed == 5
        remaining = [k for k in manager._metric_timestamps if k[1] == _METRIC]
        assert len(remaining) == 10
        assert manager._metric_counts[_COLLECTOR] == 10

    def test_oldest_series_are_shed_first(self, manager: MetricExpirationManager) -> None:
        """The least-recently-updated series are removed first."""
        base_time = 1_000_000.0
        serials = [f"S{i:03d}" for i in range(10)]
        for idx, serial in enumerate(serials):
            _add_series(manager, serial, timestamp=base_time + idx)

        manager.check_family_cardinality(_METRIC, max_series=5, action="drop")

        remaining_serials = set()
        for _col, _metric, frozen in manager._metric_timestamps:
            for part in frozen.split("|"):
                if part.startswith("serial="):
                    remaining_serials.add(part.split("=", 1)[1])

        for s in serials[:5]:
            assert s not in remaining_serials, f"Expected {s} to be shed"
        for s in serials[5:]:
            assert s in remaining_serials, f"Expected {s} to survive"

    def test_other_families_unaffected(self, manager: MetricExpirationManager) -> None:
        """Shedding one family leaves sibling families of the same collector alone."""
        other_metric = "meraki_other_metric"
        now = time.time()
        for i in range(15):
            _add_series(manager, f"S{i:03d}", timestamp=now + i)
        for i in range(8):
            _add_series(manager, f"O{i:03d}", metric=other_metric, timestamp=now + i)

        manager.check_family_cardinality(_METRIC, max_series=10, action="drop")

        other_entries = [k for k in manager._metric_timestamps if k[1] == other_metric]
        assert len(other_entries) == 8

    def test_drop_increments_limit_counter(self, manager: MetricExpirationManager) -> None:
        """Drop mode alarms via the counter as well as shedding."""
        now = time.time()
        for i in range(15):
            _add_series(manager, f"S{i:03d}", timestamp=now + i)

        manager.check_family_cardinality(_METRIC, max_series=10, action="drop")

        assert _limit_counter_value(manager, _METRIC) == 1

    def test_drop_removes_live_gauge_series(self, manager: MetricExpirationManager) -> None:
        """Drop mode still removes the underlying Prometheus series (legacy path)."""
        gauge = Gauge(
            "meraki_test_drop_shed",
            "test gauge",
            labelnames=["org_id", "serial"],
        )
        base_time = 22_000_000.0
        for i in range(5):
            labels = {"org_id": "o1", "serial": f"s{i}"}
            gauge.labels(**labels).set(1)
            manager.track_metric_update(
                collector_name=_COLLECTOR,
                metric_name="meraki_test_drop_shed",
                label_values=labels,
                metric=gauge,
            )
            key = (_COLLECTOR, "meraki_test_drop_shed", manager._freeze_labels(labels))
            manager._metric_timestamps[key] = _TrackedSeries(base_time + i, UpdateTier.MEDIUM, None)

        shed = manager.check_family_cardinality(
            "meraki_test_drop_shed", max_series=2, action="drop"
        )

        assert shed == 3
        assert ("o1", "s0") not in gauge._metrics
        assert ("o1", "s1") not in gauge._metrics
        assert ("o1", "s2") not in gauge._metrics
        assert ("o1", "s3") in gauge._metrics
        assert ("o1", "s4") in gauge._metrics


# ---------------------------------------------------------------------------
# Tests: cleanup-loop integration + the #540 regression
# ---------------------------------------------------------------------------


class TestCleanupLoopIntegration:
    """_cleanup_expired_metrics enforces per-family budgets from settings."""

    @pytest.mark.asyncio
    async def test_live_series_survive_past_old_shared_threshold(self) -> None:
        """REGRESSION (#540): >10k fresh series under ONE collector survive.

        The old shared 10k DeviceCollector bucket would have shed 50 of these.
        Per-family budgets (default 50k) with action='warn' must keep them all.
        """
        settings = _base_mock_settings()  # no usable .cardinality → seam defaults
        manager = MetricExpirationManager(settings=settings)

        now = time.time()
        # 10,050 fresh series under one collector, spread over 3 families
        # (each family well under the 50k default family budget).
        families = ["meraki_ms_port_status", "meraki_ms_port_traffic", "meraki_device_up"]
        for i in range(10_050):
            _add_series(
                manager,
                f"S{i:05d}",
                metric=families[i % len(families)],
                timestamp=now,
            )
        assert len(manager._metric_timestamps) == 10_050

        await manager._cleanup_expired_metrics()

        assert len(manager._metric_timestamps) == 10_050
        assert manager._metric_counts[_COLLECTOR] == 10_050

    @pytest.mark.asyncio
    async def test_cleanup_warn_mode_alarms_but_keeps_series(
        self, manager: MetricExpirationManager
    ) -> None:
        """Over-budget family in warn mode: counter fires, nothing removed."""
        now = time.time()
        for i in range(15):  # budget from fixture settings = 10
            _add_series(manager, f"S{i:03d}", timestamp=now)

        await manager._cleanup_expired_metrics()

        assert len(manager._metric_timestamps) == 15
        assert _limit_counter_value(manager, _METRIC) == 1

    @pytest.mark.asyncio
    async def test_cleanup_drop_mode_sheds_to_budget(self, mock_settings: MagicMock) -> None:
        """Cleanup applies drop-mode budgets from settings."""
        mock_settings.cardinality.action = "drop"
        manager = MetricExpirationManager(settings=mock_settings)

        now = time.time()
        for i in range(15):  # budget = 10
            _add_series(manager, f"S{i:03d}", timestamp=now + i)

        await manager._cleanup_expired_metrics()

        remaining = [k for k in manager._metric_timestamps if k[1] == _METRIC]
        assert len(remaining) == 10

    @pytest.mark.asyncio
    async def test_cleanup_enforces_each_family_independently(
        self, mock_settings: MagicMock
    ) -> None:
        """Two families under one collector are budgeted independently."""
        mock_settings.cardinality.action = "drop"
        manager = MetricExpirationManager(settings=mock_settings)

        now = time.time()
        for i in range(15):  # over budget (10)
            _add_series(manager, f"S{i:03d}", metric="meraki_family_a", timestamp=now + i)
        for i in range(5):  # within budget
            _add_series(manager, f"T{i:03d}", metric="meraki_family_b", timestamp=now + i)

        await manager._cleanup_expired_metrics()

        family_a = [k for k in manager._metric_timestamps if k[1] == "meraki_family_a"]
        family_b = [k for k in manager._metric_timestamps if k[1] == "meraki_family_b"]
        assert len(family_a) == 10
        assert len(family_b) == 5
