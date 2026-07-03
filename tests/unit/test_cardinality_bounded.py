"""Tests for the bounded retention in CardinalityMonitor (F-003 / #554).

``_label_value_distribution`` previously accumulated every label value ever
seen, forever - an unbounded memory leak driven by high-churn labels - and the
full per-metric ``label_values`` lists were retained in ``_full_metric_data``.
Both are now capped at ``cardinality.monitor_max_label_values`` (default 100)
so the monitor's own memory stays bounded no matter how many distinct values
flow through, while per-analysis cardinality counts remain accurate. The
analysis interval is exposed as ``analysis_interval_seconds`` (default 300,
from ``cardinality.monitor_interval_seconds``) for the app's monitor loop.
"""

from __future__ import annotations

from types import SimpleNamespace

from prometheus_client import CollectorRegistry
from prometheus_client.core import Metric

from meraki_dashboard_exporter.core.cardinality import CardinalityMonitor


def _metric_with_distinct_values(count: int, *, name: str = "test_metric") -> Metric:
    """Build a metric family with ``count`` distinct values for label 'churn'."""
    metric = Metric(name, "test metric", "gauge")
    for i in range(count):
        metric.add_sample(name, labels={"churn": f"value_{i}"}, value=1.0)
    return metric


def _settings(
    *, max_label_values: int | None = None, interval: int | None = None
) -> SimpleNamespace:
    """Minimal settings shim exposing the frozen CFG3 cardinality seam."""
    card = SimpleNamespace()
    if max_label_values is not None:
        card.monitor_max_label_values = max_label_values
    if interval is not None:
        card.monitor_interval_seconds = interval
    return SimpleNamespace(cardinality=card)


class TestLabelValueDistributionBounded:
    """The per-label distribution set is capped."""

    def test_default_cap_is_100(self) -> None:
        """Without settings the seam default (100) applies."""
        monitor = CardinalityMonitor(registry=CollectorRegistry())
        assert monitor._max_label_values == 100

    def test_cap_configurable_via_settings(self) -> None:
        """cardinality.monitor_max_label_values overrides the cap."""
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(max_label_values=10),
        )
        assert monitor._max_label_values == 10

    def test_distribution_is_capped_per_label(self) -> None:
        """Feeding many distinct values never grows the set past the cap."""
        cap = 10
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(max_label_values=cap),
        )

        # Feed well over the cap of distinct values across several analyses.
        for _ in range(3):
            metric = _metric_with_distinct_values(cap * 3)
            monitor._analyze_metric(metric)

        churn_values = monitor._label_value_distribution["test_metric"]["churn"]
        assert len(churn_values) <= cap

    def test_retained_label_values_lists_are_capped(self) -> None:
        """The per-metric label_values retained for detail views are a bounded sample."""
        cap = 10
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(max_label_values=cap),
        )

        info = monitor._analyze_metric(_metric_with_distinct_values(cap * 5))

        assert info is not None
        assert len(info["label_values"]["churn"]) <= cap
        retained = monitor._full_metric_data["test_metric"]["label_values"]["churn"]
        assert len(retained) <= cap

    def test_cardinality_count_still_accurate(self) -> None:
        """The bound on retention does not distort cardinality counting."""
        cap = 10
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(max_label_values=cap),
        )

        distinct = 250
        metric = _metric_with_distinct_values(distinct)
        info = monitor._analyze_metric(metric)

        assert info is not None
        # sample_count equals the number of series (one per distinct value).
        assert info["cardinality"] == distinct
        # Per-label counts are computed from the full per-cycle set, not the sample.
        assert info["label_cardinalities"]["churn"] == distinct

    def test_existing_values_still_tracked_after_cap(self) -> None:
        """Once capped, already-seen values are still accepted (idempotent add)."""
        cap = 10
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(max_label_values=cap),
        )

        # Saturate the cap.
        monitor._analyze_metric(_metric_with_distinct_values(cap * 2))
        churn = monitor._label_value_distribution["test_metric"]["churn"]
        assert len(churn) == cap

        # Re-feeding the same (already-tracked) values must not exceed the cap
        # and must not error.
        monitor._analyze_metric(_metric_with_distinct_values(cap * 2))
        assert len(monitor._label_value_distribution["test_metric"]["churn"]) == cap

    def test_reporting_endpoint_data_still_available(self) -> None:
        """get_label_value_distribution keeps returning data under the cap."""
        monitor = CardinalityMonitor(registry=CollectorRegistry())

        monitor._analyze_metric(_metric_with_distinct_values(50))
        dist = monitor.get_label_value_distribution("test_metric")
        assert "test_metric" in dist
        assert "churn" in dist["test_metric"]
        assert len(dist["test_metric"]["churn"]) == 50


class TestAnalysisInterval:
    """The monitor exposes its analysis interval for the app loop (#554)."""

    def test_default_interval_is_300(self) -> None:
        """Without settings the seam default interval (300s) applies."""
        monitor = CardinalityMonitor(registry=CollectorRegistry())
        assert monitor.analysis_interval_seconds == 300

    def test_interval_configurable_via_settings(self) -> None:
        """cardinality.monitor_interval_seconds overrides the interval."""
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(interval=900),
        )
        assert monitor.analysis_interval_seconds == 900

    def test_cache_ttl_follows_interval(self) -> None:
        """On-demand endpoint hits reuse cached analysis for a full interval."""
        monitor = CardinalityMonitor(
            registry=CollectorRegistry(),
            settings=_settings(interval=900),
        )
        assert monitor._cache_ttl == 900.0
