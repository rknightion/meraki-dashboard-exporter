"""Tests for span metrics generation from OpenTelemetry spans."""

# ruff: noqa: S101

from __future__ import annotations

import time
from typing import Any

from opentelemetry.trace import StatusCode
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.core.span_metrics import (
    SpanMetricsProcessor,
    setup_span_metrics,
)
from tests.helpers.metrics import MetricAssertions


class _DummySpan:
    """Simple span object for testing on_start."""

    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class _DummyReadableSpan(_DummySpan):
    """Readable span for testing on_end."""

    def __init__(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
        status_code: StatusCode = StatusCode.OK,
        events: list[Any] | None = None,
        duration: float = 0.1,
    ) -> None:
        super().__init__()
        self.name = name
        if attributes:
            self.attributes.update(attributes)
        self.status = type("Status", (), {"status_code": status_code})()
        self.events = events or []
        self.start_time = time.time_ns()
        self.end_time = self.start_time + int(duration * 1e9)


def make_exception_event(exc_type: str) -> Any:
    """Create a span event representing an exception."""

    return type(
        "Event",
        (),
        {"name": "exception", "attributes": {"exception.type": exc_type}},
    )()


def test_on_start_sets_start_time() -> None:
    """Verify ``on_start`` records the start timestamp."""

    registry = CollectorRegistry()
    processor = SpanMetricsProcessor(registry)
    span = _DummySpan()
    processor.on_start(span)  # type: ignore[arg-type]
    assert "span.start_time" in span.attributes


def test_on_end_records_metrics() -> None:
    """Ensure ``on_end`` generates expected metrics."""

    registry = CollectorRegistry()
    processor = SpanMetricsProcessor(registry)
    metrics = MetricAssertions(registry)

    # Successful span
    ok_span = _DummyReadableSpan(
        "op",
        attributes={"collector.name": "C", "api.endpoint": "https://api/x"},
    )
    processor.on_end(ok_span)  # type: ignore[arg-type]

    # Error span with exception event
    err_span = _DummyReadableSpan(
        "op",
        attributes={"collector.name": "C", "api.endpoint": "https://api/x"},
        status_code=StatusCode.ERROR,
        events=[make_exception_event("ValueError")],
    )
    processor.on_end(err_span)  # type: ignore[arg-type]

    metrics.assert_counter_value(
        "meraki_span_requests",
        1,
        operation="op",
        collector="C",
        endpoint="/x",
        status="success",
    )
    metrics.assert_counter_value(
        "meraki_span_requests",
        1,
        operation="op",
        collector="C",
        endpoint="/x",
        status="error",
    )
    metrics.assert_counter_value(
        "meraki_span_errors",
        1,
        operation="op",
        collector="C",
        endpoint="/x",
        error_type="ValueError",
    )
    metrics.assert_histogram_count(
        "meraki_span_duration_seconds",
        2,
        operation="op",
        collector="C",
        endpoint="/x",
    )


class _DummyTracerProvider:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add_span_processor(self, processor: Any) -> None:
        self.added.append(processor)


def test_setup_span_metrics_adds_processor() -> None:
    """``setup_span_metrics`` registers the processor with the provider."""

    registry = CollectorRegistry()
    provider = _DummyTracerProvider()
    processor = setup_span_metrics(provider, registry)

    assert isinstance(processor, SpanMetricsProcessor)
    assert provider.added == [processor]
