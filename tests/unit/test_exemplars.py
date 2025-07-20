"""Tests for exemplar utilities."""

# ruff: noqa: S101

from opentelemetry import trace
from prometheus_client import Gauge

from meraki_dashboard_exporter.core.exemplars import (
    ExemplarCollector,
    ExemplarManager,
)


def test_add_exemplar_to_metric_with_active_span(monkeypatch):
    """Value is recorded when a span is active."""
    metric = Gauge("test_exemplar_metric", "desc")
    em = ExemplarManager()

    class DummySpan:
        def __init__(self) -> None:
            self.ended = False
            self._context = type("ctx", (), {"trace_id": 1, "span_id": 2, "is_valid": True})

        def is_recording(self) -> bool:
            return True

        def get_span_context(self):
            return self._context

        def end(self) -> None:
            self.ended = True

    class DummyTracer:
        def start_span(self, *args, **kwargs):
            return DummySpan()

    dummy_span = DummySpan()

    def fake_get_current_span() -> DummySpan:
        return dummy_span

    def fake_get_tracer(name: str) -> DummyTracer:
        return DummyTracer()

    monkeypatch.setattr(trace, "get_current_span", fake_get_current_span)
    monkeypatch.setattr(trace, "get_tracer", fake_get_tracer)

    em.add_exemplar_to_metric(metric, value=5)
    assert metric._value.get() == 5


def test_exemplar_collector_trace_id_management(monkeypatch):
    """Collector stores and trims trace IDs."""
    em = ExemplarManager()
    coll = ExemplarCollector(em)

    class DummySpan:
        def __init__(self) -> None:
            self.ended = False
            self._context = type("ctx", (), {"trace_id": 1, "span_id": 2, "is_valid": True})

        def is_recording(self) -> bool:
            return True

        def get_span_context(self):
            return self._context

        def end(self) -> None:
            self.ended = True

    class DummyTracer:
        def start_span(self, *args, **kwargs):
            return DummySpan()

    monkeypatch.setattr(trace, "get_tracer", lambda name: DummyTracer())

    span = coll.start_collection("devices")
    trace_id = coll.get_recent_trace_ids()[0]
    coll.end_collection(span)
    assert trace_id in coll.get_recent_trace_ids()

    # Add many spans
    for i in range(15):
        s = coll.start_collection(f"c{i}")
        coll.end_collection(s)
    coll.clear_old_trace_ids(keep_last=5)
    assert len(coll.get_recent_trace_ids(100)) <= 5
