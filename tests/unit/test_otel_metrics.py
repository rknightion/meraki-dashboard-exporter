"""Unit tests for the OTLP metrics bridge (#339/#313).

Covers the pure ``translate_families`` translation table, prefix routing +
heartbeat exemption, the async export loop against a stub ``MetricExporter``,
and the load-bearing sole-surface invariant: constructing the bridge must not
change ``/metrics`` output unless enabled, and when enabled only the four new
self-observability series may differ.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics.export import (
    Gauge,
    Histogram,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    Sum,
)
from prometheus_client import (
    REGISTRY as GLOBAL_REGISTRY,
)
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Info,
)
from prometheus_client import (
    Gauge as PromGauge,
)
from prometheus_client import (
    Histogram as PromHistogram,
)
from prometheus_client.exposition import generate_latest

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.otel_metrics import (
    OTelMetricsBridge,
    translate_families,
)
from meraki_dashboard_exporter.core.otel_tracing import build_otel_resource

HEARTBEAT = "meraki_exporter_otlp_metrics_last_success_timestamp_seconds"
EXPORTS_TOTAL = "meraki_exporter_otlp_metrics_exports_total"
POINTS_EXPORTED = "meraki_exporter_otlp_metrics_points_exported_total"
POINTS_DROPPED = "meraki_exporter_otlp_metrics_points_dropped_total"

NOW = 1_700_000_000_000_000_000  # arbitrary fixed now (unix nanos)
FALLBACK = 1_600_000_000_000_000_000  # arbitrary bridge-start fallback (unix nanos)


class _StubExporter(MetricExporter):
    """~10-line in-memory ``MetricExporter`` test seam capturing ``MetricsData``."""

    def __init__(self, result: MetricExportResult = MetricExportResult.SUCCESS) -> None:
        """Record the result the stub should return on export."""
        super().__init__()
        self.exported: list[MetricsData] = []
        self._result = result
        self.shutdown_called = False

    def export(
        self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: object
    ) -> MetricExportResult:
        """Capture the exported ``MetricsData`` and return the canned result."""
        self.exported.append(metrics_data)
        return self._result

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        """No-op flush."""
        return True

    def shutdown(self, timeout_millis: float = 30000, **kwargs: object) -> None:
        """Record that shutdown was called."""
        self.shutdown_called = True


def _settings(**metrics: object) -> Settings:
    """Build Settings with the given otel.metrics sub-block (api key stubbed)."""
    otel: dict[str, object] = {}
    if metrics:
        otel["metrics"] = metrics
    return Settings(meraki={"api_key": "a" * 40}, otel=otel)


def _metrics_by_name(metrics: list) -> dict[str, object]:
    """Index a list of OTLP ``Metric`` objects by name."""
    return {m.name: m for m in metrics}


# --------------------------------------------------------------------------- #
# Pure translation table
# --------------------------------------------------------------------------- #
class TestTranslateCounter:
    """counter -> monotonic cumulative Sum named ``<name>_total``."""

    def test_counter_maps_to_monotonic_cumulative_sum(self) -> None:
        """Counter becomes a monotonic cumulative Sum with _created-derived start."""
        reg = CollectorRegistry()
        c = Counter("meraki_reqs", "reqs", ["code"], registry=reg)
        c.labels(code="200").inc(5)

        # Grab the real _created start-time from the registry sample.
        created = next(
            s.value for fam in reg.collect() for s in fam.samples if s.name == "meraki_reqs_created"
        )

        metrics = translate_families(
            reg.collect(),
            now_unix_nano=NOW,
            fallback_start_unix_nano=FALLBACK,
            include="all",
        )
        by_name = _metrics_by_name(metrics)

        assert "meraki_reqs_total" in by_name
        # No _created series is ever emitted.
        assert "meraki_reqs_created" not in by_name

        m = by_name["meraki_reqs_total"]
        assert isinstance(m.data, Sum)
        assert m.data.is_monotonic is True
        assert m.data.aggregation_temporality.name == "CUMULATIVE"
        assert m.unit == ""  # noqa: PLC1901  (byte-equality with "" is the frozen invariant)
        assert m.description == "reqs"

        dp = m.data.data_points[0]
        assert dp.value == 5.0
        assert dp.attributes["code"] == "200"
        # start_time is the _created sample x 1e9.
        assert dp.start_time_unix_nano == int(created * 1e9)
        assert dp.time_unix_nano == NOW

    def test_counter_without_created_uses_fallback_start(self) -> None:
        """A counter point lacking a matching _created sample uses the fallback start."""
        reg = CollectorRegistry()
        c = Counter("meraki_widgets", "widgets", ["kind"], registry=reg)
        c.labels(kind="a").inc(1)
        families = list(reg.collect())
        # Strip the _created sample to force the fallback branch.
        fam = families[0]
        fam.samples = [s for s in fam.samples if not s.name.endswith("_created")]

        metrics = translate_families(
            [fam], now_unix_nano=NOW, fallback_start_unix_nano=FALLBACK, include="all"
        )
        dp = metrics[0].data.data_points[0]
        assert dp.start_time_unix_nano == FALLBACK


class TestTranslateGauge:
    """gauge -> Gauge with start_time 0."""

    def test_gauge_maps_to_gauge_zero_start(self) -> None:
        """Gauge becomes an OTLP Gauge with start_time 0 and empty unit."""
        reg = CollectorRegistry()
        g = PromGauge("meraki_temp", "temp", ["room"], registry=reg)
        g.labels(room="a").set(21.5)

        metrics = translate_families(
            reg.collect(), now_unix_nano=NOW, fallback_start_unix_nano=FALLBACK, include="all"
        )
        m = _metrics_by_name(metrics)["meraki_temp"]
        assert isinstance(m.data, Gauge)
        assert m.unit == ""  # noqa: PLC1901  (byte-equality with "" is the frozen invariant)
        dp = m.data.data_points[0]
        assert dp.value == 21.5
        assert dp.start_time_unix_nano == 0
        assert dp.time_unix_nano == NOW
        assert dp.attributes["room"] == "a"


class TestTranslateHistogram:
    """histogram -> cumulative Histogram with de-cumulated bucket_counts."""

    def test_histogram_decumulates_buckets(self) -> None:
        """Cumulative le buckets become per-bucket counts; +Inf excluded from bounds."""
        reg = CollectorRegistry()
        h = PromHistogram("meraki_lat", "lat", buckets=[0.1, 0.5, 1.0], registry=reg)
        h.observe(0.3)  # falls in (0.1, 0.5]
        h.observe(0.7)  # falls in (0.5, 1.0]

        metrics = translate_families(
            reg.collect(), now_unix_nano=NOW, fallback_start_unix_nano=FALLBACK, include="all"
        )
        m = _metrics_by_name(metrics)["meraki_lat"]
        assert isinstance(m.data, Histogram)
        assert m.data.aggregation_temporality.name == "CUMULATIVE"
        assert m.unit == ""  # noqa: PLC1901  (byte-equality with "" is the frozen invariant)

        dp = m.data.data_points[0]
        # cumulative le buckets 0.1:0, 0.5:1, 1.0:2, +Inf:2 -> per-bucket 0,1,1,0
        assert list(dp.bucket_counts) == [0, 1, 1, 0]
        assert list(dp.explicit_bounds) == [0.1, 0.5, 1.0]
        assert dp.count == 2
        assert dp.sum == pytest.approx(1.0)
        assert dp.min is None
        assert dp.max is None


class TestTranslateInfo:
    """info -> Gauge=1 named ``<name>_info``."""

    def test_info_maps_to_gauge_one(self) -> None:
        """Info becomes a Gauge valued 1 named ``<name>_info`` with labels as attrs."""
        reg = CollectorRegistry()
        i = Info("meraki_build", "build", registry=reg)
        i.info({"version": "1.2.3"})

        metrics = translate_families(
            reg.collect(), now_unix_nano=NOW, fallback_start_unix_nano=FALLBACK, include="all"
        )
        by_name = _metrics_by_name(metrics)
        assert "meraki_build_info" in by_name
        m = by_name["meraki_build_info"]
        assert isinstance(m.data, Gauge)
        dp = m.data.data_points[0]
        assert dp.value == 1
        assert dp.attributes["version"] == "1.2.3"


# --------------------------------------------------------------------------- #
# Routing partition + heartbeat exemption
# --------------------------------------------------------------------------- #
def _routing_registry() -> CollectorRegistry:
    """A registry seeded with one product, one exporter-self, one runtime, and heartbeat."""
    reg = CollectorRegistry()
    PromGauge("meraki_device_up", "product metric", registry=reg).set(1)
    PromGauge("meraki_exporter_collector_duration", "self metric", registry=reg).set(2)
    PromGauge("python_gc_objects", "runtime metric", registry=reg).set(3)
    PromGauge(HEARTBEAT, "heartbeat", registry=reg).set(4)
    return reg


class TestRouting:
    """Prefix routing for product/self/all and the heartbeat exemption."""

    def test_product_partition(self) -> None:
        """product = meraki_* excluding meraki_exporter_*; heartbeat still present."""
        metrics = translate_families(
            _routing_registry().collect(),
            now_unix_nano=NOW,
            fallback_start_unix_nano=FALLBACK,
            include="product",
        )
        names = set(_metrics_by_name(metrics))
        assert "meraki_device_up" in names
        assert "meraki_exporter_collector_duration" not in names
        assert "python_gc_objects" not in names
        # heartbeat always present (routing exemption)
        assert HEARTBEAT in names

    def test_self_partition(self) -> None:
        """self = meraki_exporter_* plus process/python runtime families."""
        metrics = translate_families(
            _routing_registry().collect(),
            now_unix_nano=NOW,
            fallback_start_unix_nano=FALLBACK,
            include="self",
        )
        names = set(_metrics_by_name(metrics))
        assert "meraki_device_up" not in names
        assert "meraki_exporter_collector_duration" in names
        assert "python_gc_objects" in names
        assert HEARTBEAT in names

    def test_all_partition(self) -> None:
        """all = product plus self."""
        metrics = translate_families(
            _routing_registry().collect(),
            now_unix_nano=NOW,
            fallback_start_unix_nano=FALLBACK,
            include="all",
        )
        names = set(_metrics_by_name(metrics))
        assert {
            "meraki_device_up",
            "meraki_exporter_collector_duration",
            "python_gc_objects",
        } <= names
        assert HEARTBEAT in names

    @pytest.mark.parametrize("include", ["product", "self", "all"])
    def test_heartbeat_present_under_all_modes(self, include: str) -> None:
        """The heartbeat gauge is present under every include mode."""
        metrics = translate_families(
            _routing_registry().collect(),
            now_unix_nano=NOW,
            fallback_start_unix_nano=FALLBACK,
            include=include,
        )
        assert HEARTBEAT in set(_metrics_by_name(metrics))


# --------------------------------------------------------------------------- #
# Bridge loop against the stub exporter
# --------------------------------------------------------------------------- #
class TestBridgeLoop:
    """Async export loop, self-obs counters, and shutdown behaviour."""

    def test_disabled_is_cheap_noop(self) -> None:
        """A disabled bridge reports not-enabled and builds no exporter."""
        reg = CollectorRegistry()
        bridge = OTelMetricsBridge(_settings(), registry=reg, exporter=_StubExporter())
        assert bridge.enabled is False

    async def test_export_once_success_moves_self_obs(self) -> None:
        """A successful export bumps success + points-exported and sets the heartbeat."""
        reg = CollectorRegistry()
        PromGauge("meraki_device_up", "up", registry=reg).set(1)
        exp = _StubExporter(MetricExportResult.SUCCESS)
        bridge = OTelMetricsBridge(
            _settings(enabled=True, endpoint="http://otel:4317"),
            registry=reg,
            exporter=exp,
        )
        assert bridge.enabled is True

        await bridge._export_once()

        assert len(exp.exported) == 1
        assert reg.get_sample_value(EXPORTS_TOTAL, {"status": "success"}) == 1.0
        assert (reg.get_sample_value(POINTS_EXPORTED) or 0) > 0
        assert (reg.get_sample_value(HEARTBEAT) or 0) > 0

    async def test_export_resource_matches_build_otel_resource(self) -> None:
        """The pushed resource attributes match ``build_otel_resource``."""
        reg = CollectorRegistry()
        settings = _settings(enabled=True, endpoint="http://otel:4317")
        exp = _StubExporter()
        bridge = OTelMetricsBridge(settings, registry=reg, exporter=exp)

        await bridge._export_once()

        pushed = exp.exported[0].resource_metrics[0].resource
        expected = build_otel_resource(settings)
        assert dict(pushed.attributes) == dict(expected.attributes)

    async def test_export_failure_result_counts_and_never_raises(self) -> None:
        """A FAILURE export result increments the failure counter and never raises."""
        reg = CollectorRegistry()
        exp = _StubExporter(MetricExportResult.FAILURE)
        bridge = OTelMetricsBridge(
            _settings(enabled=True, endpoint="http://otel:4317"),
            registry=reg,
            exporter=exp,
        )

        await bridge._export_once()  # must not raise

        assert reg.get_sample_value(EXPORTS_TOTAL, {"status": "failure"}) == 1.0
        assert reg.get_sample_value(EXPORTS_TOTAL, {"status": "success"}) is None

    async def test_export_exception_counts_failure_and_never_raises(self) -> None:
        """An exporter that raises is caught, counted as failure, and never propagates."""
        reg = CollectorRegistry()

        class _Boom(_StubExporter):
            def export(self, metrics_data, timeout_millis=10000, **kwargs):  # type: ignore[override]
                raise RuntimeError("collector down")

        bridge = OTelMetricsBridge(
            _settings(enabled=True, endpoint="http://otel:4317"),
            registry=reg,
            exporter=_Boom(),
        )

        await bridge._export_once()  # must not raise

        assert reg.get_sample_value(EXPORTS_TOTAL, {"status": "failure"}) == 1.0

    async def test_stop_does_final_export_and_shutdown(self) -> None:
        """stop() performs a final export and shuts the exporter down."""
        reg = CollectorRegistry()
        exp = _StubExporter()
        bridge = OTelMetricsBridge(
            _settings(enabled=True, endpoint="http://otel:4317"),
            registry=reg,
            exporter=exp,
        )
        await bridge.start()
        await bridge.stop()

        # stop() flushes at least one final export and shuts the exporter down.
        assert len(exp.exported) >= 1
        assert exp.shutdown_called is True

    async def test_start_stop_when_disabled_is_safe(self) -> None:
        """start()/stop() on a disabled bridge are safe no-ops."""
        reg = CollectorRegistry()
        bridge = OTelMetricsBridge(_settings(), registry=reg, exporter=_StubExporter())
        await bridge.start()
        await bridge.stop()  # must not raise


# --------------------------------------------------------------------------- #
# THE load-bearing sole-surface invariant
# --------------------------------------------------------------------------- #
class TestSoleSurfaceInvariant:
    """Constructing the bridge must not change ``/metrics`` unless enabled."""

    def test_disabled_bridge_does_not_change_metrics_output(self) -> None:
        """generate_latest is byte-identical before/after a disabled bridge."""
        before = generate_latest(GLOBAL_REGISTRY)
        OTelMetricsBridge(_settings())  # default registry == GLOBAL_REGISTRY, disabled
        after = generate_latest(GLOBAL_REGISTRY)
        assert before == after

    def test_enabled_bridge_only_adds_four_self_obs_series(self) -> None:
        """An enabled bridge adds exactly the four self-obs families and nothing else."""
        before_names = {fam.name for fam in GLOBAL_REGISTRY.collect()}
        OTelMetricsBridge(
            _settings(enabled=True, endpoint="http://otel:4317"),
            exporter=_StubExporter(),
        )
        after_names = {fam.name for fam in GLOBAL_REGISTRY.collect()}

        new = after_names - before_names
        assert new == {
            "meraki_exporter_otlp_metrics_exports",
            "meraki_exporter_otlp_metrics_points_exported",
            "meraki_exporter_otlp_metrics_points_dropped",
            "meraki_exporter_otlp_metrics_last_success_timestamp_seconds",
        }
