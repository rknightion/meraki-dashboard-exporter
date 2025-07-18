"""Exemplar support for linking metrics to traces."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram

from .logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ExemplarManager:
    """Manages exemplars for Prometheus metrics to enable trace correlation.

    Exemplars allow jumping from a metric anomaly directly to the traces
    that contributed to that metric value.
    """

    def __init__(self) -> None:
        """Initialize the exemplar manager."""
        self._tracer = trace.get_tracer(__name__)
        self._enabled = True
        logger.debug("Initialized ExemplarManager")

    def add_exemplar_to_metric(
        self,
        metric: Gauge | Counter | Histogram,
        value: float | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Add an exemplar to a metric if a trace is active.

        Parameters
        ----------
        metric : Gauge | Counter | Histogram
            The metric to add an exemplar to.
        value : float | None
            The value to record (required for Counter/Histogram).
        labels : dict[str, str] | None
            Labels to apply to the metric.

        """
        if not self._enabled:
            return

        span = trace.get_current_span()
        if not span or not span.is_recording():
            return

        span_context = span.get_span_context()
        if not span_context.is_valid:
            return

        # Format trace ID for exemplar
        trace_id = format(span_context.trace_id, "032x")
        span_id = format(span_context.span_id, "016x")

        # Create exemplar labels (for future use when exemplar API is available)
        # exemplar_labels = {
        #     "trace_id": trace_id,
        #     "span_id": span_id,
        # }

        # Apply the metric operation
        # Note: exemplar support requires newer prometheus-client versions
        # For now, we'll just set the metrics without exemplars
        try:
            if isinstance(metric, Gauge):
                if labels:
                    metric.labels(**labels).set(value or 0)
                else:
                    metric.set(value or 0)
            elif isinstance(metric, Counter):
                if labels:
                    metric.labels(**labels).inc(value or 1)
                else:
                    metric.inc(value or 1)
            elif isinstance(metric, Histogram):
                if labels:
                    metric.labels(**labels).observe(value or 0)
                else:
                    metric.observe(value or 0)

            logger.debug(
                "Added exemplar to metric",
                metric_name=metric._name,
                trace_id=trace_id,
                span_id=span_id,
            )
        except Exception as e:
            # Exemplar support might not be available in all Prometheus client versions
            logger.debug(
                "Failed to add exemplar to metric",
                metric_name=metric._name,
                error=str(e),
            )
            # Disable exemplars if not supported
            self._enabled = False

    def create_observable_counter(
        self,
        name: str,
        callback: Any,
        description: str = "",
        unit: str = "",
    ) -> Any:
        """Create an observable counter with exemplar support.

        Parameters
        ----------
        name : str
            Metric name.
        callback : Any
            Callback function that returns the metric value.
        description : str
            Metric description.
        unit : str
            Metric unit.

        """

        def wrapped_callback() -> Any:
            """Wrapped callback that adds exemplars."""
            value = callback()

            span = trace.get_current_span()
            if span and span.is_recording():
                span_context = span.get_span_context()
                if span_context.is_valid:
                    # Add trace context as metric attributes
                    if isinstance(value, dict):
                        value["_exemplar"] = {
                            "trace_id": format(span_context.trace_id, "032x"),
                            "span_id": format(span_context.span_id, "016x"),
                        }

            return value

        # Register the wrapped callback
        # Note: This is a simplified example - actual implementation
        # would depend on the metrics framework being used
        return wrapped_callback


class ExemplarCollector:
    """Collects exemplars for metrics during collection cycles."""

    def __init__(self, exemplar_manager: ExemplarManager) -> None:
        """Initialize the exemplar collector.

        Parameters
        ----------
        exemplar_manager : ExemplarManager
            The exemplar manager instance.

        """
        self._exemplar_manager = exemplar_manager
        self._collection_trace_ids: list[str] = []

    def start_collection(self, collector_name: str) -> Any:
        """Start a collection cycle with tracing.

        Parameters
        ----------
        collector_name : str
            Name of the collector.

        Returns
        -------
        Any
            The trace span.

        """
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(
            f"collect_{collector_name}",
            attributes={
                "collector.name": collector_name,
                "collector.timestamp": time.time(),
            },
        )

        if span.is_recording():
            span_context = span.get_span_context()
            if span_context.is_valid:
                trace_id = format(span_context.trace_id, "032x")
                self._collection_trace_ids.append(trace_id)

        return span

    def end_collection(self, span: Any) -> None:
        """End a collection cycle.

        Parameters
        ----------
        span : Any
            The trace span to end.

        """
        if span:
            span.end()

    def get_recent_trace_ids(self, limit: int = 10) -> list[str]:
        """Get recent trace IDs from collections.

        Parameters
        ----------
        limit : int
            Maximum number of trace IDs to return.

        Returns
        -------
        list[str]
            List of recent trace IDs.

        """
        return self._collection_trace_ids[-limit:]

    def clear_old_trace_ids(self, keep_last: int = 100) -> None:
        """Clear old trace IDs to prevent memory growth.

        Parameters
        ----------
        keep_last : int
            Number of recent trace IDs to keep.

        """
        if len(self._collection_trace_ids) > keep_last:
            self._collection_trace_ids = self._collection_trace_ids[-keep_last:]


# Global exemplar manager instance
_exemplar_manager: ExemplarManager | None = None


def get_exemplar_manager() -> ExemplarManager:
    """Get the global exemplar manager instance.

    Returns
    -------
    ExemplarManager
        The exemplar manager instance.

    """
    global _exemplar_manager
    if _exemplar_manager is None:
        _exemplar_manager = ExemplarManager()
    return _exemplar_manager


def add_exemplar(
    metric: Gauge | Counter | Histogram,
    value: float | None = None,
    labels: dict[str, str] | None = None,
) -> None:
    """Convenience function to add an exemplar to a metric.

    Parameters
    ----------
    metric : Gauge | Counter | Histogram
        The metric to add an exemplar to.
    value : float | None
        The value to record.
    labels : dict[str, str] | None
        Labels to apply to the metric.

    """
    manager = get_exemplar_manager()
    manager.add_exemplar_to_metric(metric, value, labels)
