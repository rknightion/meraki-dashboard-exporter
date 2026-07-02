"""Tests for the bounded label-value distribution in CardinalityMonitor (F-003).

``_label_value_distribution`` previously accumulated every label value ever
seen, forever - an unbounded memory leak driven by high-churn labels. It is now
capped per label so the structure stays bounded no matter how many distinct
values flow through, while per-analysis cardinality counts remain accurate.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry
from prometheus_client.core import Metric

from meraki_dashboard_exporter.core.cardinality import CardinalityMonitor


def _metric_with_distinct_values(count: int, *, name: str = "test_metric") -> Metric:
    """Build a metric family with ``count`` distinct values for label 'churn'."""
    metric = Metric(name, "test metric", "gauge")
    for i in range(count):
        metric.add_sample(name, labels={"churn": f"value_{i}"}, value=1.0)
    return metric


class TestLabelValueDistributionBounded:
    """The per-label distribution set is capped."""

    def test_distribution_is_capped_per_label(self) -> None:
        """Feeding many distinct values never grows the set past the cap."""
        registry = CollectorRegistry()
        monitor = CardinalityMonitor(registry=registry)
        cap = CardinalityMonitor._MAX_LABEL_VALUES_PER_LABEL

        # Feed well over the cap of distinct values across several analyses.
        for _ in range(3):
            metric = _metric_with_distinct_values(cap * 3)
            monitor._analyze_metric(metric)

        churn_values = monitor._label_value_distribution["test_metric"]["churn"]
        assert len(churn_values) <= cap

    def test_cardinality_count_still_accurate(self) -> None:
        """The bound on the distribution does not distort cardinality counting."""
        registry = CollectorRegistry()
        monitor = CardinalityMonitor(registry=registry)

        distinct = 250
        metric = _metric_with_distinct_values(distinct)
        info = monitor._analyze_metric(metric)

        assert info is not None
        # sample_count equals the number of series (one per distinct value).
        assert info["cardinality"] == distinct
        # Below the cap, distribution retains the true per-label cardinality.
        assert info["label_cardinalities"]["churn"] == distinct

    def test_existing_values_still_tracked_after_cap(self) -> None:
        """Once capped, already-seen values are still accepted (idempotent add)."""
        registry = CollectorRegistry()
        monitor = CardinalityMonitor(registry=registry)
        cap = CardinalityMonitor._MAX_LABEL_VALUES_PER_LABEL

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
        registry = CollectorRegistry()
        monitor = CardinalityMonitor(registry=registry)

        monitor._analyze_metric(_metric_with_distinct_values(50))
        dist = monitor.get_label_value_distribution("test_metric")
        assert "test_metric" in dist
        assert "churn" in dist["test_metric"]
        assert len(dist["test_metric"]["churn"]) == 50
