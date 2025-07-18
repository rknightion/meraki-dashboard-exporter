"""Span metrics processor for generating RED metrics from traces."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.trace import StatusCode
from prometheus_client import Counter, Histogram

from .logging import get_logger

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

logger = get_logger(__name__)


class SpanMetricsProcessor(SpanProcessor):
    """Generates RED (Rate, Errors, Duration) metrics from trace spans.

    This processor automatically creates Prometheus metrics from OpenTelemetry
    spans, providing visibility into request rates, error rates, and durations
    without requiring manual instrumentation.

    Parameters
    ----------
    registry : CollectorRegistry | None
        Prometheus registry to register metrics with.

    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize the span metrics processor."""
        from prometheus_client.core import REGISTRY

        self.registry = registry or REGISTRY
        self._initialize_metrics()
        logger.info("Initialized SpanMetricsProcessor for RED metrics generation")

    def _initialize_metrics(self) -> None:
        """Initialize RED metrics."""
        # Request rate metric
        self.span_requests_total = Counter(
            "meraki_span_requests_total",
            "Total number of requests tracked via spans",
            labelnames=["operation", "collector", "endpoint", "status"],
            registry=self.registry,
        )

        # Duration histogram
        self.span_duration_seconds = Histogram(
            "meraki_span_duration_seconds",
            "Request duration tracked via spans",
            labelnames=["operation", "collector", "endpoint"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
            registry=self.registry,
        )

        # Error counter
        self.span_errors_total = Counter(
            "meraki_span_errors_total",
            "Total number of errors tracked via spans",
            labelnames=["operation", "collector", "endpoint", "error_type"],
            registry=self.registry,
        )

    def on_start(self, span: Span, parent_context: Any | None = None) -> None:
        """Called when a span is started.

        Parameters
        ----------
        span : Span
            The span that was started.
        parent_context : Any | None
            The parent context.

        """
        # Record start time as span attribute for duration calculation
        span.set_attribute("span.start_time", time.time())

    def on_end(self, span: ReadableSpan) -> None:
        """Called when a span ends, generates metrics.

        Parameters
        ----------
        span : ReadableSpan
            The span that ended.

        """
        # Extract relevant attributes
        operation = span.name
        attributes = span.attributes or {}

        # Extract common labels
        collector = attributes.get("collector.name", "unknown")
        endpoint = attributes.get("api.endpoint", attributes.get("http.url", "unknown"))

        # Simplify endpoint URLs for cardinality control
        if isinstance(endpoint, str) and endpoint.startswith("http"):
            # Extract just the path portion
            try:
                from urllib.parse import urlparse

                parsed = urlparse(endpoint)
                endpoint = parsed.path or "/"
            except Exception:
                pass  # nosec B110 - URL parsing failure is non-critical

        # Determine status
        status = "success"
        error_type = None

        if span.status.status_code == StatusCode.ERROR:
            status = "error"
            # Try to determine error type from attributes or events
            error_type = attributes.get("error.type", "unknown")

            # Check events for exceptions
            for event in span.events:
                if event.name == "exception":
                    event_attrs = event.attributes or {}
                    error_type = event_attrs.get("exception.type", error_type)
                    break

        # Calculate duration
        if (
            hasattr(span, "end_time")
            and hasattr(span, "start_time")
            and span.end_time
            and span.start_time
        ):
            # Duration in seconds
            duration = (span.end_time - span.start_time) / 1e9  # Convert nanoseconds to seconds
        else:
            # Fallback to attribute if available
            start_time = attributes.get("span.start_time")
            if start_time and isinstance(start_time, (int, float)):
                duration = time.time() - start_time
            else:
                duration = 0

        # Skip very short spans (likely internal)
        if duration < 0.001 and not span.status.status_code == StatusCode.ERROR:
            return

        # Update metrics
        try:
            # Request counter
            self.span_requests_total.labels(
                operation=operation,
                collector=collector,
                endpoint=endpoint,
                status=status,
            ).inc()

            # Duration histogram (only for successful requests or all based on config)
            if status == "success" or True:  # Always record duration
                self.span_duration_seconds.labels(
                    operation=operation,
                    collector=collector,
                    endpoint=endpoint,
                ).observe(duration)

            # Error counter
            if status == "error":
                self.span_errors_total.labels(
                    operation=operation,
                    collector=collector,
                    endpoint=endpoint,
                    error_type=error_type or "unknown",
                ).inc()

            logger.debug(
                "Generated span metrics",
                operation=operation,
                collector=collector,
                endpoint=endpoint,
                status=status,
                duration=f"{duration:.3f}s",
                error_type=error_type,
            )

        except Exception as e:
            logger.exception("Failed to generate span metrics", error=str(e))

    def shutdown(self) -> None:
        """Shutdown the processor."""
        logger.debug("Shutting down SpanMetricsProcessor")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush any pending data.

        Parameters
        ----------
        timeout_millis : int
            Timeout in milliseconds.

        Returns
        -------
        bool
            True if successful.

        """
        return True


class SpanMetricsAggregator:
    """Aggregates span metrics to provide SLI/SLO metrics.

    This class provides higher-level metrics suitable for SLI/SLO monitoring
    by aggregating the raw span metrics.

    Parameters
    ----------
    registry : CollectorRegistry | None
        Prometheus registry to register metrics with.

    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize the span metrics aggregator."""
        from prometheus_client import Gauge
        from prometheus_client.core import REGISTRY

        self.registry = registry or REGISTRY

        # SLI metrics
        self.sli_availability = Gauge(
            "meraki_sli_availability",
            "Service Level Indicator for availability (success rate)",
            labelnames=["collector", "operation"],
            registry=self.registry,
        )

        self.sli_latency_seconds = Gauge(
            "meraki_sli_latency_seconds",
            "Service Level Indicator for latency",
            labelnames=["collector", "operation", "quantile"],
            registry=self.registry,
        )

        self.sli_error_rate = Gauge(
            "meraki_sli_error_rate",
            "Service Level Indicator for error rate",
            labelnames=["collector", "operation"],
            registry=self.registry,
        )

        logger.info("Initialized SpanMetricsAggregator for SLI metrics")

    def calculate_slis(self) -> None:
        """Calculate SLI metrics from span metrics.

        This should be called periodically to update SLI values.
        """
        # This is a placeholder - in a real implementation, you would:
        # 1. Query the span metrics from Prometheus
        # 2. Calculate success rates, latency percentiles, etc.
        # 3. Update the SLI gauges
        #
        # For now, we'll just log that this would be calculated
        logger.debug("SLI calculation would be performed here")


def setup_span_metrics(
    tracer_provider: Any, registry: CollectorRegistry | None = None
) -> SpanMetricsProcessor:
    """Set up span metrics generation.

    Parameters
    ----------
    tracer_provider : Any
        The OpenTelemetry tracer provider.
    registry : CollectorRegistry | None
        Prometheus registry to use.

    Returns
    -------
    SpanMetricsProcessor
        The configured span metrics processor.

    """
    processor = SpanMetricsProcessor(registry)
    tracer_provider.add_span_processor(processor)
    logger.info("Added SpanMetricsProcessor to tracer provider")
    return processor
