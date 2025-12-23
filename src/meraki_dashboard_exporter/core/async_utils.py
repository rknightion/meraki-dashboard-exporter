"""Async utilities and context managers for standardized async patterns."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from contextvars import copy_context
from typing import TYPE_CHECKING, Any, TypeVar

from opentelemetry import trace
from prometheus_client import Counter, Gauge
from prometheus_client.core import REGISTRY

from .logging import get_logger

if TYPE_CHECKING:
    from asyncio import Semaphore, Task

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class ManagedTaskGroup:
    """Context manager for tracking and cleaning up async tasks with structured concurrency.

    Provides structured concurrency for managing groups of related async tasks,
    ensuring proper cleanup even in error scenarios. All tasks created within
    the group are automatically tracked and cleaned up on exit.

    Key differences from alternatives:
    - vs asyncio.gather: Allows dynamic task creation within context
    - vs asyncio.TaskGroup (3.11+): Works on older Python versions
    - vs manual tracking: Automatic cleanup prevents orphaned tasks

    Examples
    --------
    Basic parallel API calls:
    >>> async with ManagedTaskGroup("api_calls") as group:
    ...     await group.create_task(fetch_organizations())
    ...     await group.create_task(fetch_networks())
    ...     # Both tasks run in parallel and are awaited on exit

    Dynamic task creation based on results:
    >>> async with ManagedTaskGroup("device_fetch") as group:
    ...     orgs = await fetch_organizations()
    ...     for org in orgs:
    ...         await group.create_task(
    ...             fetch_devices(org["id"]),
    ...             name=f"devices_{org['id']}"
    ...         )

    Bounded concurrency with backpressure (NEW):
    >>> async with ManagedTaskGroup("org_fetch", max_concurrency=3) as group:
    ...     orgs = await fetch_organizations()
    ...     for org in orgs:
    ...         # Only 3 orgs will be processed concurrently
    ...         # Additional tasks wait for semaphore slot (backpressure)
    ...         await group.create_task(
    ...             process_organization(org["id"]),
    ...             name=f"org_{org['id']}"
    ...         )

    Error handling - all tasks cancelled on exception:
    >>> async with ManagedTaskGroup("metrics") as group:
    ...     await group.create_task(collect_fast_metrics())
    ...     await group.create_task(collect_slow_metrics())
    ...     raise ValueError("Something went wrong")
    ...     # Both tasks will be cancelled

    When to Use
    -----------
    - Multiple independent API calls that should run in parallel
    - Dynamic number of tasks based on API responses
    - Operations that should all complete or all be cancelled
    - When you need task lifecycle tracking

    When NOT to Use
    ---------------
    - Single async operation (just await directly)
    - CPU-bound operations (use ProcessPoolExecutor)
    - Fire-and-forget tasks (use asyncio.create_task)
    - When you need return values (use gather or as_completed)

    Notes
    -----
    - Tasks are cancelled on exception but not on normal exit
    - Task exceptions are propagated after all tasks complete
    - Memory usage scales with number of concurrent tasks
    - Use for I/O-bound operations, not CPU-bound work

    """

    def __init__(
        self,
        name: str = "task_group",
        max_concurrency: int | None = None,
    ) -> None:
        """Initialize the task group.

        Parameters
        ----------
        name : str
            Name for the task group (used in logging).
        max_concurrency : int | None
            Maximum number of concurrent tasks. If None, unlimited concurrency.
            Used for bounded pipeline execution and backpressure management.

        """
        self.name = name
        self.tasks: set[Task[Any]] = set()
        self._closed = False
        self.max_concurrency = max_concurrency
        self._semaphore: Semaphore | None = (
            asyncio.Semaphore(max_concurrency) if max_concurrency else None
        )
        self._active_count = 0
        self._total_created = 0
        self._total_completed = 0

        # Tracing support for distributed tracing context propagation
        self._span: trace.Span | None = None
        self._span_context_manager: Any = None

    async def __aenter__(self) -> ManagedTaskGroup:
        """Enter the context manager with optional tracing span."""
        logger.debug(f"Starting task group: {self.name}")

        # Create a span for the task group to enable distributed tracing
        tracer = trace.get_tracer(__name__)
        self._span = tracer.start_span(f"taskgroup.{self.name}")
        self._span.set_attribute("taskgroup.name", self.name)
        if self.max_concurrency:
            self._span.set_attribute("taskgroup.max_concurrency", self.max_concurrency)

        # Enter the span context to make it current
        self._span_context_manager = trace.use_span(self._span, end_on_exit=False)
        self._span_context_manager.__enter__()

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context manager and clean up tasks."""
        self._closed = True

        if self.tasks:
            logger.debug(
                f"Cleaning up task group: {self.name}",
                task_count=len(self.tasks),
                exception=exc_type.__name__ if exc_type else None,
            )

            # If exiting due to exception, cancel all tasks
            if exc_type:
                for task in self.tasks:
                    if not task.done():
                        task.cancel()

            # Wait for all tasks to complete
            try:
                results = await asyncio.gather(*self.tasks, return_exceptions=True)

                # Log any exceptions from tasks
                for i, result in enumerate(results):
                    if isinstance(result, Exception) and not isinstance(
                        result, asyncio.CancelledError
                    ):
                        logger.error(
                            f"Task failed in group {self.name}",
                            task_index=i,
                            error=str(result),
                            error_type=type(result).__name__,
                        )
            except Exception:
                logger.exception(f"Error cleaning up task group: {self.name}")

        # End the tracing span with proper status
        if self._span is not None:
            # Set span attributes with final statistics
            self._span.set_attribute("taskgroup.tasks_created", self._total_created)
            self._span.set_attribute("taskgroup.tasks_completed", self._total_completed)

            if exc_type:
                self._span.set_status(
                    trace.Status(trace.StatusCode.ERROR, str(exc_val) if exc_val else "Error")
                )
                if exc_val:
                    self._span.record_exception(exc_val)
            else:
                self._span.set_status(trace.Status(trace.StatusCode.OK))

            # Exit the span context
            if self._span_context_manager is not None:
                self._span_context_manager.__exit__(exc_type, exc_val, exc_tb)

            # End the span
            self._span.end()

    async def create_task(
        self,
        coro: Coroutine[Any, Any, T],
        name: str | None = None,
    ) -> Task[T]:
        """Create and track a task with context propagation and optional bounded concurrency.

        If max_concurrency is set, this method will wait for a semaphore
        slot before creating the task, implementing backpressure management.

        Trace context is automatically propagated to child tasks to maintain
        distributed tracing hierarchy.

        Parameters
        ----------
        coro : Coroutine
            The coroutine to run as a task.
        name : str | None
            Optional name for the task.

        Returns
        -------
        Task[T]
            The created task.

        Raises
        ------
        RuntimeError
            If the task group is closed.

        """
        if self._closed:
            raise RuntimeError(f"Cannot add tasks to closed group: {self.name}")

        # Copy the current context to propagate trace context to child tasks
        # This ensures distributed tracing maintains proper parent-child relationships
        ctx = copy_context()

        async def _run_with_context() -> T:
            """Run the coroutine within the copied context."""
            if self._semaphore:
                return await self._run_with_semaphore(coro, name or "unnamed")
            return await coro

        # Create the task using the copied context
        # ctx.run() ensures the coroutine runs with the trace context from when
        # create_task was called, not when the task actually executes
        task = ctx.run(asyncio.create_task, _run_with_context(), name=name)

        self.tasks.add(task)
        self._total_created += 1

        # Remove from set and update counters when done
        def _on_complete(t: Task[T]) -> None:
            self.tasks.discard(t)
            self._total_completed += 1

        task.add_done_callback(_on_complete)

        return task

    async def _run_with_semaphore(
        self,
        coro: Coroutine[Any, Any, T],
        task_name: str,
    ) -> T:
        """Run coroutine with semaphore for bounded concurrency.

        Parameters
        ----------
        coro : Coroutine
            The coroutine to run.
        task_name : str
            Name of the task for logging.

        Returns
        -------
        T
            Result from the coroutine.

        """
        if not self._semaphore:
            return await coro

        # Wait for semaphore slot (backpressure)
        async with self._semaphore:
            self._active_count += 1
            logger.debug(
                f"Task acquired semaphore in {self.name}",
                task_name=task_name,
                active=self._active_count,
                max_concurrency=self.max_concurrency,
            )
            try:
                return await coro
            finally:
                self._active_count -= 1

    async def gather(self) -> list[Any]:
        """Wait for all tasks and return results.

        Returns
        -------
        list[Any]
            Results from all tasks.

        """
        if not self.tasks:
            return []

        return await asyncio.gather(*self.tasks, return_exceptions=True)

    def get_stats(self) -> dict[str, int]:
        """Get statistics about task group execution.

        Returns
        -------
        dict[str, int]
            Dictionary with statistics including active, pending, completed counts.

        """
        return {
            "active": len(self.tasks),
            "total_created": self._total_created,
            "total_completed": self._total_completed,
            "pending": self._total_created - self._total_completed,
            "active_count": self._active_count,
        }

    async def wait_for_capacity(self, target_active: int = 1) -> None:
        """Wait until the number of active tasks drops below target.

        Useful for implementing backpressure in producer-consumer patterns.

        Parameters
        ----------
        target_active : int
            Target number of active tasks to wait for.

        """
        while len(self.tasks) >= (self.max_concurrency or target_active):
            # Wait a bit and check again
            await asyncio.sleep(0.1)

    async def create_tasks_batch(
        self,
        coros: list[Coroutine[Any, Any, T]],
        name_prefix: str = "task",
    ) -> list[Task[T]]:
        """Create multiple tasks at once with optional backpressure.

        Parameters
        ----------
        coros : list[Coroutine]
            List of coroutines to create tasks for.
        name_prefix : str
            Prefix for task names.

        Returns
        -------
        list[Task[T]]
            List of created tasks.

        """
        tasks = []
        for i, coro in enumerate(coros):
            task = await self.create_task(coro, name=f"{name_prefix}_{i}")
            tasks.append(task)
        return tasks


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout: float,
    operation: str = "operation",
    default: T | None = None,
) -> T | None:
    """Execute coroutine with timeout and proper error handling.

    Parameters
    ----------
    coro : Coroutine
        The coroutine to execute.
    timeout : float
        Timeout in seconds.
    operation : str
        Description of the operation for logging.
    default : T | None
        Default value to return on timeout.

    Returns
    -------
    T | None
        Result from coroutine or default on timeout.

    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        logger.warning(
            f"Timeout during {operation}",
            timeout=timeout,
        )
        return default
    except Exception:
        logger.exception(f"Error during {operation}")
        return default


@asynccontextmanager
async def managed_resource(
    resource_factory: Callable[[], Coroutine[Any, Any, T]],
    cleanup_func: Callable[[T], Coroutine[Any, Any, None]] | None = None,
    resource_name: str = "resource",
) -> AsyncIterator[T]:
    """Context manager for async resource management with cleanup.

    Parameters
    ----------
    resource_factory : Callable
        Async function that creates the resource.
    cleanup_func : Callable | None
        Async function to clean up the resource.
    resource_name : str
        Name of the resource for logging.

    Yields
    ------
    T
        The created resource.

    """
    resource = None
    try:
        logger.debug(f"Creating {resource_name}")
        resource = await resource_factory()
        yield resource
    except Exception:
        logger.exception(f"Error with {resource_name}")
        raise
    finally:
        if resource is not None and cleanup_func:
            try:
                logger.debug(f"Cleaning up {resource_name}")
                await cleanup_func(resource)
            except Exception:
                logger.exception(f"Error cleaning up {resource_name}")


async def safe_gather[T](
    *coros: Coroutine[Any, Any, T],
    return_exceptions: bool = True,
    description: str = "operations",
    log_errors: bool = True,
) -> list[T | Exception]:
    """Gather coroutines with logging and error tracking.

    Parameters
    ----------
    *coros : Coroutine
        Coroutines to gather.
    return_exceptions : bool
        Whether to return exceptions instead of raising.
    description : str
        Description for logging.
    log_errors : bool
        Whether to log exceptions.

    Returns
    -------
    list[T | Exception]
        Results from all coroutines.

    """
    if not coros:
        return []

    logger.debug(
        f"Gathering {len(coros)} {description}",
        count=len(coros),
    )

    results = await asyncio.gather(*coros, return_exceptions=return_exceptions)

    # Filter out non-Exception BaseExceptions (like SystemExit, KeyboardInterrupt)
    filtered_results: list[T | Exception] = []
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, Exception):
            # Log and skip non-Exception BaseExceptions
            logger.warning(
                f"Skipping non-Exception BaseException in {description}",
                error_type=type(result).__name__,
            )
            continue
        filtered_results.append(result)

    if log_errors:
        error_count = sum(1 for r in filtered_results if isinstance(r, Exception))
        if error_count > 0:
            logger.warning(
                f"Errors in {description}",
                total=len(filtered_results),
                errors=error_count,
            )

            # Log individual errors at debug level
            for i, result in enumerate(filtered_results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.debug(
                        f"Error in {description}[{i}]",
                        error=str(result),
                        error_type=type(result).__name__,
                    )

    return filtered_results


async def rate_limited_gather[T](
    coros: list[Coroutine[Any, Any, T]],
    semaphore: Semaphore,
    description: str = "operations",
) -> list[T | Exception]:
    """Gather coroutines with semaphore-based rate limiting.

    Parameters
    ----------
    coros : list[Coroutine]
        Coroutines to execute.
    semaphore : Semaphore
        Semaphore for rate limiting.
    description : str
        Description for logging.

    Returns
    -------
    list[T | Exception]
        Results from all coroutines.

    """

    async def _run_with_semaphore(coro: Coroutine[Any, Any, T]) -> T:
        """Run coroutine with semaphore."""
        async with semaphore:
            return await coro

    limited_coros = [_run_with_semaphore(coro) for coro in coros]
    return await safe_gather(*limited_coros, description=description)


class AsyncRetry:
    """Async retry logic with exponential backoff.

    Example:
    -------
    retry = AsyncRetry(max_attempts=3, base_delay=1.0)
    result = await retry.execute(async_operation, "fetch data")

    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retry_on: tuple[type[Exception], ...] | None = None,
    ) -> None:
        """Initialize retry configuration.

        Parameters
        ----------
        max_attempts : int
            Maximum number of attempts.
        base_delay : float
            Initial delay between retries in seconds.
        max_delay : float
            Maximum delay between retries.
        exponential_base : float
            Base for exponential backoff.
        retry_on : tuple[type[Exception], ...] | None
            Exception types to retry on. If None, retries on all exceptions.

        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retry_on = retry_on or (Exception,)

    async def execute(
        self,
        coro_func: Callable[[], Coroutine[Any, Any, T]],
        operation: str = "operation",
    ) -> T:
        """Execute coroutine with retry logic.

        Parameters
        ----------
        coro_func : Callable
            Function that returns a coroutine to execute.
        operation : str
            Description of the operation.

        Returns
        -------
        T
            Result from successful execution.

        Raises
        ------
        Exception
            The last exception if all retries fail.

        """
        last_error: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                return await coro_func()
            except self.retry_on as e:
                last_error = e

                if attempt < self.max_attempts - 1:
                    delay = min(
                        self.base_delay * (self.exponential_base**attempt),
                        self.max_delay,
                    )

                    logger.warning(
                        f"Retry {operation}",
                        attempt=attempt + 1,
                        max_attempts=self.max_attempts,
                        delay=delay,
                        error=str(e),
                    )

                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed {operation} after all retries",
                        attempts=self.max_attempts,
                        error=str(e),
                    )

        if last_error:
            raise last_error

        # Should never reach here
        raise RuntimeError(f"Unexpected error in retry logic for {operation}")


async def chunked_async_iter[T](
    items: list[T],
    chunk_size: int,
    delay_between_chunks: float = 0.0,
) -> AsyncIterator[list[T]]:
    """Async iterator that yields chunks of items with optional delay.

    Parameters
    ----------
    items : list[T]
        Items to chunk.
    chunk_size : int
        Size of each chunk.
    delay_between_chunks : float
        Delay in seconds between chunks.

    Yields
    ------
    list[T]
        Chunks of items.

    """
    for i in range(0, len(items), chunk_size):
        chunk = items[i : i + chunk_size]
        yield chunk

        # Delay between chunks (except for the last chunk)
        if i + chunk_size < len(items) and delay_between_chunks > 0:
            await asyncio.sleep(delay_between_chunks)


class CircuitBreaker:
    """Circuit breaker pattern for handling failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests are allowed
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing if the service has recovered

    """

    class State:
        """Circuit breaker states."""

        CLOSED = "closed"
        OPEN = "open"
        HALF_OPEN = "half_open"

    # Class-level metrics shared by all circuit breakers
    _metrics_initialized = False
    _state_gauge: Gauge | None = None
    _failures_counter: Counter | None = None
    _success_counter: Counter | None = None
    _rejections_counter: Counter | None = None
    _state_changes_counter: Counter | None = None

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
        name: str = "default",
    ) -> None:
        """Initialize circuit breaker.

        Parameters
        ----------
        failure_threshold : int
            Number of failures before opening circuit.
        recovery_timeout : float
            Time in seconds before attempting recovery.
        expected_exception : type[Exception]
            Exception type that triggers the circuit breaker.
        name : str
            Name of the circuit breaker for metrics.

        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name

        self._state = self.State.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

        # Initialize metrics if not done yet
        if not CircuitBreaker._metrics_initialized:
            CircuitBreaker._initialize_metrics()

        # Set initial state in metrics
        if CircuitBreaker._state_gauge:
            CircuitBreaker._state_gauge.labels(breaker=self.name, state=self.State.CLOSED).set(1)
            CircuitBreaker._state_gauge.labels(breaker=self.name, state=self.State.OPEN).set(0)
            CircuitBreaker._state_gauge.labels(breaker=self.name, state=self.State.HALF_OPEN).set(0)

    @classmethod
    def _initialize_metrics(cls) -> None:
        """Initialize circuit breaker metrics."""
        if cls._metrics_initialized:
            return

        try:
            cls._state_gauge = Gauge(
                "meraki_circuit_breaker_state",
                "Current state of circuit breakers (1=active, 0=inactive)",
                labelnames=["breaker", "state"],
                registry=REGISTRY,
            )

            cls._failures_counter = Counter(
                "meraki_circuit_breaker_failures_total",
                "Total number of failures handled by circuit breakers",
                labelnames=["breaker"],
                registry=REGISTRY,
            )

            cls._success_counter = Counter(
                "meraki_circuit_breaker_success_total",
                "Total number of successful calls through circuit breakers",
                labelnames=["breaker"],
                registry=REGISTRY,
            )

            cls._rejections_counter = Counter(
                "meraki_circuit_breaker_rejections_total",
                "Total number of calls rejected by open circuit breakers",
                labelnames=["breaker"],
                registry=REGISTRY,
            )

            cls._state_changes_counter = Counter(
                "meraki_circuit_breaker_state_changes_total",
                "Total number of state changes in circuit breakers",
                labelnames=["breaker", "from_state", "to_state"],
                registry=REGISTRY,
            )

            cls._metrics_initialized = True
            logger.info("Initialized circuit breaker metrics")

        except Exception:
            logger.exception("Failed to initialize circuit breaker metrics")

    async def call(
        self,
        coro_func: Callable[[], Coroutine[Any, Any, T]],
        operation: str = "operation",
    ) -> T:
        """Execute coroutine through circuit breaker.

        Parameters
        ----------
        coro_func : Callable
            Function that returns a coroutine to execute.
        operation : str
            Description of the operation.

        Returns
        -------
        T
            Result from successful execution.

        Raises
        ------
        Exception
            If circuit is open or operation fails.

        """
        async with self._lock:
            current_state = await self._get_state()

            if current_state == self.State.OPEN:
                # Track rejection
                if CircuitBreaker._rejections_counter:
                    CircuitBreaker._rejections_counter.labels(breaker=self.name).inc()

                raise RuntimeError(
                    f"Circuit breaker is OPEN for {operation} (failures: {self._failure_count})"
                )

        try:
            result = await coro_func()
            await self._on_success()
            return result
        except self.expected_exception:
            await self._on_failure()
            raise

    async def _get_state(self) -> str:
        """Get current circuit breaker state."""
        if self._state == self.State.CLOSED:
            return self.State.CLOSED

        if self._state == self.State.OPEN:
            if (
                self._last_failure_time
                and asyncio.get_event_loop().time() - self._last_failure_time
                >= self.recovery_timeout
            ):
                old_state = self._state
                self._state = self.State.HALF_OPEN

                # Track state change
                if CircuitBreaker._state_changes_counter:
                    CircuitBreaker._state_changes_counter.labels(
                        breaker=self.name,
                        from_state=old_state,
                        to_state=self.State.HALF_OPEN,
                    ).inc()

                # Update state gauge
                self._update_state_gauge(old_state, self.State.HALF_OPEN)

                logger.info("Circuit breaker entering HALF_OPEN state", breaker=self.name)

        return self._state

    async def _on_success(self) -> None:
        """Handle successful operation."""
        async with self._lock:
            # Track success
            if CircuitBreaker._success_counter:
                CircuitBreaker._success_counter.labels(breaker=self.name).inc()

            if self._state == self.State.HALF_OPEN:
                old_state = self._state
                self._state = self.State.CLOSED
                self._failure_count = 0

                # Track state change
                if CircuitBreaker._state_changes_counter:
                    CircuitBreaker._state_changes_counter.labels(
                        breaker=self.name,
                        from_state=old_state,
                        to_state=self.State.CLOSED,
                    ).inc()

                # Update state gauge
                self._update_state_gauge(old_state, self.State.CLOSED)

                logger.info("Circuit breaker reset to CLOSED state", breaker=self.name)

    async def _on_failure(self) -> None:
        """Handle failed operation."""
        async with self._lock:
            # Track failure
            if CircuitBreaker._failures_counter:
                CircuitBreaker._failures_counter.labels(breaker=self.name).inc()

            self._failure_count += 1
            self._last_failure_time = asyncio.get_event_loop().time()

            if self._failure_count >= self.failure_threshold:
                old_state = self._state
                self._state = self.State.OPEN

                # Track state change
                if CircuitBreaker._state_changes_counter:
                    CircuitBreaker._state_changes_counter.labels(
                        breaker=self.name,
                        from_state=old_state,
                        to_state=self.State.OPEN,
                    ).inc()

                # Update state gauge
                self._update_state_gauge(old_state, self.State.OPEN)

                logger.warning(
                    "Circuit breaker opened",
                    breaker=self.name,
                    failures=self._failure_count,
                    threshold=self.failure_threshold,
                )

    def _update_state_gauge(self, old_state: str, new_state: str) -> None:
        """Update state gauge metrics.

        Parameters
        ----------
        old_state : str
            Previous state.
        new_state : str
            New state.

        """
        if CircuitBreaker._state_gauge:
            # Set old state to 0
            CircuitBreaker._state_gauge.labels(breaker=self.name, state=old_state).set(0)
            # Set new state to 1
            CircuitBreaker._state_gauge.labels(breaker=self.name, state=new_state).set(1)
