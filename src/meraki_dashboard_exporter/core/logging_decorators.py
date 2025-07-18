"""Standardized logging decorators and helpers for consistent logging patterns."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast

import structlog

logger = structlog.get_logger()

P = ParamSpec("P")
R = TypeVar("R")


def log_api_call(
    operation: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to log API calls with consistent context.

    Parameters
    ----------
    operation : str
        The API operation name (e.g., "getOrganizationDevices")

    Returns
    -------
    Callable
        Decorated function with API call logging

    Examples
    --------
    @log_api_call("getOrganizationDevices")
    async def _fetch_devices(self, org_id: str) -> list[Device]:
        return await self.api.organizations.getOrganizationDevices(org_id)

    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Extract context from common parameters
            context = _extract_context(args, kwargs)

            # Log API call start
            logger.debug(f"API call: {operation}", operation=operation, **context)

            # Track the API call if collector has the method
            if hasattr(self, "_track_api_call"):
                self._track_api_call(operation)
            elif hasattr(self, "parent") and hasattr(self.parent, "_track_api_call"):
                self.parent._track_api_call(operation)

            start_time = time.time()
            try:
                result = await func(self, *args, **kwargs)  # type: ignore[misc]
                duration = time.time() - start_time

                # Log successful API call with result info
                result_info = _get_result_info(result)
                logger.debug(
                    f"API call completed: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    **context,
                    **result_info,
                )
                return cast(R, result)

            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"API call failed: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    error_type=type(e).__name__,
                    error=str(e),
                    **context,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Extract context from common parameters
            context = _extract_context(args, kwargs)

            # Log API call start
            logger.debug(f"API call: {operation}", operation=operation, **context)

            # Track the API call if collector has the method
            if hasattr(self, "_track_api_call"):
                self._track_api_call(operation)
            elif hasattr(self, "parent") and hasattr(self.parent, "_track_api_call"):
                self.parent._track_api_call(operation)

            start_time = time.time()
            try:
                result = func(self, *args, **kwargs)
                duration = time.time() - start_time

                # Log successful API call with result info
                result_info = _get_result_info(result)
                logger.debug(
                    f"API call completed: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    **context,
                    **result_info,
                )
                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"API call failed: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    error_type=type(e).__name__,
                    error=str(e),
                    **context,
                )
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        else:
            return cast(Callable[P, R], sync_wrapper)

    return decorator


def log_collection_progress(
    description: str, total_field: str = "total", current_field: str = "current"
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to log collection progress for batch operations.

    Parameters
    ----------
    description : str
        Description of what's being collected (e.g., "devices", "networks")
    total_field : str, optional
        Field name containing total count (default: "total")
    current_field : str, optional
        Field name containing current count (default: "current")

    Returns
    -------
    Callable
        Decorated function with progress logging

    Examples
    --------
    @log_collection_progress("switch ports")
    async def _process_switch_ports(self, serial: str, ports: list, current: int, total: int):
        # Process ports...

    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Extract counts from kwargs
            total = kwargs.get(total_field)
            current = kwargs.get(current_field)

            if total is not None and current is not None:
                # Cast to float for division
                total_val = float(cast(int | float, total))
                current_val = float(cast(int | float, current))
                logger.debug(
                    f"Processing {description}",
                    description=description,
                    current=current,
                    total=total,
                    progress_percent=round((current_val / total_val) * 100, 1)
                    if total_val > 0
                    else 0,
                )

            result = await func(self, *args, **kwargs)  # type: ignore[misc]
            return cast(R, result)

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Extract counts from kwargs
            total = kwargs.get(total_field)
            current = kwargs.get(current_field)

            if total is not None and current is not None:
                # Cast to float for division
                total_val = float(cast(int | float, total))
                current_val = float(cast(int | float, current))
                logger.debug(
                    f"Processing {description}",
                    description=description,
                    current=current,
                    total=total,
                    progress_percent=round((current_val / total_val) * 100, 1)
                    if total_val > 0
                    else 0,
                )

            return func(self, *args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        else:
            return cast(Callable[P, R], sync_wrapper)

    return decorator


def log_metric_update(metric_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to log metric updates with consistent format.

    Parameters
    ----------
    metric_name : str
        The name of the metric being updated

    Returns
    -------
    Callable
        Decorated function with metric update logging

    Examples
    --------
    @log_metric_update("device_status")
    def _update_device_status(self, serial: str, status: str):
        # Update metric...

    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Extract metric value and labels from args/kwargs
            value = None
            labels: dict[str, Any] = {}

            # Try to extract value (usually first arg after self)
            if args:
                value = args[0]

            # Extract label context
            if "labels" in kwargs:
                labels = cast(dict[str, Any], kwargs["labels"])
            else:
                # Common label names to extract
                for label_name in ["serial", "name", "org_id", "network_id", "type", "status"]:
                    if label_name in kwargs:
                        labels[label_name] = kwargs[label_name]

            result = await func(self, *args, **kwargs)  # type: ignore[misc]

            # Log the metric update
            logger.debug(
                f"Metric updated: {metric_name}", metric_name=metric_name, value=value, **labels
            )

            return cast(R, result)

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Extract metric value and labels from args/kwargs
            value = None
            labels: dict[str, Any] = {}

            # Try to extract value (usually first arg after self)
            if args:
                value = args[0]

            # Extract label context
            if "labels" in kwargs:
                labels = cast(dict[str, Any], kwargs["labels"])
            else:
                # Common label names to extract
                for label_name in ["serial", "name", "org_id", "network_id", "type", "status"]:
                    if label_name in kwargs:
                        labels[label_name] = kwargs[label_name]

            result = func(self, *args, **kwargs)

            # Log the metric update
            logger.debug(
                f"Metric updated: {metric_name}", metric_name=metric_name, value=value, **labels
            )

            return result

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        else:
            return cast(Callable[P, R], sync_wrapper)

    return decorator


def log_collector_discovery(collector_type: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for one-time discovery logging at INFO level.

    Parameters
    ----------
    collector_type : str
        Type of discovery (e.g., "organization", "device", "network")

    Returns
    -------
    Callable
        Decorated function with discovery logging

    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            logger.info(f"Starting {collector_type} discovery", collector_type=collector_type)
            result = await func(self, *args, **kwargs)  # type: ignore[misc]

            # Log discovery summary
            summary = _get_discovery_summary(collector_type, result)
            if summary:
                logger.info(
                    f"Completed {collector_type} discovery",
                    collector_type=collector_type,
                    **summary,
                )

            return cast(R, result)

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            logger.info(f"Starting {collector_type} discovery", collector_type=collector_type)
            result = func(self, *args, **kwargs)

            # Log discovery summary
            summary = _get_discovery_summary(collector_type, result)
            if summary:
                logger.info(
                    f"Completed {collector_type} discovery",
                    collector_type=collector_type,
                    **summary,
                )

            return result

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        else:
            return cast(Callable[P, R], sync_wrapper)

    return decorator


# Helper functions


def _extract_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extract common context parameters from function arguments."""
    context = {}

    # Extract from kwargs first (more reliable)
    for key in ["org_id", "network_id", "serial", "device_id", "name", "type"]:
        if key in kwargs:
            context[key] = kwargs[key]

    # Try to extract org_id from first positional arg if not in kwargs
    if "org_id" not in context and args and isinstance(args[0], str):
        # Check if it looks like an org ID
        if args[0].startswith(("org_", "O_")) or len(args[0]) == 18:
            context["org_id"] = args[0]

    return context


def _get_result_info(result: Any) -> dict[str, Any]:
    """Extract information about API call results."""
    info: dict[str, Any] = {}

    if result is None:
        info["result"] = "none"
    elif isinstance(result, list):
        info["result_count"] = len(result)
        info["result_type"] = "list"
    elif isinstance(result, dict):
        info["result_type"] = "dict"
        if "items" in result:
            info["result_count"] = len(result["items"])
    else:
        info["result_type"] = type(result).__name__

    return info


def _get_discovery_summary(collector_type: str, result: Any) -> dict[str, Any]:
    """Generate summary information for discovery results."""
    summary: dict[str, Any] = {}

    if result is None:
        return summary

    if collector_type == "organization" and isinstance(result, list):
        summary["organization_count"] = len(result)
        summary["organization_ids"] = [org.get("id", "") for org in result]
    elif collector_type == "device" and isinstance(result, dict):
        summary["total_devices"] = result.get("total", 0)
        if "by_type" in result:
            summary["devices_by_type"] = result["by_type"]
    elif collector_type == "network" and isinstance(result, list):
        summary["network_count"] = len(result)
        # Group by product type
        by_type: dict[str, int] = {}
        for net in result:
            for prod_type in net.get("productTypes", []):
                by_type[prod_type] = by_type.get(prod_type, 0) + 1
        if by_type:
            summary["networks_by_type"] = by_type

    return summary


# Additional helper for batch operations


def log_batch_operation(
    operation: str, batch_size: int | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log batch operations with consistent format.

    Parameters
    ----------
    operation : str
        Description of the batch operation
    batch_size : int, optional
        Size of the batch (if known)

    Returns
    -------
    Callable
        Decorated function with batch operation logging

    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Try to get batch size from kwargs if not provided
            actual_batch_size = batch_size or kwargs.get("batch_size")

            # Extract items count
            items = args[0] if args else kwargs.get("items", [])
            item_count = len(items) if hasattr(items, "__len__") else "unknown"

            logger.debug(
                f"Starting batch operation: {operation}",
                operation=operation,
                item_count=item_count,
                batch_size=actual_batch_size,
            )

            start_time = time.time()
            try:
                result = await func(self, *args, **kwargs)  # type: ignore[misc]
                duration = time.time() - start_time

                logger.debug(
                    f"Completed batch operation: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    item_count=item_count,
                    batch_size=actual_batch_size,
                )

                return cast(R, result)
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"Batch operation failed: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    error_type=type(e).__name__,
                    error=str(e),
                    item_count=item_count,
                    batch_size=actual_batch_size,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            # Try to get batch size from kwargs if not provided
            actual_batch_size = batch_size or kwargs.get("batch_size")

            # Extract items count
            items = args[0] if args else kwargs.get("items", [])
            item_count = len(items) if hasattr(items, "__len__") else "unknown"

            logger.debug(
                f"Starting batch operation: {operation}",
                operation=operation,
                item_count=item_count,
                batch_size=actual_batch_size,
            )

            start_time = time.time()
            try:
                result = func(self, *args, **kwargs)
                duration = time.time() - start_time

                logger.debug(
                    f"Completed batch operation: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    item_count=item_count,
                    batch_size=actual_batch_size,
                )

                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"Batch operation failed: {operation}",
                    operation=operation,
                    duration_seconds=round(duration, 3),
                    error_type=type(e).__name__,
                    error=str(e),
                    item_count=item_count,
                    batch_size=actual_batch_size,
                )
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        else:
            return cast(Callable[P, R], sync_wrapper)

    return decorator
