"""Regression tests for coherent CardinalityMonitor registry snapshots."""

from __future__ import annotations

from collections.abc import Iterator

from prometheus_client import CollectorRegistry, Gauge
from prometheus_client.core import Metric

from meraki_dashboard_exporter.core.cardinality import CardinalityMonitor


class _CountingRegistry(CollectorRegistry):
    """Registry that records how many live collection walks are requested."""

    def __init__(self) -> None:
        super().__init__()
        self.collect_calls = 0

    def collect(self) -> Iterator[Metric]:
        self.collect_calls += 1
        yield from super().collect()


class _OneSnapshotRegistry(_CountingRegistry):
    """Simulate a mutation that would empty a second live registry walk."""

    def collect(self) -> Iterator[Metric]:
        self.collect_calls += 1
        if self.collect_calls > 1:
            return
        yield from CollectorRegistry.collect(self)


def _ready_monitor(registry: CollectorRegistry) -> CardinalityMonitor:
    """Create a monitor whose analysis gate is open."""
    monitor = CardinalityMonitor(registry=registry)
    monitor.mark_first_run_complete()
    return monitor


def test_analysis_materializes_registry_once() -> None:
    """A single live registry walk supplies all cardinality accounting."""
    registry = _CountingRegistry()
    monitor = _ready_monitor(registry)
    Gauge("meraki_snapshot_product_metric", "Product", registry=registry).set(1)
    Gauge("meraki_exporter_snapshot_metric", "Exporter", registry=registry).set(1)
    registry.collect_calls = 0

    analysis = monitor.analyze_cardinality(use_cache=False)

    assert registry.collect_calls == 1
    assert analysis["product_series"] == 1
    assert analysis["exporter_series"] == 1
    assert (
        analysis["product_series"] + analysis["exporter_series"] + analysis["self_series"]
        == (analysis["exposed_series"])
    )


def test_snapshot_buckets_do_not_go_negative_when_registry_mutates() -> None:
    """The self bucket is a direct snapshot classification, never subtraction."""
    registry = _OneSnapshotRegistry()
    monitor = _ready_monitor(registry)
    Gauge("meraki_snapshot_product_metric", "Product", registry=registry).set(1)
    Gauge("meraki_exporter_snapshot_metric", "Exporter", registry=registry).set(1)
    registry.collect_calls = 0

    analysis = monitor.analyze_cardinality(use_cache=False)

    assert registry.collect_calls == 1
    assert analysis["self_series"] >= 0
    assert (
        analysis["product_series"] + analysis["exporter_series"] + analysis["self_series"]
        == (analysis["exposed_series"])
    )


def test_drilldowns_retain_only_product_families_from_snapshot() -> None:
    """Exporter, runtime, and monitor families never enter product drilldowns."""
    registry = CollectorRegistry()
    monitor = _ready_monitor(registry)
    Gauge(
        "meraki_snapshot_product_metric", "Product", labelnames=["scope"], registry=registry
    ).labels(scope="product").set(1)
    Gauge("meraki_exporter_snapshot_metric", "Exporter", registry=registry).set(1)
    Gauge("python_snapshot_runtime_metric", "Runtime", registry=registry).set(1)

    monitor.analyze_cardinality(use_cache=False)

    assert list(monitor._full_metric_data) == ["meraki_snapshot_product_metric"]
    assert [item["name"] for item in monitor.get_all_metrics()] == [
        "meraki_snapshot_product_metric"
    ]
    assert {item["label"] for item in monitor.get_all_labels()} == {"scope"}
    distribution = monitor.get_label_value_distribution()
    assert set(distribution) == {"scope"}
    assert "meraki_exporter_snapshot_metric" not in distribution
    assert "python_snapshot_runtime_metric" not in distribution
