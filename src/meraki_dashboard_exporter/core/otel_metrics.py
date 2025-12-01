"""OpenTelemetry metrics integration for Prometheus metric mirroring."""

from __future__ import annotations

import asyncio
import time
from enum import Enum
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


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, block requests
    HALF_OPEN = "half_open"  # Testing if recovered


class PrometheusToOTelBridge:
    """Bridge to automatically export Prometheus metrics to OpenTelemetry.

    Features:
    - Proper Prometheus registry collection via collect()
    - Metric/label allowlists and blocklists for filtering
    - Circuit breaker for OTEL endpoint failures
    - Exponential backoff on push failures
    - Failure tracking and recovery

    """

    def __init__(
        self,
        registry: CollectorRegistry,
        endpoint: str,
        service_name: str = "meraki-dashboard-exporter",
        export_interval_seconds: int = 60,
        resource_attributes: dict[str, str] | None = None,
        metric_allowlist: list[str] | None = None,
        metric_blocklist: list[str] | None = None,
        label_allowlist: list[str] | None = None,
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
        metric_allowlist : list[str] | None
            Only export metrics matching these prefixes (None = all).
        metric_blocklist : list[str] | None
            Never export metrics matching these prefixes (None = none blocked).
        label_allowlist : list[str] | None
            Only include these label names (None = all labels).

        """
        self.registry = registry
        self.endpoint = endpoint
        self.service_name = service_name
        self.export_interval = export_interval_seconds
        self._running = False
        self._sync_task: asyncio.Task[None] | None = None

        # Filtering configuration
        self.metric_allowlist = metric_allowlist or []
        self.metric_blocklist = metric_blocklist or []
        self.label_allowlist = set(label_allowlist) if label_allowlist else None

        # Circuit breaker state
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._circuit_open_time: float | None = None
        self._failure_threshold = 5  # Open circuit after 5 consecutive failures
        self._recovery_timeout = 60  # Try to recover after 60 seconds
        self._half_open_max_failures = 2  # Allow 2 failures in half-open before reopening

        # Backoff configuration
        self._backoff_multiplier = 2.0
        self._max_backoff: float = 300.0  # Max 5 minutes
        self._current_backoff: float = float(export_interval_seconds)

        # Metrics tracking
        self._total_exports = 0
        self._failed_exports = 0
        self._last_successful_export: float | None = None

        # Create resource with attributes
        resource_attrs = {
            "service.name": service_name,
            "service.version": "0.8.0",
        }
        if resource_attributes:
            resource_attrs.update(resource_attributes)

        resource = Resource.create(resource_attrs)

        # Set up OTLP exporter
        exporter = OTLPMetricExporter(
            endpoint=endpoint,
            insecure=True,
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
            "Initialized Prometheus to OpenTelemetry bridge with circuit breaker",
            endpoint=endpoint,
            service_name=service_name,
            export_interval=export_interval_seconds,
            metric_allowlist_count=len(self.metric_allowlist) if self.metric_allowlist else None,
            metric_blocklist_count=len(self.metric_blocklist) if self.metric_blocklist else None,
            label_filtering=bool(self.label_allowlist),
        )

    def _should_export_metric(self, metric_name: str) -> bool:
        """Check if a metric should be exported based on allowlist/blocklist.

        Parameters
        ----------
        metric_name : str
            Name of the metric to check.

        Returns
        -------
        bool
            True if metric should be exported.

        """
        # Check blocklist first (higher priority)
        if self.metric_blocklist:
            for blocked_prefix in self.metric_blocklist:
                if metric_name.startswith(blocked_prefix):
                    return False

        # Check allowlist
        if self.metric_allowlist:
            for allowed_prefix in self.metric_allowlist:
                if metric_name.startswith(allowed_prefix):
                    return True
            return False  # Not in allowlist

        return True  # No filtering, export everything

    def _filter_labels(self, labels: dict[str, str]) -> dict[str, str]:
        """Filter labels based on allowlist.

        Parameters
        ----------
        labels : dict[str, str]
            Original labels.

        Returns
        -------
        dict[str, str]
            Filtered labels.

        """
        if not self.label_allowlist:
            return labels

        return {k: v for k, v in labels.items() if k in self.label_allowlist}

    def _get_prometheus_metrics(self) -> None:
        """Collect all metrics from Prometheus registry using proper API."""
        new_cache: dict[str, list[tuple[dict[str, str], float]]] = {}
        histogram_data: dict[str, dict[str, float]] = {}

        try:
            # Use proper collect() method instead of private _collector_to_names
            for metric_family in self.registry.collect():
                # Check if metric should be exported
                if not self._should_export_metric(metric_family.name):
                    logger.debug(
                        "Skipping metric (filtered)",
                        metric_name=metric_family.name,
                    )
                    continue

                if metric_family.type == "histogram":
                    self._process_histogram_metric(metric_family, histogram_data)
                else:
                    self._process_regular_metric(metric_family, new_cache)

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

    def _process_regular_metric(
        self, metric: Any, new_cache: dict[str, list[tuple[dict[str, str], float]]]
    ) -> None:
        """Process non-histogram metric samples with label filtering."""
        metric_values = []
        for sample in metric.samples:
            # Skip created timestamps
            if sample.name.endswith("_created"):
                continue

            # Filter labels if allowlist is configured
            filtered_labels = self._filter_labels(sample.labels)

            # Store labels and value
            metric_values.append((filtered_labels, sample.value))

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
                self._otel_metrics[metric_name] = self.meter.create_observable_gauge(
                    name=metric_name,
                    callbacks=[callback],
                    description=documentation,
                    unit="1",
                )
            elif metric_type == "counter":
                self._otel_metrics[metric_name] = self.meter.create_observable_counter(
                    name=metric_name,
                    callbacks=[callback],
                    description=documentation,
                    unit="1",
                )
            elif metric_type == "histogram":
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

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operation.

        Returns
        -------
        bool
            True if operation should proceed, False if blocked by circuit.

        """
        current_time = time.time()

        if self._circuit_state == CircuitState.CLOSED:
            # Normal operation
            return True

        elif self._circuit_state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if (
                self._circuit_open_time
                and (current_time - self._circuit_open_time) >= self._recovery_timeout
            ):
                logger.info(
                    "Circuit breaker entering half-open state (testing recovery)",
                    failure_count=self._failure_count,
                    time_open=current_time - self._circuit_open_time,
                )
                self._circuit_state = CircuitState.HALF_OPEN
                self._failure_count = 0
                return True

            # Still in open state, block operation
            logger.debug(
                "Circuit breaker blocking OTEL export (open)",
                time_remaining=self._recovery_timeout
                - (current_time - (self._circuit_open_time or current_time)),
            )
            return False

        else:  # HALF_OPEN
            # Allow operation to test recovery
            return True

    def _record_success(self) -> None:
        """Record successful export."""
        self._total_exports += 1
        self._last_successful_export = time.time()
        self._failure_count = 0
        self._current_backoff = self.export_interval

        if self._circuit_state != CircuitState.CLOSED:
            logger.info(
                "Circuit breaker recovered (closing circuit)",
                previous_state=self._circuit_state.value,
                total_exports=self._total_exports,
                failed_exports=self._failed_exports,
            )
            self._circuit_state = CircuitState.CLOSED

    def _record_failure(self) -> None:
        """Record failed export and update circuit breaker state."""
        self._total_exports += 1
        self._failed_exports += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        # Update backoff
        self._current_backoff = min(
            self._current_backoff * self._backoff_multiplier,
            self._max_backoff,
        )

        if self._circuit_state == CircuitState.CLOSED:
            # Check if we should open circuit
            if self._failure_count >= self._failure_threshold:
                logger.error(
                    "Circuit breaker opening (too many failures)",
                    failure_count=self._failure_count,
                    failure_threshold=self._failure_threshold,
                    backoff_seconds=self._current_backoff,
                )
                self._circuit_state = CircuitState.OPEN
                self._circuit_open_time = time.time()

        elif self._circuit_state == CircuitState.HALF_OPEN:
            # Failed during recovery testing
            if self._failure_count >= self._half_open_max_failures:
                logger.warning(
                    "Circuit breaker reopening (recovery test failed)",
                    failure_count=self._failure_count,
                    recovery_timeout=self._recovery_timeout,
                )
                self._circuit_state = CircuitState.OPEN
                self._circuit_open_time = time.time()

    async def _sync_metrics(self) -> None:
        """Sync Prometheus metrics to OpenTelemetry with circuit breaker."""
        # Check circuit breaker
        if not self._check_circuit_breaker():
            return

        try:
            # Update metric cache from Prometheus
            self._get_prometheus_metrics()

            # Ensure OTEL metrics exist for all Prometheus metrics
            for metric_family in self.registry.collect():
                if self._should_export_metric(metric_family.name):
                    self._ensure_otel_metric(
                        metric_family.name,
                        metric_family.type,
                        metric_family.documentation,
                    )

            # Record success
            self._record_success()

            logger.debug(
                "Synced metrics to OpenTelemetry",
                prometheus_metrics=len(self._metric_cache),
                otel_metrics=len(self._otel_metrics),
                circuit_state=self._circuit_state.value,
            )

        except Exception as e:
            # Record failure
            self._record_failure()

            logger.error(
                "Failed to sync metrics to OpenTelemetry",
                error=str(e),
                error_type=type(e).__name__,
                failure_count=self._failure_count,
                circuit_state=self._circuit_state.value,
                backoff_seconds=self._current_backoff,
            )

    async def _sync_loop(self) -> None:
        """Periodically sync metrics with exponential backoff on failures."""
        while self._running:
            try:
                await self._sync_metrics()

                # Use current backoff interval (increases on failures)
                sleep_time = self._current_backoff / 2
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in OTEL sync loop")
                await asyncio.sleep(10)

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

        logger.info(
            "Started Prometheus to OpenTelemetry bridge with circuit breaker",
            export_interval=self.export_interval,
            failure_threshold=self._failure_threshold,
            recovery_timeout=self._recovery_timeout,
        )

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

        logger.info(
            "Stopped Prometheus to OpenTelemetry bridge",
            total_exports=self._total_exports,
            failed_exports=self._failed_exports,
            success_rate=(
                f"{(self._total_exports - self._failed_exports) / self._total_exports * 100:.1f}%"
                if self._total_exports > 0
                else "N/A"
            ),
        )

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about OTEL bridge performance.

        Returns
        -------
        dict[str, Any]
            Statistics including exports, failures, circuit state.

        """
        return {
            "total_exports": self._total_exports,
            "failed_exports": self._failed_exports,
            "success_rate": (
                (self._total_exports - self._failed_exports) / self._total_exports
                if self._total_exports > 0
                else 0.0
            ),
            "circuit_state": self._circuit_state.value,
            "failure_count": self._failure_count,
            "current_backoff": self._current_backoff,
            "last_successful_export": self._last_successful_export,
            "last_failure_time": self._last_failure_time,
            "metrics_cached": len(self._metric_cache),
            "otel_metrics_created": len(self._otel_metrics),
        }
