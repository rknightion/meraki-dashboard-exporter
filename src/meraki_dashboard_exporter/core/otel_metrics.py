"""OTLP metrics bridge: push a periodic snapshot of the Prometheus registry (#339/#313).

This is a NEW, dedicated OTLP **metrics** channel — distinct from tracing
(``otel_tracing.py``) and the data-log emitter (``otel_data_logs.py``). It reads
the live ``prometheus_client`` ``REGISTRY`` on a timer, translates each metric
family into the OTLP metrics data model by hand, and ships it via
``OTLPMetricExporter.export``.

Design invariants
-----------------
- **Prometheus ``/metrics`` stays the sole, default metrics surface.** The bridge
  is strictly opt-in / off by default; enabling it does NOT change ``/metrics``
  output. The registry is the single source of truth — no OTel instruments are
  created, no ``MeterProvider`` exists, ``_create_gauge``/``_create_counter``/
  ``MetricExpirationManager`` are untouched. The only ``/metrics`` change when
  enabled is the four self-observability series this module registers (mirroring
  ``DataLogEmitter``: registered *only when enabled*).
- **Bespoke periodic snapshotter, no ``MeterProvider``.** There is no supported
  hook to feed foreign metric families through a ``MetricReader``; hand-building
  ``MetricsData`` gives byte-exact control over metric names (the whole of parity
  gap 4). See the frozen design spec for the full rationale.
- **Off by default / cheap no-op.** When ``otel.metrics.enabled`` is False the
  constructor logs and returns; ``start``/``stop`` no-op.

The OTLP metrics data model lives in the *public* ``opentelemetry.sdk.metrics.export``
namespace (no underscore-prefixed imports needed here, unlike the ``_logs`` SDK);
a Renovate major bump should re-run this module's unit tests as the canary.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    Gauge,
    Histogram,
    HistogramDataPoint,
    Metric,
    MetricExportResult,
    MetricsData,
    NumberDataPoint,
    ResourceMetrics,
    ScopeMetrics,
    Sum,
)
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from prometheus_client import CollectorRegistry, Counter
from prometheus_client import Gauge as PromGauge
from prometheus_client.core import REGISTRY

from ..__version__ import get_version
from .constants.metrics_constants import CollectorMetricName
from .logging import get_logger
from .metrics import LabelName
from .otel_tracing import build_otel_resource, build_otlp_credentials

if TYPE_CHECKING:
    from collections.abc import Iterable

    from opentelemetry.sdk.metrics.export import MetricExporter
    from prometheus_client.core import Metric as PrometheusMetricFamily

    from .config import Settings

logger = get_logger(__name__)

#: Instrumentation scope name for every pushed metric.
_SCOPE_NAME = "meraki_dashboard_exporter.otlp_metrics"

#: The heartbeat gauge name (parity gap 2). This family is ALWAYS included in a
#: push regardless of ``include`` mode — the single documented routing exemption.
HEARTBEAT_METRIC_NAME: str = CollectorMetricName.OTLP_METRICS_LAST_SUCCESS_TIMESTAMP.value

#: Cap so the SDK splits requests under gRPC's 4 MB limit for large fleets.
_MAX_EXPORT_BATCH_SIZE = 10_000

#: One-time debug-log dedupe for skipped Summary families (no OTLP Summary type).
_SUMMARY_WARNED: set[str] = set()


def _label_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Order-independent hashable key for a label set (for start-time matching)."""
    return tuple(sorted(labels.items()))


def _is_product_family(name: str) -> bool:
    """``product`` plane: ``meraki_*`` but not ``meraki_exporter_*``."""
    return name.startswith("meraki_") and not name.startswith("meraki_exporter_")


def _family_included(name: str, include: str) -> bool:
    """Whether a family is pushed under ``include``, honouring the heartbeat exemption."""
    if name == HEARTBEAT_METRIC_NAME:
        return True
    if include == "product":
        return _is_product_family(name)
    if include == "self":
        return not _is_product_family(name)
    return True  # "all"


def _number_point(
    labels: dict[str, str], value: float, *, start_unix_nano: int, now_unix_nano: int
) -> NumberDataPoint:
    return NumberDataPoint(
        attributes=dict(labels),
        start_time_unix_nano=start_unix_nano,
        time_unix_nano=now_unix_nano,
        value=value,
        exemplars=[],
    )


def _translate_counter(
    family: PrometheusMetricFamily, now_unix_nano: int, fallback_start_unix_nano: int
) -> Metric:
    """counter -> monotonic cumulative ``Sum`` named ``<name>_total``.

    ``start_time`` is the label-set's ``_created`` sample x 1e9 when present, else
    the bridge-start fallback. ``_created`` samples are consumed as start-times and
    never exported as their own series.
    """
    created: dict[tuple[tuple[str, str], ...], int] = {}
    for sample in family.samples:
        if sample.name.endswith("_created"):
            created[_label_key(sample.labels)] = int(sample.value * 1e9)

    points: list[NumberDataPoint] = []
    for sample in family.samples:
        if not sample.name.endswith("_total"):
            continue
        start = created.get(_label_key(sample.labels), fallback_start_unix_nano)
        points.append(
            _number_point(
                sample.labels, sample.value, start_unix_nano=start, now_unix_nano=now_unix_nano
            )
        )

    return Metric(
        name=f"{family.name}_total",
        description=family.documentation,
        unit="",
        data=Sum(
            data_points=points,
            aggregation_temporality=AggregationTemporality.CUMULATIVE,
            is_monotonic=True,
        ),
    )


def _translate_gauge_like(
    family: PrometheusMetricFamily, now_unix_nano: int, *, name: str, sample_name: str
) -> Metric:
    """gauge / unknown / info -> ``Gauge`` (start_time 0). Selects ``sample_name`` samples."""
    points = [
        _number_point(sample.labels, sample.value, start_unix_nano=0, now_unix_nano=now_unix_nano)
        for sample in family.samples
        if sample.name == sample_name
    ]
    return Metric(
        name=name,
        description=family.documentation,
        unit="",
        data=Gauge(data_points=points),
    )


@dataclass
class _HistGroup:
    """Accumulator for one histogram label-set while grouping registry samples."""

    labels: dict[str, str]
    start: int
    buckets: dict[str, float] = field(default_factory=dict)  # le -> cumulative count
    count: float | None = None
    total: float | None = None


def _translate_histogram(
    family: PrometheusMetricFamily, now_unix_nano: int, fallback_start_unix_nano: int
) -> Metric:
    """histogram -> cumulative OTLP ``Histogram`` with de-cumulated ``bucket_counts``.

    Prom ``le`` buckets are cumulative; OTLP ``bucket_counts`` are per-bucket.
    ``explicit_bounds`` = the ``le`` values excluding ``+Inf`` (its bucket becomes
    the final ``bucket_counts`` entry). ``count``/``sum`` from ``_count``/``_sum``;
    ``min``/``max`` = None; start-time from ``_created`` (else fallback).
    """
    groups: dict[tuple[tuple[str, str], ...], _HistGroup] = {}

    def _group(labels: dict[str, str]) -> _HistGroup:
        key = _label_key(labels)
        g = groups.get(key)
        if g is None:
            g = _HistGroup(labels=dict(labels), start=fallback_start_unix_nano)
            groups[key] = g
        return g

    for sample in family.samples:
        if sample.name.endswith("_bucket"):
            base = {k: v for k, v in sample.labels.items() if k != "le"}
            _group(base).buckets[sample.labels["le"]] = sample.value
        elif sample.name.endswith("_count"):
            _group(dict(sample.labels)).count = sample.value
        elif sample.name.endswith("_sum"):
            _group(dict(sample.labels)).total = sample.value
        elif sample.name.endswith("_created"):
            _group(dict(sample.labels)).start = int(sample.value * 1e9)

    points: list[HistogramDataPoint] = []
    for g in groups.values():
        les = sorted(g.buckets, key=lambda le: float("inf") if le == "+Inf" else float(le))
        bucket_counts: list[int] = []
        prev = 0.0
        for le in les:
            cumulative = g.buckets[le]
            bucket_counts.append(int(cumulative - prev))
            prev = cumulative
        explicit_bounds = [float(le) for le in les if le != "+Inf"]

        points.append(
            HistogramDataPoint(
                attributes=g.labels,
                start_time_unix_nano=g.start,
                time_unix_nano=now_unix_nano,
                count=int(g.count) if g.count is not None else int(prev),
                sum=g.total if g.total is not None else 0.0,
                bucket_counts=bucket_counts,
                explicit_bounds=explicit_bounds,
                min=None,  # type: ignore[arg-type]  # SDK uses None for absent min/max
                max=None,  # type: ignore[arg-type]
                exemplars=[],
            )
        )

    return Metric(
        name=family.name,
        description=family.documentation,
        unit="",
        data=Histogram(
            data_points=points,
            aggregation_temporality=AggregationTemporality.CUMULATIVE,
        ),
    )


def translate_families(
    families: Iterable[PrometheusMetricFamily],
    *,
    now_unix_nano: int,
    fallback_start_unix_nano: int,
    include: str,
) -> list[Metric]:
    """Translate ``prometheus_client`` metric families into OTLP ``Metric`` objects.

    Pure and deterministic (logging only). Routes each family by name prefix per
    ``include`` (with the heartbeat exemption), then applies the frozen
    translation table. ``Summary`` families are skipped (no OTLP Summary type)
    with a one-time debug log. ``Metric.unit`` is always ``""`` (our names embed
    units); ``Metric.description`` is the family documentation.

    Parameters
    ----------
    families : Iterable[PrometheusMetricFamily]
        Output of ``CollectorRegistry.collect()``.
    now_unix_nano : int
        Snapshot timestamp applied as every point's ``time_unix_nano``.
    fallback_start_unix_nano : int
        Start time for counter/histogram points lacking a ``_created`` sample
        (the bridge start time).
    include : str
        One of ``"product"``, ``"self"``, ``"all"``.

    Returns
    -------
    list[Metric]
        OTLP metrics ready to wrap in a ``ScopeMetrics``.

    """
    metrics: list[Metric] = []
    for family in families:
        if not _family_included(family.name, include):
            continue
        ftype = family.type
        if ftype == "counter":
            metrics.append(_translate_counter(family, now_unix_nano, fallback_start_unix_nano))
        elif ftype == "gauge":
            metrics.append(
                _translate_gauge_like(
                    family, now_unix_nano, name=family.name, sample_name=family.name
                )
            )
        elif ftype == "histogram":
            metrics.append(_translate_histogram(family, now_unix_nano, fallback_start_unix_nano))
        elif ftype == "info":
            info_name = f"{family.name}_info"
            metrics.append(
                _translate_gauge_like(family, now_unix_nano, name=info_name, sample_name=info_name)
            )
        elif ftype == "summary":
            if family.name not in _SUMMARY_WARNED:
                _SUMMARY_WARNED.add(family.name)
                logger.debug(
                    "Skipping Summary family in OTLP metrics bridge (no OTLP Summary type)",
                    family=family.name,
                )
        else:
            # unknown / untyped / anything else -> Gauge (best-effort).
            metrics.append(
                _translate_gauge_like(
                    family, now_unix_nano, name=family.name, sample_name=family.name
                )
            )
    return metrics


def _count_points(metrics_data: MetricsData) -> int:
    """Total data points across a ``MetricsData`` (for the exported-points counter)."""
    return sum(
        len(metric.data.data_points)
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
    )


class OTelMetricsBridge:
    """Periodically snapshots the Prometheus registry and pushes it via OTLP gRPC.

    Constructed once in ``ExporterApp``; ``start`` is called in lifespan startup
    (it needs the running loop) and ``stop`` in lifespan shutdown before the
    tracing/logging shutdowns so the final flush still has a live channel.

    Parameters
    ----------
    settings : Settings
        Application settings (reads ``settings.otel.metrics`` + resolved endpoint
        / insecure via ``settings.otel.metrics_endpoint`` / ``metrics_insecure``).
    registry : CollectorRegistry | None
        Prometheus registry to snapshot AND register the self-obs series on.
        Defaults to the global ``REGISTRY``.
    exporter : MetricExporter | None
        Test seam. When provided, used directly (tests pass a stub capturing
        ``MetricsData``). When None and enabled, a real ``OTLPMetricExporter`` is
        built lazily.

    """

    def __init__(
        self,
        settings: Settings,
        *,
        registry: CollectorRegistry | None = None,
        exporter: MetricExporter | None = None,
    ) -> None:
        """Build the bridge; a cheap no-op when ``otel.metrics.enabled`` is False."""
        self.settings = settings
        metrics_cfg = settings.otel.metrics
        self._enabled: bool = metrics_cfg.enabled
        self._include: str = metrics_cfg.include
        self._interval: int = metrics_cfg.export_interval_seconds
        self._registry: CollectorRegistry = registry if registry is not None else REGISTRY
        self._start_time_unix_nano: int = time.time_ns()

        self._exporter: MetricExporter | None = None
        self._task: asyncio.Task[None] | None = None
        self._last_dropped: int = 0

        self._exports_counter: Counter | None = None
        self._points_exported_counter: Counter | None = None
        self._points_dropped_counter: Counter | None = None
        self._heartbeat_gauge: PromGauge | None = None

        if not self._enabled:
            logger.info("OTel metrics bridge disabled (otel.metrics.enabled is False)")
            return

        reg = self._registry
        self._exports_counter = Counter(
            CollectorMetricName.OTLP_METRICS_EXPORTS_TOTAL.value,
            "OTLP metrics-bridge export attempts, by result status (#339/#313).",
            labelnames=[LabelName.STATUS.value],
            registry=reg,
        )
        self._points_exported_counter = Counter(
            CollectorMetricName.OTLP_METRICS_POINTS_EXPORTED_TOTAL.value,
            "Metric data points successfully shipped via the OTLP metrics bridge (#339/#313).",
            registry=reg,
        )
        self._points_dropped_counter = Counter(
            CollectorMetricName.OTLP_METRICS_POINTS_DROPPED_TOTAL.value,
            (
                "Metric data points dropped before export due to translation "
                "failures, best-effort (#339/#313)."
            ),
            registry=reg,
        )
        self._heartbeat_gauge = PromGauge(
            CollectorMetricName.OTLP_METRICS_LAST_SUCCESS_TIMESTAMP.value,
            (
                "Unix timestamp of the last successful OTLP metrics export; the "
                "OTLP-only liveness heartbeat (gap 2). Always pushed regardless "
                "of include mode."
            ),
            registry=reg,
        )

        self._setup_exporter(exporter)

    def _setup_exporter(self, exporter: MetricExporter | None) -> None:
        """Wire the exporter (test seam or real OTLP); self-disable on failure."""
        try:
            if exporter is not None:
                self._exporter = exporter
            else:
                # Import the OTLP exporter lazily so module import + pure tests
                # never hard-depend on the gRPC exporter package.
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter,
                )

                credentials = build_otlp_credentials(
                    self.settings.otel.ca_cert_path,
                    self.settings.otel.client_cert_path,
                    self.settings.otel.client_key_path,
                )
                self._exporter = OTLPMetricExporter(
                    endpoint=self.settings.otel.metrics_endpoint,
                    insecure=self.settings.otel.metrics_insecure,
                    credentials=credentials,
                    max_export_batch_size=_MAX_EXPORT_BATCH_SIZE,
                )
            logger.info(
                "OTel metrics bridge initialized",
                endpoint=self.settings.otel.metrics_endpoint,
                include=self._include,
                export_interval_seconds=self._interval,
            )
        except Exception:
            # Never let a misconfigured channel abort startup.
            logger.exception("Failed to initialize OTel metrics bridge; disabling")
            self._enabled = False
            self._exporter = None

    @property
    def enabled(self) -> bool:
        """Whether the bridge is live (enabled and an exporter constructed)."""
        return self._enabled and self._exporter is not None

    async def start(self) -> None:
        """Spawn the periodic export loop (lifespan startup). No-op when disabled."""
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        logger.info("OTel metrics bridge export loop started", interval=self._interval)

    async def stop(self) -> None:
        """Cancel the loop, do one final export (flush), and shut the exporter down."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if not self.enabled:
            return

        # One final export so the last interval's data is not lost.
        await self._export_once()
        try:
            await asyncio.to_thread(self._exporter.shutdown)  # type: ignore[union-attr]
            logger.info("OTel metrics bridge shutdown complete")
        except Exception:
            logger.exception("Error shutting down OTel metrics bridge exporter")

    async def _run(self) -> None:
        """Export every ``export_interval_seconds`` until cancelled."""
        while True:
            await asyncio.sleep(self._interval)
            await self._export_once()

    async def _export_once(self) -> None:
        """Snapshot + export once. Failures are logged and counted, never raised."""
        if not self.enabled:
            return

        try:
            metrics_data = await asyncio.to_thread(self._snapshot)
        except Exception:
            logger.exception("OTLP metrics snapshot failed")
            self._record_failure()
            return

        if self._last_dropped and self._points_dropped_counter is not None:
            self._points_dropped_counter.inc(self._last_dropped)

        try:
            result = await asyncio.to_thread(self._exporter.export, metrics_data)  # type: ignore[union-attr]
        except Exception:
            logger.exception("OTLP metrics export failed")
            self._record_failure()
            return

        if result == MetricExportResult.SUCCESS:
            self._record_success(metrics_data)
        else:
            logger.warning("OTLP metrics export returned a failure result")
            self._record_failure()

    def _record_success(self, metrics_data: MetricsData) -> None:
        if self._exports_counter is not None:
            self._exports_counter.labels(**{LabelName.STATUS.value: "success"}).inc()
        if self._points_exported_counter is not None:
            self._points_exported_counter.inc(_count_points(metrics_data))
        if self._heartbeat_gauge is not None:
            self._heartbeat_gauge.set(time.time())

    def _record_failure(self) -> None:
        if self._exports_counter is not None:
            self._exports_counter.labels(**{LabelName.STATUS.value: "failure"}).inc()

    def _snapshot(self) -> MetricsData:
        """Collect the registry, translate per-family (best-effort), wrap in MetricsData."""
        families = list(self._registry.collect())
        now = time.time_ns()
        metrics: list[Metric] = []
        dropped = 0
        for family in families:
            try:
                metrics.extend(
                    translate_families(
                        [family],
                        now_unix_nano=now,
                        fallback_start_unix_nano=self._start_time_unix_nano,
                        include=self._include,
                    )
                )
            except Exception:
                logger.debug(
                    "Failed to translate metric family for OTLP export", family=family.name
                )
                dropped += sum(1 for s in family.samples if not s.name.endswith("_created"))
        self._last_dropped = dropped

        scope = InstrumentationScope(_SCOPE_NAME, get_version())
        return MetricsData(
            resource_metrics=[
                ResourceMetrics(
                    resource=build_otel_resource(self.settings),
                    scope_metrics=[ScopeMetrics(scope=scope, metrics=metrics, schema_url="")],
                    schema_url="",
                )
            ]
        )
