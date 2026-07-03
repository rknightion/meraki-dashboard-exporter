"""Standardized error handling utilities for collectors.

This module provides decorators and utilities for consistent error handling,
retry logic, and error tracking across all collectors.
"""

from __future__ import annotations

import asyncio
import functools
import random
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

# Rate limit patterns to detect in API error responses (case-insensitive)
RATE_LIMIT_PATTERNS: tuple[str, ...] = (
    "rate limit exceeded",
    "too many requests",
    "throttled",
    "rate limited",
)


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


class RetryableAPIError(CollectorError):
    """Raised when an API error is retryable (e.g., rate limit in HTTP 200 response)."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize retryable API error.

        Parameters
        ----------
        message : str
            Error message.
        retry_after : float | None
            Suggested wait time before retry in seconds.
        context : dict[str, Any] | None
            Additional context for debugging.

        """
        super().__init__(message, ErrorCategory.API_RATE_LIMIT, context)
        self.retry_after = retry_after


class NothingCollectedError(CollectorError):
    """A collection cycle produced zero successful organization-scope updates.

    Raised by coordinator collectors when organizations were present but every
    attempted unit of work failed (or every org was skipped for backoff), so the
    manager records the cycle as a FAILURE instead of a spurious success
    (#509 / RES-01). The failure seam contract: a collector signals failure by
    raising out of ``_collect_impl()``; success/failure accounting lives ONLY in
    ``collectors/manager.py`` (collector_health) and ``core/collector.py``
    (success timestamp / error counter).
    """

    def __init__(
        self,
        collector: str,
        *,
        attempted: int,
        failed: int,
        skipped_backoff: int = 0,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize NothingCollectedError."""
        super().__init__(
            f"{collector} collected nothing this cycle: "
            f"attempted={attempted} failed={failed} skipped_backoff={skipped_backoff}",
            ErrorCategory.API_CLIENT_ERROR,
            context,
        )
        self.attempted = attempted
        self.failed = failed
        self.skipped_backoff = skipped_backoff


def with_error_handling(
    *,
    operation: str,
    continue_on_error: bool = True,
    error_category: ErrorCategory | None = None,
    max_retries: int = 3,
    base_delay: float = 10.0,
    max_delay: float = 60.0,
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
    max_retries : int
        Maximum number of retries for retryable errors (default: 3).
    base_delay : float
        Base delay in seconds for exponential backoff (default: 10.0).
    max_delay : float
        Maximum delay in seconds (default: 60.0).

    Returns
    -------
    Callable
        Decorated function with error handling and retry logic.

    Notes
    -----
    **Single 429 retry owner (#545).** This decorator owns rate-limit (429)
    retries for the whole exporter: the Meraki SDK is created with
    ``wait_on_rate_limit=False`` (see ``api/client.py``), so a 429 raises
    immediately in the worker thread instead of sleeping ``Retry-After``
    in-thread. The backoff waits happen here via ``await asyncio.sleep`` on
    the event loop - cancellable, and never holding an executor thread. A
    server-sent ``Retry-After`` is honoured but capped at
    ``settings.api.retry_after_max_seconds`` (read from the decorated
    instance at call time; falls back to ``max_delay``). Total HTTP attempts
    per logical fetch are therefore bounded by ``1 + max_retries``.

    **Per-fetch deadline & timeout semantics (#546).** When the decorated
    instance carries ``settings.api``, the entire logical fetch (all attempts
    plus all backoff waits) runs under
    ``asyncio.timeout(settings.api.per_fetch_deadline_seconds)``. On expiry
    the fetch is cancelled, tracked via ``_track_error(TIMEOUT)``, and treated
    exactly like any other failed fetch: ``None`` is returned (or
    ``CollectorError`` raised when ``continue_on_error=False``), so no partial
    result is handed back for metric emission and a slow fetch cannot consume
    the whole per-collector timeout budget. The underlying SDK worker thread
    cannot be cancelled mid-request, but it runs on the dedicated bounded SDK
    executor (#544) and its own HTTP timeouts bound how long it lingers.

    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, T | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
            start_time = time.time()

            # Extract context and collector instance from self if available
            context: dict[str, Any] = {}
            collector_instance = None
            if args and hasattr(args[0], "__class__"):
                collector_instance = args[0]
                if hasattr(collector_instance, "__class__"):
                    context["collector"] = collector_instance.__class__.__name__
                if hasattr(collector_instance, "update_tier"):
                    context["tier"] = collector_instance.update_tier.value

            async def _run_attempts() -> T | None:
                """Run all fetch attempts (and their backoff waits) for one logical fetch."""
                retry_count = 0

                while True:
                    try:
                        result = await func(*args, **kwargs)

                        # Log successful operation at debug level
                        duration = time.time() - start_time
                        log_context = dict(context)
                        log_context["duration_seconds"] = round(duration, 2)
                        if retry_count > 0:
                            log_context["retry_count"] = retry_count

                        logger.debug(
                            f"{operation} completed successfully",
                            **log_context,
                        )

                        return result

                    except RetryableAPIError as e:
                        # Handle retryable errors with exponential backoff
                        if retry_count < max_retries:
                            retry_count += 1
                            # #545: honour a server-sent Retry-After but cap it
                            # (settings.api.retry_after_max_seconds) so one
                            # pathological header cannot stall the whole fetch;
                            # exponential backoff keeps the max_delay cap.
                            if e.retry_after is not None:
                                capped_retry_after = min(
                                    e.retry_after,
                                    _resolve_retry_after_cap(collector_instance, max_delay),
                                )
                                delay = capped_retry_after
                            else:
                                capped_retry_after = None
                                delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
                            delay = _apply_jitter(delay)

                            logger.warning(
                                f"{operation} rate limited, retrying",
                                retry_count=retry_count,
                                max_retries=max_retries,
                                wait_seconds=round(delay, 2),
                                retry_after_seconds=e.retry_after,
                                error=str(e),
                                **context,
                            )

                            # Track retry metric if collector available
                            if collector_instance and hasattr(collector_instance, "_track_retry"):
                                collector_instance._track_retry(operation, "http_200_rate_limit")

                            # #617: feed the (capped) Retry-After into the AIMD
                            # budget controller so the effective client-side rate
                            # backs off; no-op in fixed mode / without a limiter.
                            _record_throttle_event(collector_instance, capped_retry_after)

                            await asyncio.sleep(delay)
                            continue

                        # Max retries exceeded
                        error_context = dict(context)
                        error_context["duration_seconds"] = round(time.time() - start_time, 2)
                        error_context["retry_count"] = retry_count

                        logger.error(
                            f"{operation} failed after {max_retries} retries",
                            error=str(e),
                            error_type="RetryableAPIError",
                            **error_context,
                        )

                        # Track error metric if collector available
                        if collector_instance and hasattr(collector_instance, "_track_error"):
                            collector_instance._track_error(ErrorCategory.API_RATE_LIMIT)

                        if continue_on_error:
                            return None
                        raise CollectorError(
                            f"{operation} failed after {max_retries} retries: {e}",
                            ErrorCategory.API_RATE_LIMIT,
                            error_context,
                        ) from e

                    except TimeoutError as e:
                        # Create a new context dict with the duration
                        error_context = dict(context)
                        error_context["duration_seconds"] = round(time.time() - start_time, 2)
                        logger.error(
                            f"{operation} timed out",
                            error_type="TimeoutError",
                            **error_context,
                        )

                        # Track error metric if collector available
                        if collector_instance and hasattr(collector_instance, "_track_error"):
                            collector_instance._track_error(ErrorCategory.TIMEOUT)

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

                        if _is_rate_limit_error(e):
                            retry_after = _get_retry_after_seconds(e)
                            if retry_count < max_retries:
                                retry_count += 1
                                # #545: same bounded Retry-After handling as above.
                                if retry_after is not None:
                                    capped_retry_after = min(
                                        retry_after,
                                        _resolve_retry_after_cap(collector_instance, max_delay),
                                    )
                                    delay = capped_retry_after
                                else:
                                    capped_retry_after = None
                                    delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
                                delay = _apply_jitter(delay)

                                logger.warning(
                                    f"{operation} rate limited, retrying",
                                    retry_count=retry_count,
                                    max_retries=max_retries,
                                    wait_seconds=round(delay, 2),
                                    retry_after_seconds=retry_after,
                                    error_type=error_type,
                                    error=error_msg,
                                    **context,
                                )

                                if collector_instance and hasattr(
                                    collector_instance, "_track_retry"
                                ):
                                    collector_instance._track_retry(
                                        operation, "http_429_rate_limit"
                                    )

                                # #617: feed the (capped) Retry-After into the AIMD
                                # budget controller (see the RetryableAPIError branch).
                                _record_throttle_event(collector_instance, capped_retry_after)

                                await asyncio.sleep(delay)
                                continue

                            # Max retries exceeded for rate limit
                            rate_context = dict(context)
                            rate_context.update({
                                "duration_seconds": round(duration, 2),
                                "retry_count": retry_count,
                                "error_type": error_type,
                                "error": error_msg,
                            })

                            logger.warning(
                                f"{operation} rate limited, retries exhausted",
                                **rate_context,
                            )

                            if collector_instance and hasattr(collector_instance, "_track_error"):
                                collector_instance._track_error(ErrorCategory.API_RATE_LIMIT)

                            if continue_on_error:
                                return None

                            raise CollectorError(
                                f"{operation} failed after {max_retries} retries: {error_msg}",
                                ErrorCategory.API_RATE_LIMIT,
                                rate_context,
                            ) from e

                        # Determine error category
                        category = error_category or _categorize_error(e)

                        # Create new context with mixed types
                        exc_context: dict[str, Any] = dict(context)
                        exc_context.update({
                            "duration_seconds": round(duration, 2),
                            "error_type": error_type,
                            "error": error_msg,
                        })

                        # Special handling for 404 errors. Prefer the structured
                        # HTTP status code (e.g. meraki.APIError.status) over a bare
                        # substring check: str(APIError) concatenates server-controlled
                        # body text, so a genuine 500 whose message merely contains
                        # "404" must not be silently downgraded. Only fall back to the
                        # substring heuristic for non-APIError exceptions with no status.
                        status_code = getattr(e, "status", None)
                        is_not_available = (
                            status_code == 404 if status_code is not None else "404" in error_msg
                        )
                        if is_not_available:
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
                        if collector_instance and hasattr(collector_instance, "_track_error"):
                            collector_instance._track_error(category)

                        if continue_on_error:
                            return None

                        # Re-raise as CollectorError with context
                        raise CollectorError(
                            f"{operation} failed: {error_msg}",
                            category,
                            context,
                        ) from e

            # #546: per-fetch wall-clock deadline. One logical fetch (all HTTP
            # attempts plus all backoff waits) must finish within
            # ``settings.api.per_fetch_deadline_seconds``. On expiry the fetch
            # coroutine is cancelled (``asyncio.timeout``), the failure is
            # tracked as a TIMEOUT, and ``None`` is returned - so no partial
            # result is handed back for metric emission and the collector's
            # remaining budget is preserved. Instances without settings (plain
            # decorated functions) keep the historic no-deadline behavior.
            deadline = _resolve_per_fetch_deadline(collector_instance)
            try:
                async with asyncio.timeout(deadline):
                    return await _run_attempts()
            except TimeoutError as timeout_exc:
                error_context = dict(context)
                error_context["duration_seconds"] = round(time.time() - start_time, 2)
                error_context["deadline_seconds"] = deadline

                logger.error(
                    f"{operation} exceeded per-fetch deadline",
                    error_type="TimeoutError",
                    **error_context,
                )

                if collector_instance and hasattr(collector_instance, "_track_error"):
                    collector_instance._track_error(ErrorCategory.TIMEOUT)

                if continue_on_error:
                    return None
                raise CollectorError(
                    f"{operation} exceeded per-fetch deadline",
                    ErrorCategory.TIMEOUT,
                    error_context,
                ) from timeout_exc

        return wrapper

    return decorator


#: Frozen default for ``settings.api.per_fetch_deadline_seconds`` (#546), used
#: when the decorated instance has ``settings.api`` but the field is absent
#: (e.g. an older settings snapshot). Kept in sync with ``APISettings``.
DEFAULT_PER_FETCH_DEADLINE_SECONDS = 120.0


def _resolve_api_settings(instance: Any) -> Any:
    """Return ``instance.settings.api`` if the decorated instance carries it."""
    settings = getattr(instance, "settings", None)
    return getattr(settings, "api", None)


def _resolve_retry_after_cap(instance: Any, fallback: float) -> float:
    """Upper bound honoured for a server-sent Retry-After wait (#545).

    Reads ``settings.api.retry_after_max_seconds`` from the decorated instance
    at call time (the decorator itself has no settings access); falls back to
    the decorator's ``max_delay`` when the instance has no settings, the field
    is absent, or the value is unusable.
    """
    cap = getattr(_resolve_api_settings(instance), "retry_after_max_seconds", None)
    # Strict isinstance (not float() coercion): mocks and other proxies can
    # implement __float__ and would otherwise smuggle in a bogus cap.
    if isinstance(cap, bool) or not isinstance(cap, (int, float)):
        return fallback
    return float(cap)


def _resolve_rate_limiter(instance: Any) -> Any:
    """Resolve the ``OrgRateLimiter`` from a decorated collector instance (#617).

    Mirrors ``_resolve_retry_after_cap``'s lookup pattern: the limiter hangs off
    the collector directly (``instance.rate_limiter``) or off its coordinator
    parent (``instance.parent.rate_limiter``). Returns ``None`` when neither
    carries one (plain decorated functions, standalone tests).
    """
    rate_limiter = getattr(instance, "rate_limiter", None)
    if rate_limiter is not None:
        return rate_limiter
    parent = getattr(instance, "parent", None)
    if parent is not None:
        return getattr(parent, "rate_limiter", None)
    return None


def _record_throttle_event(instance: Any, retry_after: float | None) -> None:
    """Feed a 429/Retry-After event into the AIMD budget controller (#617).

    Resolves the rate limiter off the decorated instance and calls
    ``record_throttle_event(None, retry_after)`` with the already-extracted,
    capped Retry-After. No-op when the instance carries no limiter;
    ``OrgRateLimiter.record_throttle_event`` is itself a no-op in fixed mode or
    when AIMD is disabled.
    """
    rate_limiter = _resolve_rate_limiter(instance)
    recorder = getattr(rate_limiter, "record_throttle_event", None)
    if recorder is None:
        return
    recorder(None, retry_after)


def _resolve_per_fetch_deadline(instance: Any) -> float | None:
    """Per-fetch wall-clock deadline in seconds, or ``None`` for no deadline (#546).

    Reads ``settings.api.per_fetch_deadline_seconds`` from the decorated
    instance. Instances with ``settings.api`` but no field (pre-seam) get the
    frozen 120s default; instances without settings (plain decorated
    functions) and unusable/non-positive values get no deadline, preserving
    the historic behavior.
    """
    api_settings = _resolve_api_settings(instance)
    if api_settings is None:
        return None
    deadline = getattr(
        api_settings, "per_fetch_deadline_seconds", DEFAULT_PER_FETCH_DEADLINE_SECONDS
    )
    # Strict isinstance (not float() coercion): mocks and other proxies can
    # implement __float__ and would otherwise impose a bogus ~1s deadline.
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        return None
    return float(deadline) if deadline > 0 else None


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
    status = getattr(error, "status", None)

    # Prefer the structured HTTP status code (e.g. meraki.APIError.status) over
    # brittle substring matching. str(APIError) concatenates server-controlled
    # body text, so a status-code-like fragment (a serial, an ID, etc.) in the
    # message must not miscategorize a genuine 500 as a 404.
    if status is not None:
        if status == 429:
            return ErrorCategory.API_RATE_LIMIT
        if status == 404:
            return ErrorCategory.API_NOT_AVAILABLE
        if status in {400, 401, 403, 405, 406}:
            return ErrorCategory.API_CLIENT_ERROR
        if status in {500, 502, 503, 504}:
            return ErrorCategory.API_SERVER_ERROR
        # Unknown/other status: fall through to the heuristics below.

    # Fallback string heuristics for non-APIError exceptions (no .status).
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
    RetryableAPIError
        If response contains retryable errors (e.g., rate limit).
    DataValidationError
        If response format is unexpected or contains non-retryable errors.

    """
    # Check for API error responses (e.g., rate limit errors)
    if isinstance(response, dict) and "errors" in response:
        errors = response["errors"]
        error_msg = "; ".join(str(e) for e in errors) if isinstance(errors, list) else str(errors)

        # Check if this is a retryable rate limit error
        error_lower = error_msg.lower()
        is_rate_limit = any(pattern in error_lower for pattern in RATE_LIMIT_PATTERNS)

        if is_rate_limit:
            raise RetryableAPIError(
                f"{operation}: API rate limit error: {error_msg}",
                retry_after=None,  # Will use default backoff
                context={"errors": errors, "operation": operation},
            )

        # Non-retryable error
        raise DataValidationError(
            f"{operation}: API returned errors: {error_msg}",
            {"errors": errors, "operation": operation},
        )

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


def _apply_jitter(delay: float, jitter_ratio: float = 0.2) -> float:
    """Apply jitter to a delay to avoid thundering herd effects."""
    if delay <= 0:
        return delay
    jitter_multiplier = 1.0 + random.uniform(-jitter_ratio, jitter_ratio)
    return max(0.0, delay * jitter_multiplier)


def _get_retry_after_seconds(error: Exception) -> float | None:
    """Extract Retry-After seconds from an exception if available."""
    retry_after = getattr(error, "retry_after", None)
    if retry_after is not None:
        try:
            return float(retry_after)
        except TypeError, ValueError:
            return None

    response = getattr(error, "response", None)
    if response is not None and hasattr(response, "headers"):
        header_value = response.headers.get("Retry-After")
        if header_value:
            try:
                return float(header_value)
            except TypeError, ValueError:
                return None

    return None


def _is_rate_limit_error(error: Exception) -> bool:
    """Check if an exception indicates a rate limit condition."""
    status = getattr(error, "status", None)
    if status == 429:
        return True
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in RATE_LIMIT_PATTERNS)


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
