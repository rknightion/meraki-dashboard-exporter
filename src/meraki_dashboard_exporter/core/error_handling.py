"""Standardized error handling utilities for collectors.

This module provides decorators and utilities for consistent error handling,
retry logic, and error tracking across all collectors.
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from ..core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class ErrorCategory(StrEnum):
    """Categories of errors for tracking and handling."""

    API_RATE_LIMIT = "api_rate_limit"
    API_CLIENT_ERROR = "api_client_error"
    API_SERVER_ERROR = "api_server_error"
    API_NOT_AVAILABLE = "api_not_available"
    TIMEOUT = "timeout"
    PARSING = "parsing"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class CollectorError(Exception):
    """Base exception for collector-specific errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize collector error.

        Parameters
        ----------
        message : str
            Error message.
        category : ErrorCategory
            Category of the error for tracking.
        context : dict[str, Any] | None
            Additional context for debugging.

        """
        super().__init__(message)
        self.category = category
        self.context = context or {}


class APINotAvailableError(CollectorError):
    """Raised when an API endpoint is not available (404)."""

    def __init__(self, endpoint: str, context: dict[str, Any] | None = None) -> None:
        """Initialize API not available error."""
        super().__init__(
            f"API endpoint '{endpoint}' not available",
            ErrorCategory.API_NOT_AVAILABLE,
            context,
        )


class DataValidationError(CollectorError):
    """Raised when API response data doesn't match expected format."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize data validation error."""
        super().__init__(message, ErrorCategory.VALIDATION, context)


def with_error_handling(
    *,
    operation: str,
    continue_on_error: bool = True,
    error_category: ErrorCategory | None = None,
) -> Callable[[Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T | None]]]:
    """Decorator for standardized error handling on collector methods.

    Parameters
    ----------
    operation : str
        Description of the operation for logging.
    continue_on_error : bool
        Whether to continue execution on error (return None) or re-raise.
    error_category : ErrorCategory | None
        Category to use for errors, if known.

    Returns
    -------
    Callable
        Decorated function with error handling.

    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
            start_time = time.time()

            # Extract context from self if available
            context = {}
            if args and hasattr(args[0], "__class__"):
                self = args[0]
                if hasattr(self, "__class__"):
                    context["collector"] = self.__class__.__name__
                if hasattr(self, "update_tier"):
                    context["tier"] = self.update_tier.value

            try:
                result = await func(*args, **kwargs)

                # Log successful operation at debug level
                duration = time.time() - start_time
                logger.debug(
                    f"{operation} completed successfully",
                    duration_seconds=round(duration, 2),
                    **context,
                )

                return result

            except TimeoutError as e:
                # Create a new context dict with the duration
                error_context: dict[str, Any] = dict(context)
                error_context["duration_seconds"] = round(time.time() - start_time, 2)
                logger.error(
                    f"{operation} timed out",
                    error_type="TimeoutError",
                    **error_context,
                )

                # Track error metric if collector available
                if args and isinstance(args[0], object) and hasattr(args[0], "_track_error"):
                    args[0]._track_error(ErrorCategory.TIMEOUT)

                if continue_on_error:
                    return None
                raise CollectorError(
                    f"{operation} timed out",
                    ErrorCategory.TIMEOUT,
                    error_context,
                ) from e

            except Exception as e:
                duration = time.time() - start_time
                error_type = type(e).__name__
                error_msg = str(e)

                # Determine error category
                category = error_category or _categorize_error(e)

                # Create new context with mixed types
                exc_context: dict[str, Any] = dict(context)
                exc_context.update({
                    "duration_seconds": round(duration, 2),
                    "error_type": error_type,
                    "error": error_msg,
                })

                # Special handling for 404 errors
                if "404" in error_msg:
                    logger.debug(
                        f"{operation} - API endpoint not available",
                        **exc_context,
                    )
                    category = ErrorCategory.API_NOT_AVAILABLE
                else:
                    logger.exception(
                        f"{operation} failed",
                        **exc_context,
                    )

                # Track error metric if collector available
                if args and isinstance(args[0], object) and hasattr(args[0], "_track_error"):
                    args[0]._track_error(category)

                if continue_on_error:
                    return None

                # Re-raise as CollectorError with context
                raise CollectorError(
                    f"{operation} failed: {error_msg}",
                    category,
                    context,
                ) from e

        return wrapper

    return decorator


def _categorize_error(error: Exception) -> ErrorCategory:
    """Categorize an error based on its type and message.

    Parameters
    ----------
    error : Exception
        The error to categorize.

    Returns
    -------
    ErrorCategory
        The category of the error.

    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Check for specific error patterns
    if "429" in error_str or "rate limit" in error_str:
        return ErrorCategory.API_RATE_LIMIT
    elif "404" in error_str or "not found" in error_str:
        return ErrorCategory.API_NOT_AVAILABLE
    elif any(code in error_str for code in ["400", "401", "403", "405", "406"]):
        return ErrorCategory.API_CLIENT_ERROR
    elif any(code in error_str for code in ["500", "502", "503", "504"]):
        return ErrorCategory.API_SERVER_ERROR
    elif error_type == "TimeoutError" or "timeout" in error_str:
        return ErrorCategory.TIMEOUT
    elif "parsing" in error_str or "json" in error_str:
        return ErrorCategory.PARSING
    elif "validation" in error_str or "invalid" in error_str:
        return ErrorCategory.VALIDATION
    else:
        return ErrorCategory.UNKNOWN


def validate_response_format(
    response: Any,
    expected_type: type,
    operation: str,
) -> Any:
    """Validate API response format and extract data.

    Parameters
    ----------
    response : Any
        The API response to validate.
    expected_type : type
        Expected type of the response (list or dict).
    operation : str
        Description of the operation for error messages.

    Returns
    -------
    Any
        The validated response data.

    Raises
    ------
    DataValidationError
        If response format is unexpected.

    """
    # Handle wrapped responses
    if isinstance(response, dict) and "items" in response:
        data = response["items"]
    else:
        data = response

    # Validate type
    if not isinstance(data, expected_type):
        raise DataValidationError(
            f"{operation}: Expected {expected_type.__name__}, got {type(data).__name__}",
            {"response_type": type(data).__name__, "operation": operation},
        )

    logger.debug(
        f"Successfully validated response format for {operation}",
        response_type=expected_type.__name__,
        item_count=len(data) if isinstance(data, (list, dict)) else 1,
        wrapped="items" in response if isinstance(response, dict) else False,
    )

    return data


async def with_semaphore_limit[T](
    semaphore: asyncio.Semaphore,
    coro: Coroutine[Any, Any, T],
) -> T:
    """Execute a coroutine with semaphore concurrency limit.

    Parameters
    ----------
    semaphore : asyncio.Semaphore
        Semaphore to limit concurrency.
    coro : Coroutine
        Coroutine to execute.

    Returns
    -------
    T
        Result of the coroutine.

    """
    async with semaphore:
        logger.debug(
            "Executing task with semaphore limit",
            current_count=semaphore._value,
        )
        return await coro


def batch_with_concurrency_limit[T](
    tasks: list[Coroutine[Any, Any, T]],
    max_concurrent: int = 5,
) -> list[Coroutine[Any, Any, T]]:
    """Wrap tasks with semaphore for concurrency limiting.

    Parameters
    ----------
    tasks : list[Coroutine]
        List of coroutines to execute.
    max_concurrent : int
        Maximum number of concurrent tasks.

    Returns
    -------
    list[Coroutine]
        Tasks wrapped with semaphore.

    """
    logger.debug(
        "Creating batch with concurrency limit",
        task_count=len(tasks),
        max_concurrent=max_concurrent,
    )
    semaphore = asyncio.Semaphore(max_concurrent)
    return [with_semaphore_limit(semaphore, task) for task in tasks]
