"""Span-attribution + error-status regression tests for the tracing seam.

Covers the v1-sink tracing fixes:

- #645 ``trace_method`` auto-extracts ``org_id``/``network_id``/... from
  **positional** args (every real call site passes them positionally), not only
  from kwargs.
- #646 the ``collect.collector`` root span (``CollectorManager.
  _run_collector_with_timeout``) carries ``collector.name`` so it is
  identifiable without descending into the child ``collect.<Collector>`` span.
- #647 a collector failure the manager swallows (to let other collectors
  continue) still marks the ``collect.collector`` root span ``ERROR`` -- the
  ``trace_method`` wrapper must not clobber an ERROR status back to OK on the
  swallow-and-return path.
- #648 the ``collect.<Collector>`` span carries the owning scheduler
  ``EndpointGroupName``(s) as ``scheduler.endpoint_groups``.
"""

from __future__ import annotations

# ruff: noqa: S101
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from prometheus_client import CollectorRegistry
from pydantic import SecretStr

import meraki_dashboard_exporter.core.otel_tracing as ot
from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError
from meraki_dashboard_exporter.core.scheduler import EndpointGroup, EndpointGroupName


@pytest.fixture
def span_capture():
    """Route every ``trace.get_tracer`` through an in-memory-exported provider.

    ``otel_tracing.trace`` and ``core.collector.trace`` are the same
    ``opentelemetry.trace`` module object, so patching ``get_tracer`` on it
    captures spans from both the ``trace_method`` wrapper and ``collect()``.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with patch.object(ot.trace, "get_tracer", provider.get_tracer):
        yield exporter


def _one(exporter: InMemorySpanExporter, name: str):
    """Return the single finished span with ``name`` (fails if not exactly one)."""
    spans = [s for s in exporter.get_finished_spans() if s.name == name]
    assert len(spans) == 1, f"expected exactly one {name!r} span, got {len(spans)}"
    return spans[0]


# --------------------------------------------------------------------------- #
# #645 -- positional-arg auto-extraction
# --------------------------------------------------------------------------- #
class TestPositionalAttributeExtraction:
    """#645: positional org_id/network_id/... reach the span, not only kwargs."""

    async def test_positional_args_extracted(self, span_capture: InMemorySpanExporter) -> None:
        """org_id/org_name passed POSITIONALLY reach the span (the real call shape)."""

        class Fake:
            @ot.trace_method("process.organization")
            async def run(self, org_id: str, org_name: str) -> str:
                return "ok"

        await Fake().run("1019781", "Knight")

        span = _one(span_capture, "process.organization")
        assert span.attributes["org.id"] == "1019781"
        assert span.attributes["org.name"] == "Knight"
        assert span.attributes["class"] == "Fake"

    async def test_keyword_args_still_extracted(self, span_capture: InMemorySpanExporter) -> None:
        """The pre-existing kwargs path keeps working."""

        class Fake:
            @ot.trace_method("fetch.data")
            async def run(self, serial: str | None = None) -> None:
                return None

        await Fake().run(serial="Q2XX-XXXX-XXXX")

        span = _one(span_capture, "fetch.data")
        assert span.attributes["serial"] == "Q2XX-XXXX-XXXX"

    def test_sync_positional_args_extracted(self, span_capture: InMemorySpanExporter) -> None:
        """The sync wrapper binds positional args too."""

        class Fake:
            @ot.trace_method("sync.op")
            def run(self, network_id: str) -> None:
                return None

        Fake().run("N_123")

        span = _one(span_capture, "sync.op")
        assert span.attributes["network.id"] == "N_123"


# --------------------------------------------------------------------------- #
# #647 -- wrapper must not overwrite an ERROR status with OK
# --------------------------------------------------------------------------- #
class TestWrapperStatusPrecedence:
    """#647: the wrapper must not overwrite an ERROR body-status with OK."""

    async def test_success_sets_ok(self, span_capture: InMemorySpanExporter) -> None:
        """A clean return marks the span OK."""

        @ot.trace_method("x.ok")
        async def op() -> int:
            return 1

        await op()
        assert _one(span_capture, "x.ok").status.status_code is StatusCode.OK

    async def test_error_status_set_in_body_is_preserved(
        self, span_capture: InMemorySpanExporter
    ) -> None:
        """A body that marks the span ERROR then returns normally stays ERROR."""

        @ot.trace_method("x.err")
        async def op() -> None:
            ot.trace.get_current_span().set_status(
                ot.trace.Status(ot.trace.StatusCode.ERROR, "boom")
            )

        await op()
        assert _one(span_capture, "x.err").status.status_code is StatusCode.ERROR


# --------------------------------------------------------------------------- #
# manager / collector integration (#646, #647, #648)
# --------------------------------------------------------------------------- #
def _settings() -> Settings:
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    settings.api.smoothing_enabled = False
    return settings


@pytest.fixture
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    """Fresh registry for MetricCollector's class-level performance metrics."""
    registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", registry)
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.collector.MetricCollector._metrics_initialized", False
    )
    for attr in (
        "_collector_duration",
        "_collector_errors",
        "_collector_last_success",
        "_collector_api_calls",
    ):
        monkeypatch.setattr(
            f"meraki_dashboard_exporter.core.collector.MetricCollector.{attr}", None
        )
    return registry


class _StubCollector(MetricCollector):
    """Real MetricCollector whose _collect_impl can be toggled fail/succeed."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.should_fail = True
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def _initialize_metrics(self) -> None:
        pass

    async def _collect_impl(self) -> None:
        if self.should_fail:
            raise NothingCollectedError("Stub", attempted=1, failed=1)


class _GroupStub(MetricCollector):
    """Collector declaring a single endpoint group, for the #648 attribute."""

    def _initialize_metrics(self) -> None:
        pass

    async def _collect_impl(self) -> None:
        return None

    def get_endpoint_groups(self) -> tuple[EndpointGroup, ...]:
        return (
            EndpointGroup(
                name=EndpointGroupName.MT_SENSOR_READINGS,
                priority=2,
                floor_seconds=60,
                cost_fn=lambda _shape: 1.0,
            ),
        )


def _bare_manager(settings: Settings) -> CollectorManager:
    mock_client = MagicMock()
    mock_client.api = MagicMock()
    mock_client.get_successful_api_requests.return_value = 5
    with (
        patch.object(CollectorManager, "_initialize_collectors"),
        patch.object(CollectorManager, "_validate_collector_configuration"),
    ):
        return CollectorManager(client=mock_client, settings=settings)


def _register_stub(manager: CollectorManager, collector: MetricCollector, name: str) -> None:
    manager.collectors = [collector]
    manager.collector_health[name] = {
        "last_success_time": None,
        "failure_streak": 0,
        "total_runs": 0,
        "total_successes": 0,
        "total_failures": 0,
    }
    import asyncio

    manager._collector_locks[name] = asyncio.Lock()


class TestRootSpanAttribution:
    """#646/#647: the collect.collector root span is named + errors on failure."""

    async def test_failure_marks_root_span_error_and_named(
        self, span_capture: InMemorySpanExporter, isolated_registry: CollectorRegistry
    ) -> None:
        """A swallowed collector failure still errors the collect.collector root span."""
        settings = _settings()
        manager = _bare_manager(settings)
        collector = _StubCollector(api=MagicMock(), settings=settings, registry=isolated_registry)
        name = collector.__class__.__name__
        _register_stub(manager, collector, name)

        await manager.run_collector_once(collector)

        root = _one(span_capture, "collect.collector")
        assert root.attributes["collector.name"] == name  # #646
        assert root.status.status_code is StatusCode.ERROR  # #647

    async def test_success_root_span_ok_and_named(
        self, span_capture: InMemorySpanExporter, isolated_registry: CollectorRegistry
    ) -> None:
        """A successful run leaves the root span OK and carries collector.name."""
        settings = _settings()
        manager = _bare_manager(settings)
        collector = _StubCollector(api=MagicMock(), settings=settings, registry=isolated_registry)
        collector.should_fail = False
        name = collector.__class__.__name__
        _register_stub(manager, collector, name)

        await manager.run_collector_once(collector)

        root = _one(span_capture, "collect.collector")
        assert root.attributes["collector.name"] == name
        assert root.status.status_code is StatusCode.OK


class TestEndpointGroupSpanAttribute:
    """#648: the collect.<Collector> span exposes its scheduler endpoint groups."""

    async def test_collect_span_carries_endpoint_groups(
        self, span_capture: InMemorySpanExporter, isolated_registry: CollectorRegistry
    ) -> None:
        """The declared EndpointGroupName appears as scheduler.endpoint_groups."""
        settings = _settings()
        collector = _GroupStub(api=MagicMock(), settings=settings, registry=isolated_registry)

        await collector.collect()

        span = _one(span_capture, "collect._GroupStub")
        assert span.attributes["scheduler.endpoint_groups"] == "mt_sensor_readings"  # #648
