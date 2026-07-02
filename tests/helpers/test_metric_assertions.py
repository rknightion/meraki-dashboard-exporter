"""Regression tests for MetricAssertions' live-read behavior.

Covers bug-bash finding F-163: `MetricAssertions.get_metric` used to cache
the materialized `Metric` object per name, so every assertion after the
first one on a given metric name read a stale, point-in-time snapshot -
including `assert_metric_not_set`, which could produce a false pass.
"""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry, Gauge

from tests.helpers.metrics import MetricAssertions


@pytest.fixture
def registry() -> CollectorRegistry:
    """A fresh, isolated Prometheus registry."""
    return CollectorRegistry()


class TestLiveReads:
    """assert_* calls must always reflect the latest value, not a first-read cache."""

    def test_assert_gauge_value_sees_updates_after_first_read(
        self, registry: CollectorRegistry
    ) -> None:
        """A gauge changed after the first assertion must be seen by the next one."""
        gauge = Gauge("mock_gauge", "test", labelnames=["serial"], registry=registry)
        gauge.labels(serial="Q1").set(1)

        metrics = MetricAssertions(registry)
        metrics.assert_gauge_value("mock_gauge", 1, serial="Q1")

        gauge.labels(serial="Q1").set(0)

        metrics.assert_gauge_value("mock_gauge", 0, serial="Q1")

    def test_assert_metric_not_set_reflects_a_series_added_after_first_read(
        self, registry: CollectorRegistry
    ) -> None:
        """A series set after an earlier read of the same metric must not false-pass."""
        gauge = Gauge("mock_gauge2", "test", labelnames=["serial"], registry=registry)
        gauge.labels(serial="Q1").set(1)

        metrics = MetricAssertions(registry)
        # Touch the metric once so a caching implementation would snapshot it
        # before the Q2 series exists.
        metrics.assert_gauge_value("mock_gauge2", 1, serial="Q1")

        gauge.labels(serial="Q2").set(5)

        with pytest.raises(AssertionError):
            metrics.assert_metric_not_set("mock_gauge2", serial="Q2")

    def test_get_metric_value_sees_updates_after_first_read(
        self, registry: CollectorRegistry
    ) -> None:
        """get_metric_value (used by get_gauge_value/get_counter_value) must be live too."""
        gauge = Gauge("mock_gauge3", "test", labelnames=["serial"], registry=registry)
        gauge.labels(serial="Q1").set(10)

        metrics = MetricAssertions(registry)
        assert metrics.get_metric_value("mock_gauge3", serial="Q1") == 10

        gauge.labels(serial="Q1").set(20)

        assert metrics.get_metric_value("mock_gauge3", serial="Q1") == 20
