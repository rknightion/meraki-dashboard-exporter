"""OpenTelemetry tracing configuration and utilities."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from .logging import get_logger
from .span_metrics import setup_span_metrics

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .config import Settings

logger = get_logger(__name__)


class TracingConfig:
    """Configuration and setup for OpenTelemetry tracing."""

    def __init__(self, settings: Settings) -> None:
        """Initialize tracing configuration.

        Parameters
        ----------
        settings : Settings
            Application settings.

        """
        self.settings = settings
        self._tracer_provider: TracerProvider | None = None
        self._initialized = False

    def setup_tracing(self) -> None:
        """Set up OpenTelemetry tracing with all instrumentations."""
        if self._initialized:
            logger.warning("Tracing already initialized, skipping setup")
            return

        if not self.settings.otel.enabled or not self.settings.otel.endpoint:
            logger.info("OpenTelemetry tracing disabled (OTEL not enabled)")
            return

        try:
            # Create resource with service information
            resource = Resource.create({
                "service.name": self.settings.otel.service_name,
                "service.version": "0.8.0",
                "service.instance.id": os.getenv("HOSTNAME", "unknown"),
                "deployment.environment": self.settings.otel.resource_attributes.get(
                    "environment", "production"
                ),
            })

            # Configure sampling
            sampler = self._create_sampler()

            # Create tracer provider
            self._tracer_provider = TracerProvider(
                resource=resource,
                sampler=sampler,
            )

            # Configure OTLP exporter
            otlp_exporter = OTLPSpanExporter(
                endpoint=self.settings.otel.endpoint,
                insecure=True,  # For non-TLS endpoints
            )

            # Add span processor with batching
            span_processor = BatchSpanProcessor(
                otlp_exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                export_timeout_millis=30000,
            )
            self._tracer_provider.add_span_processor(span_processor)

            # Add span metrics processor for RED metrics
            from prometheus_client.core import REGISTRY

            setup_span_metrics(self._tracer_provider, REGISTRY)

            # Set as global tracer provider
            trace.set_tracer_provider(self._tracer_provider)

            # Set up context propagation
            set_global_textmap(TraceContextTextMapPropagator())

            # Instrument libraries
            self._instrument_libraries()

            self._initialized = True
            logger.info(
                "OpenTelemetry tracing initialized",
                endpoint=self.settings.otel.endpoint,
                service_name=self.settings.otel.service_name,
                sampling_rate=self._get_sampling_rate(),
            )

        except Exception:
            logger.exception("Failed to initialize OpenTelemetry tracing")

    def _create_sampler(self) -> Any:
        """Create appropriate sampler based on configuration.

        Returns
        -------
        Any
            OpenTelemetry sampler instance.

        """
        # Get sampling rate from environment or default
        sampling_rate = float(os.getenv("MERAKI_EXPORTER_OTEL__SAMPLING_RATE", "0.1"))

        if sampling_rate <= 0:
            return ALWAYS_OFF
        elif sampling_rate >= 1:
            return ALWAYS_ON
        else:
            # Use parent-based sampling with ratio for tail-based sampling
            return ParentBased(
                root=TraceIdRatioBased(sampling_rate),
                remote_parent_sampled=ALWAYS_ON,
                remote_parent_not_sampled=ALWAYS_OFF,
                local_parent_sampled=ALWAYS_ON,
                local_parent_not_sampled=ALWAYS_OFF,
            )

    def _get_sampling_rate(self) -> float:
        """Get the configured sampling rate.

        Returns
        -------
        float
            Sampling rate between 0 and 1.

        """
        return float(os.getenv("MERAKI_EXPORTER_OTEL__SAMPLING_RATE", "0.1"))

    def _instrument_libraries(self) -> None:
        """Instrument all relevant libraries for tracing."""
        # Instrument requests (used by Meraki SDK)
        RequestsInstrumentor().instrument(
            tracer_provider=self._tracer_provider,
            span_callback=self._requests_span_callback,
        )
        logger.debug("Instrumented requests library")

        # Instrument httpx (we use it, might as well trace it)
        HTTPXClientInstrumentor().instrument(
            tracer_provider=self._tracer_provider,
        )
        logger.debug("Instrumented httpx library")

        # Instrument threading (for asyncio.to_thread calls)
        ThreadingInstrumentor().instrument(
            tracer_provider=self._tracer_provider,
        )
        logger.debug("Instrumented threading")

        # Instrument logging to correlate logs with traces
        LoggingInstrumentor().instrument(
            tracer_provider=self._tracer_provider,
            set_logging_format=False,  # We have our own format
        )
        logger.debug("Instrumented logging")

    def _requests_span_callback(self, span: Any, response: Any) -> None:
        """Callback to enrich requests spans with additional attributes.

        Parameters
        ----------
        span : Any
            The span being recorded.
        response : Any
            The HTTP response object.

        """
        if span and response:
            # Add Meraki-specific attributes
            if hasattr(response, "headers"):
                # Add rate limit headers if present
                if "X-Request-Id" in response.headers:
                    span.set_attribute("meraki.request_id", response.headers["X-Request-Id"])
                if "Retry-After" in response.headers:
                    span.set_attribute("meraki.retry_after", response.headers["Retry-After"])
                if "X-Rate-Limit-Remaining" in response.headers:
                    span.set_attribute(
                        "meraki.rate_limit.remaining",
                        response.headers["X-Rate-Limit-Remaining"],
                    )

            # Add response size
            if hasattr(response, "content"):
                span.set_attribute("http.response.size", len(response.content))

    def instrument_fastapi(self, app: FastAPI) -> None:
        """Instrument FastAPI application.

        Parameters
        ----------
        app : FastAPI
            The FastAPI application to instrument.

        """
        if not self._initialized:
            return

        try:
            FastAPIInstrumentor().instrument_app(
                app,
                tracer_provider=self._tracer_provider,
                excluded_urls="/health,/metrics",  # Don't trace health/metrics endpoints
            )
            logger.debug("Instrumented FastAPI application")
        except Exception:
            logger.exception("Failed to instrument FastAPI")

    def get_tracer(self, name: str) -> Any:
        """Get a tracer instance.

        Parameters
        ----------
        name : str
            Name for the tracer (usually module name).

        Returns
        -------
        Any
            OpenTelemetry tracer instance.

        """
        if self._tracer_provider:
            return self._tracer_provider.get_tracer(name)
        return trace.get_tracer(name)

    def shutdown(self) -> None:
        """Shutdown tracing and flush any pending spans."""
        if self._tracer_provider and hasattr(self._tracer_provider, "shutdown"):
            try:
                self._tracer_provider.shutdown()
                logger.info("OpenTelemetry tracing shutdown complete")
            except Exception:
                logger.exception("Error shutting down tracing")


# Decorator for adding custom spans
def trace_method(name: str | None = None) -> Any:
    """Decorator to add tracing to methods.

    Parameters
    ----------
    name : str | None
        Optional span name, defaults to function name.

    Returns
    -------
    Any
        Decorated function.

    """

    def decorator(func: Any) -> Any:
        """Inner decorator."""
        import functools

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                """Async wrapper with tracing."""
                tracer = trace.get_tracer(__name__)
                span_name = name or f"{func.__module__}.{func.__name__}"

                with tracer.start_as_current_span(span_name) as span:
                    try:
                        # Add function arguments as span attributes
                        if args and hasattr(args[0], "__class__"):
                            span.set_attribute("class", args[0].__class__.__name__)

                        result = await func(*args, **kwargs)
                        span.set_status(trace.Status(trace.StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                """Sync wrapper with tracing."""
                tracer = trace.get_tracer(__name__)
                span_name = name or f"{func.__module__}.{func.__name__}"

                with tracer.start_as_current_span(span_name) as span:
                    try:
                        # Add function arguments as span attributes
                        if args and hasattr(args[0], "__class__"):
                            span.set_attribute("class", args[0].__class__.__name__)

                        result = func(*args, **kwargs)
                        span.set_status(trace.Status(trace.StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise

            return sync_wrapper

    return decorator
