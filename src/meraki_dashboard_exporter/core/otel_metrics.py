"""OpenTelemetry metrics integration for Prometheus metric mirroring."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from prometheus_client import CollectorRegistry

from .logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from opentelemetry.metrics import (
        Meter,
        ObservableCounter,
        ObservableGauge,
        ObservableUpDownCounter,
    )

logger = get_logger(__name__)


class PrometheusToOTelBridge:
    """Bridge to automatically export Prometheus metrics to OpenTelemetry."""

    def __init__(
        self,
        registry: CollectorRegistry,
        endpoint: str,
        service_name: str = "meraki-dashboard-exporter",
        export_interval_seconds: int = 60,
        resource_attributes: dict[str, str] | None = None,
    ) -> None:
        """Initialize the Prometheus to OpenTelemetry bridge.

        Parameters
        ----------
        registry : CollectorRegistry
            Prometheus registry to monitor for metrics.
        endpoint : str
            OTLP endpoint URL.
        service_name : str
            Service name for resource identification.
        export_interval_seconds : int
            How often to export metrics (in seconds).
        resource_attributes : dict[str, str] | None
            Additional resource attributes.

        """
        self.registry = registry
        self.endpoint = endpoint
        self.service_name = service_name
        self.export_interval = export_interval_seconds
        self._running = False
        self._sync_task: asyncio.Task[None] | None = None

        # Create resource with attributes
        resource_attrs = {
            "service.name": service_name,
            "service.version": "0.8.0",  # Match project version
        }
        if resource_attributes:
            resource_attrs.update(resource_attributes)

        resource = Resource.create(resource_attrs)

        # Set up OTLP exporter
        exporter = OTLPMetricExporter(
            endpoint=endpoint,
            insecure=True,  # Use insecure for non-TLS endpoints
        )

        # Create metric reader with specified interval
        reader = PeriodicExportingMetricReader(
            exporter=exporter,
            export_interval_millis=export_interval_seconds * 1000,
        )

        # Set up meter provider
        provider = MeterProvider(metric_readers=[reader], resource=resource)
        metrics.set_meter_provider(provider)

        # Get meter for creating metrics
        self.meter: Meter = metrics.get_meter(service_name)

        # Track created OTEL metrics to avoid recreation
        self._otel_metrics: dict[
            str, ObservableGauge | ObservableCounter | ObservableUpDownCounter
        ] = {}

        # Cache for latest Prometheus metric values
        self._metric_cache: dict[str, list[tuple[dict[str, str], float]]] = {}

        logger.info(
            "Initialized Prometheus to OpenTelemetry bridge",
            endpoint=endpoint,
            service_name=service_name,
            export_interval=export_interval_seconds,
        )

    def _get_prometheus_metrics(self) -> None:
        """Collect all metrics from Prometheus registry and cache values."""
        new_cache: dict[str, list[tuple[dict[str, str], float]]] = {}
        histogram_data: dict[str, dict[str, float]] = {}

        try:
            # Collect all metrics from Prometheus registry
            for collector in self.registry._collector_to_names:
                for metric in collector.collect():
                    if metric.type == "histogram":
                        self._process_histogram_metric(metric, histogram_data)
                    else:
                        self._process_regular_metric(metric, new_cache)

            # Add histogram averages to cache
            self._add_histogram_averages(histogram_data, new_cache)

            # Update cache
            self._metric_cache = new_cache

            logger.debug(
                "Updated Prometheus metric cache",
                metric_count=len(self._metric_cache),
                histogram_count=len(histogram_data),
            )

        except Exception:
            logger.exception("Error collecting Prometheus metrics")

    def _process_histogram_metric(
        self, metric: Any, histogram_data: dict[str, dict[str, float]]
    ) -> None:
        """Process histogram metric samples."""
        for sample in metric.samples:
            if sample.name.endswith("_sum"):
                histogram_data.setdefault(metric.name, {})["sum"] = sample.value
            elif sample.name.endswith("_count"):
                histogram_data.setdefault(metric.name, {})["count"] = sample.value
            # Note: We skip buckets for now as OTEL histograms work differently

    def _process_regular_metric(
        self, metric: Any, new_cache: dict[str, list[tuple[dict[str, str], float]]]
    ) -> None:
        """Process non-histogram metric samples."""
        metric_values = []
        # Process each sample in the metric
        for sample in metric.samples:
            # Skip created timestamps
            if sample.name.endswith("_created"):
                continue
            # Store labels and value
            metric_values.append((sample.labels, sample.value))

        if metric_values:
            new_cache[metric.name] = metric_values

    def _add_histogram_averages(
        self,
        histogram_data: dict[str, dict[str, float]],
        new_cache: dict[str, list[tuple[dict[str, str], float]]],
    ) -> None:
        """Add histogram averages to the cache."""
        for hist_name, hist_data in histogram_data.items():
            if "sum" in hist_data and "count" in hist_data and hist_data["count"] > 0:
                avg_value = hist_data["sum"] / hist_data["count"]
                new_cache[hist_name] = [({"_type": "histogram_avg"}, avg_value)]

    def _create_metric_callback(self, metric_name: str, metric_type: str) -> Any:
        """Create a callback function for an observable metric.

        Parameters
        ----------
        metric_name : str
            Name of the metric.
        metric_type : str
            Type of the metric (gauge, counter, etc).

        Returns
        -------
        Any
            Callback function for the observable metric.

        """

        def callback(options: CallbackOptions) -> Iterable[Observation]:
            """Callback to provide metric observations."""
            observations = []

            if metric_name in self._metric_cache:
                for labels, value in self._metric_cache[metric_name]:
                    observations.append(Observation(value, labels))

            return observations

        return callback

    def _ensure_otel_metric(self, metric_name: str, metric_type: str, documentation: str) -> None:
        """Ensure an OTEL metric exists for a Prometheus metric.

        Parameters
        ----------
        metric_name : str
            Name of the metric.
        metric_type : str
            Type of the metric.
        documentation : str
            Metric documentation.

        """
        if metric_name in self._otel_metrics:
            return

        callback = self._create_metric_callback(metric_name, metric_type)

        try:
            if metric_type in {"gauge", "info"}:
                # Gauges and info metrics use ObservableGauge
                self._otel_metrics[metric_name] = self.meter.create_observable_gauge(
                    name=metric_name,
                    callbacks=[callback],
                    description=documentation,
                    unit="1",
                )
            elif metric_type == "counter":
                # Counters use ObservableCounter
                self._otel_metrics[metric_name] = self.meter.create_observable_counter(
                    name=metric_name,
                    callbacks=[callback],
                    description=documentation,
                    unit="1",
                )
            elif metric_type == "histogram":
                # Histograms use ObservableGauge for average values
                # Note: This is a simplification - full histogram support would require
                # recording individual observations, not just averages
                self._otel_metrics[metric_name] = self.meter.create_observable_gauge(
                    name=metric_name,
                    callbacks=[callback],
                    description=f"{documentation} (average)",
                    unit="1",
                )
            else:
                logger.debug(
                    "Skipping unsupported metric type",
                    metric_name=metric_name,
                    metric_type=metric_type,
                )

        except Exception:
            logger.exception(
                "Error creating OTEL metric",
                metric_name=metric_name,
                metric_type=metric_type,
            )

    async def _sync_metrics(self) -> None:
        """Sync Prometheus metrics to OpenTelemetry."""
        # Update metric cache from Prometheus
        self._get_prometheus_metrics()

        # Ensure OTEL metrics exist for all Prometheus metrics
        for collector in self.registry._collector_to_names:
            for metric in collector.collect():
                self._ensure_otel_metric(metric.name, metric.type, metric.documentation)

        logger.debug(
            "Synced metrics to OpenTelemetry",
            prometheus_metrics=len(self._metric_cache),
            otel_metrics=len(self._otel_metrics),
        )

    async def _sync_loop(self) -> None:
        """Periodically sync metrics from Prometheus to OTEL cache."""
        while self._running:
            try:
                await self._sync_metrics()
                # Sync at half the export interval to ensure fresh data
                await asyncio.sleep(self.export_interval / 2)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in OTEL sync loop")
                await asyncio.sleep(10)  # Wait before retry

    async def start(self) -> None:
        """Start the metric sync process."""
        if self._running:
            logger.warning("Prometheus to OpenTelemetry bridge already running")
            return

        self._running = True

        # Do initial sync
        await self._sync_metrics()

        # Start background sync task
        self._sync_task = asyncio.create_task(self._sync_loop())

        logger.info("Started Prometheus to OpenTelemetry bridge")

    async def stop(self) -> None:
        """Stop the metric sync process."""
        if not self._running:
            return

        self._running = False

        # Cancel sync task
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped Prometheus to OpenTelemetry bridge")
