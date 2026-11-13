"""Tests for detecting emitted metrics in the collector test helper."""

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from tests.helpers.base import BaseCollectorTest
from tests.helpers.metrics import MetricAssertions


def test_incremented_labelled_counter_is_set():
    """An incremented counter is detected."""
    registry = CollectorRegistry()
    counter = Counter("requests", "Requests", ["kind"], registry=registry)
    counter.labels(kind="example").inc()

    with pytest.raises(pytest.fail.Exception):
        BaseCollectorTest().verify_no_metrics_set(MetricAssertions(registry), ["requests"])


def test_observed_histogram_is_set():
    """An observed histogram is detected."""
    registry = CollectorRegistry()
    Histogram("duration", "Duration", registry=registry).observe(1)

    with pytest.raises(pytest.fail.Exception):
        BaseCollectorTest().verify_no_metrics_set(MetricAssertions(registry), ["duration"])


def test_zero_gauge_is_set():
    """A zero-valued gauge is still detected."""
    registry = CollectorRegistry()
    Gauge("temperature", "Temperature", registry=registry).set(0)

    with pytest.raises(pytest.fail.Exception):
        BaseCollectorTest().verify_no_metrics_set(MetricAssertions(registry), ["temperature"])


def test_unset_and_unknown_metrics_are_not_set():
    """Unobserved and absent metrics do not fail the check."""
    registry = CollectorRegistry()
    Counter("labelled", "Labelled", ["kind"], registry=registry)
    Counter("unlabelled", "Unlabelled", registry=registry)
    Histogram("unobserved", "Unobserved", registry=registry)

    BaseCollectorTest().verify_no_metrics_set(
        MetricAssertions(registry), ["labelled", "unlabelled", "unobserved", "unknown"]
    )
