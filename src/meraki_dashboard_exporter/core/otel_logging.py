"""OpenTelemetry logging configuration for trace context correlation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from .logging import get_logger

if TYPE_CHECKING:
    from .config import Settings

logger = get_logger(__name__)


class OTELLoggingConfig:
    """Configuration for OpenTelemetry trace context in logs."""

    def __init__(self, settings: Settings) -> None:
        """Initialize OTEL logging configuration.

        Parameters
        ----------
        settings : Settings
            Application settings.

        """
        self.settings = settings
        self._initialized = False

    def setup_otel_logging(self) -> None:
        """Set up OpenTelemetry trace context in logs."""
        if self._initialized:
            logger.warning("OTEL logging already initialized, skipping setup")
            return

        if not self.settings.otel.enabled:
            logger.info("OpenTelemetry logging disabled (OTEL not enabled)")
            return

        # Note: Direct OTEL log export requires additional packages
        # For now, we just ensure trace context is added to logs
        self._initialized = True
        logger.info(
            "OpenTelemetry trace context enabled in logs",
            service_name=self.settings.otel.service_name,
        )

    def create_structlog_processor(self) -> Any:
        """Create a structlog processor that adds trace context.

        Returns
        -------
        Any
            Structlog processor function.

        """

        def add_trace_context(
            logger: Any, method_name: str, event_dict: dict[str, Any]
        ) -> dict[str, Any]:
            """Add trace context to log records.

            Parameters
            ----------
            logger : Any
                Logger instance.
            method_name : str
                Method name.
            event_dict : dict[str, Any]
                Event dictionary.

            Returns
            -------
            dict[str, Any]
                Updated event dictionary.

            """
            # Get current span
            span = trace.get_current_span()
            if span and span.is_recording():
                span_context = span.get_span_context()
                if span_context.is_valid:
                    # Add trace context
                    event_dict["trace_id"] = format(span_context.trace_id, "032x")
                    event_dict["span_id"] = format(span_context.span_id, "016x")
                    event_dict["trace_flags"] = format(span_context.trace_flags, "02x")

                    # Add span attributes if any
                    if hasattr(span, "attributes") and span.attributes:
                        # Add selected span attributes
                        for key, value in span.attributes.items():
                            if key.startswith("org.") or key.startswith("network."):
                                event_dict[f"span.{key}"] = value

            return event_dict

        return add_trace_context

    def shutdown(self) -> None:
        """Shutdown OTEL logging."""
        if self._initialized:
            logger.debug("OpenTelemetry logging context shutdown")

    def configure_structlog(self, processors: list[Any]) -> list[Any]:
        """Add OTEL processors to structlog configuration.

        Parameters
        ----------
        processors : list[Any]
            Existing structlog processors.

        Returns
        -------
        list[Any]
            Updated processor list.

        """
        if not self._initialized:
            return processors

        # Find where to insert our processors (before the final renderer)
        insert_index = len(processors) - 1

        # Insert trace context processor
        processors.insert(insert_index, self.create_structlog_processor())

        logger.info("Added OTEL trace context to structlog configuration")
        return processors
