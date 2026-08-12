"""Regression coverage for the cardinality bucket meanings (#726)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from meraki_dashboard_exporter.core.cardinality import CardinalityMonitor
from meraki_dashboard_exporter.core.constants.metrics_constants import CollectorMetricName


def _scrape_sample_count(registry: CollectorRegistry) -> int:
    """Return the number of samples in a real Prometheus text scrape."""
    scrape = generate_latest(registry).decode()
    return sum(bool(line) and not line.startswith("#") for line in scrape.splitlines())


def test_cardinality_buckets_separate_product_exporter_and_monitor_series() -> None:
    """#726: the three buckets reconcile exactly with the exposed scrape."""
    registry = CollectorRegistry()
    monitor = CardinalityMonitor(registry=registry)
    monitor.mark_first_run_complete()
    Gauge("meraki_issue_726_product_metric", "Product data", registry=registry).set(1)
    Gauge(
        "meraki_exporter_issue_726_self_metric", "Exporter instrumentation", registry=registry
    ).set(1)

    analysis = monitor.analyze_cardinality(use_cache=False)

    assert analysis["product_series"] == 1
    assert analysis["exporter_series"] == 1
    assert "meraki_exporter_issue_726_self_metric" not in analysis["metrics"]
    assert analysis["self_series"] > 0
    assert analysis["product_series"] + analysis["exporter_series"] + analysis[
        "self_series"
    ] == _scrape_sample_count(registry)
    scrape_sample_count = _scrape_sample_count(registry)
    assert analysis["total_series"] == scrape_sample_count

    scrape = generate_latest(registry).decode()
    assert f"meraki_exporter_total_series {scrape_sample_count}.0" in scrape
    assert (
        f"{CollectorMetricName.CARDINALITY_EXPORTER_SERIES.value} {analysis['exporter_series']}.0"
    ) in scrape
