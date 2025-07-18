"""Helper functions for consistent structured logging patterns."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class LogContext:
    """Context manager for adding structured logging context.

    Examples
    --------
    with LogContext(org_id="123", network_id="456"):
        logger.info("Processing network")
        # All logs within this context will include org_id and network_id

    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with context fields."""
        self.context = kwargs
        self._token: Any = None

    def __enter__(self) -> LogContext:
        """Add context on entry."""
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Remove context on exit."""
        if self._token:
            structlog.contextvars.unbind_contextvars(*self.context.keys())


def log_api_error(operation: str, error: Exception, **context: Any) -> None:
    """Log API errors with consistent format and context.

    Parameters
    ----------
    operation : str
        The API operation that failed
    error : Exception
        The exception that was raised
    **context : Any
        Additional context (org_id, network_id, etc.)

    """
    error_info = {
        "operation": operation,
        "error_type": type(error).__name__,
        "error": str(error),
    }

    # Add status code if available (from requests exceptions)
    if hasattr(error, "response") and hasattr(error.response, "status_code"):
        error_info["status_code"] = error.response.status_code

    # Add all context
    error_info.update(context)

    # Determine log level based on error type
    if isinstance(error, (TimeoutError, ConnectionError)):
        logger.warning(f"API timeout/connection error: {operation}", **error_info)
    elif hasattr(error, "response") and hasattr(error.response, "status_code"):
        if error.response.status_code == 429:
            logger.warning(f"API rate limit hit: {operation}", **error_info)
        elif error.response.status_code == 404:
            logger.debug(f"API endpoint not found: {operation}", **error_info)
        elif 400 <= error.response.status_code < 500:
            logger.warning(f"API client error: {operation}", **error_info)
        else:
            logger.error(f"API server error: {operation}", **error_info)
    else:
        logger.error(f"API error: {operation}", **error_info)


def log_metric_collection_summary(
    collector_name: str, metrics_collected: int, duration_seconds: float, **stats: Any
) -> None:
    """Log a summary of metric collection with consistent format.

    Parameters
    ----------
    collector_name : str
        Name of the collector
    metrics_collected : int
        Number of metrics collected
    duration_seconds : float
        Time taken to collect metrics
    **stats : Any
        Additional statistics (devices_processed, api_calls_made, etc.)

    """
    summary = {
        "collector": collector_name,
        "metrics_collected": metrics_collected,
        "duration_seconds": round(duration_seconds, 3),
        "metrics_per_second": round(metrics_collected / duration_seconds, 2)
        if duration_seconds > 0
        else 0,
    }
    summary.update(stats)

    logger.debug(f"Collection summary: {collector_name}", **summary)


def log_batch_progress(operation: str, current: int, total: int, **context: Any) -> None:
    """Log progress through a batch operation.

    Parameters
    ----------
    operation : str
        Description of the operation
    current : int
        Current item number
    total : int
        Total number of items
    **context : Any
        Additional context

    """
    progress_info = {
        "operation": operation,
        "current": current,
        "total": total,
        "progress_percent": round((current / total) * 100, 1) if total > 0 else 0,
    }
    progress_info.update(context)

    # Log every 10% or every 100 items, whichever is smaller
    log_interval = min(max(1, total // 10), 100)
    if current % log_interval == 0 or current == total:
        logger.debug(f"Batch progress: {operation}", **progress_info)


def log_discovery_info(discovery_type: str, **info: Any) -> None:
    """Log discovery information at INFO level.

    Parameters
    ----------
    discovery_type : str
        Type of discovery (organization, network, device)
    **info : Any
        Discovery information to log

    """
    logger.info(f"Discovery: {discovery_type}", discovery_type=discovery_type, **info)


def format_bytes(bytes_value: int | float) -> str:
    """Format bytes into human-readable format.

    Parameters
    ----------
    bytes_value : int | float
        Number of bytes

    Returns
    -------
    str
        Human-readable format (e.g., "1.5 MB")

    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration into human-readable format.

    Parameters
    ----------
    seconds : float
        Duration in seconds

    Returns
    -------
    str
        Human-readable format (e.g., "1m 30s")

    """
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def create_collector_logger(collector_name: str) -> Any:
    """Create a logger with collector context pre-bound.

    Parameters
    ----------
    collector_name : str
        Name of the collector

    Returns
    -------
    Any
        Structlog logger with collector context

    Examples
    --------
    logger = create_collector_logger("DeviceCollector")
    logger.info("Starting collection")  # Will include collector="DeviceCollector"

    """
    return logger.bind(collector=collector_name)


# Structured logging message templates


class LogMessages:
    """Standard log message templates for consistency."""

    # API operations
    API_CALL_START = "Starting API call"
    API_CALL_SUCCESS = "API call completed"
    API_CALL_FAILED = "API call failed"

    # Collection operations
    COLLECTION_START = "Starting metric collection"
    COLLECTION_SUCCESS = "Metric collection completed"
    COLLECTION_FAILED = "Metric collection failed"

    # Batch operations
    BATCH_START = "Starting batch processing"
    BATCH_PROGRESS = "Batch processing progress"
    BATCH_COMPLETE = "Batch processing completed"

    # Discovery
    DISCOVERY_START = "Starting discovery"
    DISCOVERY_COMPLETE = "Discovery completed"

    # Metrics
    METRIC_UPDATE = "Metric updated"
    METRIC_ERROR = "Failed to update metric"


def log_with_context(
    level: str, message: str, collector: str | None = None, **context: Any
) -> None:
    """Log with automatic context extraction.

    Parameters
    ----------
    level : str
        Log level (debug, info, warning, error)
    message : str
        Log message
    collector : str, optional
        Collector name
    **context : Any
        Additional context

    """
    log_func = getattr(logger, level, logger.info)

    log_context = {}
    if collector:
        log_context["collector"] = collector

    # Add any non-None context values
    log_context.update({k: v for k, v in context.items() if v is not None})

    log_func(message, **log_context)
