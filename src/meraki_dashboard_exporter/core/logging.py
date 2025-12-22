"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog
from structlog.types import EventDict, Processor

if TYPE_CHECKING:
    from .config import Settings

_LOGGING_CONFIGURED = False


def setup_logging(settings: Settings) -> None:
    """Configure structured logging with structlog using logfmt format.

    Parameters
    ----------
    settings : Settings
        Application settings containing log level.

    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.logging.level),
    )

    # Control third-party library logging
    # These libraries are used by the Meraki SDK and can be noisy
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # OpenTelemetry libraries can be chatty at INFO/DEBUG
    base_level = getattr(logging, settings.logging.level)
    if base_level == logging.DEBUG:
        otel_level = logging.DEBUG
    else:
        otel_level = max(logging.WARNING, base_level)
    for logger_name in (
        "opentelemetry",
        "opentelemetry.sdk",
        "opentelemetry.instrumentation",
        "opentelemetry.exporter",
    ):
        logging.getLogger(logger_name).setLevel(otel_level)

    # For Meraki SDK, respect DEBUG level but default to WARNING for INFO
    meraki_logger = logging.getLogger("meraki")
    if base_level == logging.DEBUG:
        meraki_level = logging.DEBUG
    else:
        meraki_level = max(logging.WARNING, base_level)
    meraki_logger.setLevel(meraki_level)

    # Configure Meraki logger to use structlog formatting
    # Remove any existing handlers first
    meraki_logger.handlers.clear()
    meraki_logger.propagate = False

    # Create a custom handler that uses structlog
    class StructlogHandler(logging.Handler):
        """Handler that formats logs using structlog."""

        def emit(self, record: logging.LogRecord) -> None:
            """Emit a log record using structlog."""
            logger = structlog.get_logger(record.name)
            # Map Python log levels to structlog methods
            level_map = {
                logging.DEBUG: logger.debug,
                logging.INFO: logger.info,
                logging.WARNING: logger.warning,
                logging.ERROR: logger.error,
                logging.CRITICAL: logger.critical,
            }
            log_method = level_map.get(record.levelno, logger.info)

            # Extract any extra fields from the record
            extra = {
                key: value
                for key, value in record.__dict__.items()
                if key
                not in {
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                }
            }

            # Log the message with any extra context
            log_method(record.getMessage(), **extra)

    # Add our custom handler to the Meraki logger
    meraki_logger.addHandler(StructlogHandler())

    # Only show httpx warnings and above (used by our code)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Control uvicorn logging - only show warnings and above unless in DEBUG mode
    if settings.logging.level != "DEBUG":
        logging.getLogger("uvicorn").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    # Processors for structlog with logfmt output
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.dict_tracebacks,
    ]

    # Add OTEL context processor if OTEL is enabled
    if settings.otel.enabled:
        processors.append(add_otel_context)

    # Add the final renderer
    processors.append(structlog.processors.LogfmtRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.logging.level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    _LOGGING_CONFIGURED = True


def add_otel_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add OpenTelemetry context to log entries.

    Parameters
    ----------
    logger : Any
        The logger instance.
    method_name : str
        The name of the log method called.
    event_dict : EventDict
        The event dictionary to process.

    Returns
    -------
    EventDict
        The processed event dictionary with OTEL context.

    """
    # This will be populated by OTEL instrumentation when enabled
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.is_recording():
        span_context = span.get_span_context()
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
        event_dict["trace_flags"] = format(span_context.trace_flags, "02x")

    return event_dict


def get_logger(name: str | None = None) -> Any:
    """Get a configured logger instance.

    Parameters
    ----------
    name : str | None
        Logger name, defaults to module name if not provided.

    Returns
    -------
    Any
        Configured logger instance.

    """
    return structlog.get_logger(name)
