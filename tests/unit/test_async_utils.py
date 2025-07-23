"""Tests for async utilities and patterns."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.core.async_utils import (
    AsyncRetry,
    CircuitBreaker,
    ManagedTaskGroup,
    chunked_async_iter,
    managed_resource,
    rate_limited_gather,
    safe_gather,
    with_timeout,
)


class TestManagedTaskGroup:
    """Test ManagedTaskGroup functionality."""

    async def test_basic_task_creation_and_execution(self):
        """Test creating and executing tasks in a group."""
        results = []

        async def task(value: int) -> int:
            await asyncio.sleep(0.01)
            results.append(value)
            return value * 2

        async with ManagedTaskGroup("test_group") as group:
            await group.create_task(task(1))
            await group.create_task(task(2))
            await group.create_task(task(3))

        # All tasks should have completed
        assert sorted(results) == [1, 2, 3]

    async def test_task_cancellation_on_exception(self):
        """Test that tasks are cancelled when exception occurs."""
        task_states: dict[str, str | bool] = {"task1": False, "task2": False}

        async def long_task(name: str) -> None:
            try:
                await asyncio.sleep(10)  # Long running task
                task_states[name] = True
            except asyncio.CancelledError:
                task_states[name] = "cancelled"
                raise

        try:
            async with ManagedTaskGroup("test_group") as group:
                await group.create_task(long_task("task1"))
                await group.create_task(long_task("task2"))
                await asyncio.sleep(0.01)  # Let tasks start
                raise ValueError("Test error")
        except ValueError:
            pass

        # Give tasks time to process cancellation
        await asyncio.sleep(0.01)

        # Both tasks should have been cancelled
        assert task_states["task1"] == "cancelled"
        assert task_states["task2"] == "cancelled"

    async def test_gather_results(self):
        """Test gathering results from all tasks."""

        async def task(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2

        async with ManagedTaskGroup("test_group") as group:
            await group.create_task(task(1))
            await group.create_task(task(2))
            await group.create_task(task(3))
            results = await group.gather()

        # Results should be available
        assert sorted(results) == [2, 4, 6]

    async def test_task_error_handling(self):
        """Test handling of errors in individual tasks."""

        async def failing_task() -> None:
            await asyncio.sleep(0.01)
            raise ValueError("Task failed")

        async def successful_task() -> str:
            await asyncio.sleep(0.01)
            return "success"

        async with ManagedTaskGroup("test_group") as group:
            await group.create_task(failing_task())
            await group.create_task(successful_task())

        # Group should complete even with failed task

    async def test_closed_group_error(self):
        """Test that adding tasks to closed group raises error."""

        async def dummy_task() -> None:
            pass

        group = ManagedTaskGroup("test_group")
        async with group:
            pass

        # Should raise error when trying to add task to closed group
        with pytest.raises(RuntimeError, match="Cannot add tasks to closed group"):
            # Properly await the dummy task to avoid RuntimeWarning
            task_coro = dummy_task()
            try:
                await group.create_task(task_coro)
            finally:
                # Ensure the coroutine is closed if it wasn't awaited
                task_coro.close()

    async def test_named_tasks(self):
        """Test creating named tasks."""

        async def task() -> str:
            return "result"

        async with ManagedTaskGroup("test_group") as group:
            task_obj = await group.create_task(task(), name="my_task")
            assert task_obj.get_name() == "my_task"

    async def test_empty_group(self):
        """Test group with no tasks."""
        async with ManagedTaskGroup("empty_group") as group:
            results = await group.gather()
            assert results == []


class TestWithTimeout:
    """Test with_timeout utility."""

    async def test_successful_operation(self):
        """Test operation that completes within timeout."""

        async def quick_operation() -> str:
            await asyncio.sleep(0.01)
            return "success"

        result = await with_timeout(quick_operation(), timeout=1.0, operation="test")
        assert result == "success"

    async def test_timeout(self):
        """Test operation that exceeds timeout."""

        async def slow_operation() -> str:
            await asyncio.sleep(2.0)
            return "never_reached"

        result = await with_timeout(
            slow_operation(), timeout=0.1, operation="slow_op", default="timeout_default"
        )
        assert result == "timeout_default"

    async def test_exception_handling(self):
        """Test handling of exceptions in operation."""

        async def failing_operation() -> str:
            raise ValueError("Operation failed")

        result = await with_timeout(
            failing_operation(), timeout=1.0, operation="failing_op", default="error_default"
        )
        assert result == "error_default"


class TestManagedResource:
    """Test managed_resource context manager."""

    async def test_resource_lifecycle(self):
        """Test resource creation and cleanup."""
        created = False
        cleaned = False

        async def create_resource() -> dict[str, Any]:
            nonlocal created
            created = True
            return {"resource": "data"}

        async def cleanup_resource(resource: dict[str, Any]) -> None:
            nonlocal cleaned
            assert resource["resource"] == "data"
            cleaned = True

        async with managed_resource(create_resource, cleanup_resource, "test_resource") as resource:
            assert created
            assert resource["resource"] == "data"

        assert cleaned

    async def test_cleanup_on_exception(self):
        """Test resource cleanup when exception occurs."""
        cleaned = False

        async def create_resource() -> dict[str, Any]:
            return {"resource": "data"}

        async def cleanup_resource(resource: dict[str, Any]) -> None:
            nonlocal cleaned
            cleaned = True

        with pytest.raises(ValueError):
            async with managed_resource(create_resource, cleanup_resource, "test_resource"):
                raise ValueError("Test error")

        assert cleaned

    async def test_no_cleanup_function(self):
        """Test resource without cleanup function."""

        async def create_resource() -> str:
            return "resource"

        async with managed_resource(create_resource, resource_name="test") as resource:
            assert resource == "resource"


class TestSafeGather:
    """Test safe_gather functionality."""

    async def test_successful_gather(self):
        """Test gathering successful coroutines."""

        async def task(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2

        results = await safe_gather(task(1), task(2), task(3), description="test tasks")
        assert results == [2, 4, 6]

    async def test_gather_with_exceptions(self):
        """Test gathering with some failed coroutines."""

        async def failing_task() -> None:
            raise ValueError("Task failed")

        async def successful_task(value: int) -> int:
            return value

        results = await safe_gather(
            successful_task(1),
            failing_task(),
            successful_task(2),
            return_exceptions=True,
            description="mixed tasks",
        )

        assert len(results) == 3
        assert results[0] == 1
        assert isinstance(results[1], ValueError)
        assert results[2] == 2

    async def test_empty_gather(self):
        """Test gathering with no coroutines."""
        results = await safe_gather(description="empty")
        assert results == []

    async def test_base_exception_filtering(self):
        """Test filtering of non-Exception BaseExceptions."""

        # Create a custom BaseException that's not an Exception
        class CustomBaseException(BaseException):
            pass

        async def base_exception_task() -> None:
            raise CustomBaseException("Not an Exception")

        async def normal_task() -> str:
            return "success"

        # Test the gather behavior - it should filter out BaseExceptions that aren't Exceptions
        results = await safe_gather(
            normal_task(), base_exception_task(), return_exceptions=True, log_errors=False
        )

        # BaseException (non-Exception) should be filtered out
        assert len(results) == 1
        assert results[0] == "success"


class TestRateLimitedGather:
    """Test rate_limited_gather functionality."""

    async def test_semaphore_limiting(self):
        """Test that semaphore properly limits concurrency."""
        concurrent_count = 0
        max_concurrent = 0

        async def task() -> None:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.1)
            concurrent_count -= 1

        semaphore = asyncio.Semaphore(2)
        coros = [task() for _ in range(5)]

        await rate_limited_gather(coros, semaphore, "test tasks")

        # Max concurrent should not exceed semaphore limit
        assert max_concurrent <= 2


class TestAsyncRetry:
    """Test AsyncRetry functionality."""

    async def test_successful_first_attempt(self):
        """Test operation that succeeds on first attempt."""
        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        retry = AsyncRetry(max_attempts=3)
        result = await retry.execute(operation, "test op")

        assert result == "success"
        assert call_count == 1

    async def test_retry_on_failure(self):
        """Test operation that fails then succeeds."""
        call_count = 0

        async def operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        retry = AsyncRetry(max_attempts=3, base_delay=0.01)
        result = await retry.execute(operation, "test op")

        assert result == "success"
        assert call_count == 3

    async def test_max_attempts_exceeded(self):
        """Test operation that always fails."""
        call_count = 0

        async def operation() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent failure")

        retry = AsyncRetry(max_attempts=3, base_delay=0.01)

        with pytest.raises(ValueError, match="Permanent failure"):
            await retry.execute(operation, "test op")

        assert call_count == 3

    async def test_retry_specific_exceptions(self):
        """Test retrying only specific exception types."""
        call_count = 0

        async def operation() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Should retry")
            raise TypeError("Should not retry")

        retry = AsyncRetry(max_attempts=3, base_delay=0.01, retry_on=(ValueError,))

        with pytest.raises(TypeError, match="Should not retry"):
            await retry.execute(operation, "test op")

        # Should have tried twice: once for ValueError, once for TypeError
        assert call_count == 2

    async def test_exponential_backoff(self):
        """Test exponential backoff timing."""
        delays = []
        last_time = asyncio.get_event_loop().time()

        async def operation() -> None:
            nonlocal last_time
            current_time = asyncio.get_event_loop().time()
            delay = current_time - last_time
            delays.append(delay)
            last_time = current_time
            raise ValueError("Force retry")

        retry = AsyncRetry(max_attempts=3, base_delay=0.1, exponential_base=2.0)

        with pytest.raises(ValueError):
            await retry.execute(operation, "test op")

        # First delay should be ~0 (first attempt)
        # Second delay should be ~0.1 (base_delay)
        # Third delay should be ~0.2 (base_delay * 2)
        assert len(delays) == 3
        assert delays[1] >= 0.09  # Allow small variance
        assert delays[2] >= 0.19


class TestChunkedAsyncIter:
    """Test chunked_async_iter functionality."""

    async def test_basic_chunking(self):
        """Test basic chunking of items."""
        items = list(range(10))
        chunks = []

        async for chunk in chunked_async_iter(items, chunk_size=3):
            chunks.append(chunk)

        assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    async def test_chunk_delay(self):
        """Test delay between chunks."""
        items = list(range(6))
        times = []

        async for _chunk in chunked_async_iter(items, chunk_size=2, delay_between_chunks=0.1):
            times.append(asyncio.get_event_loop().time())

        # Should have delays between chunks (but not after last)
        assert len(times) == 3
        assert times[1] - times[0] >= 0.09
        assert times[2] - times[1] >= 0.09

    async def test_empty_list(self):
        """Test chunking empty list."""
        chunks = []
        async for chunk in chunked_async_iter([], chunk_size=5):
            chunks.append(chunk)

        assert chunks == []


class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    @pytest.fixture
    def isolated_metrics(self, monkeypatch):
        """Reset circuit breaker metrics for each test."""
        CircuitBreaker._metrics_initialized = False
        CircuitBreaker._state_gauge = None
        CircuitBreaker._failures_counter = None
        CircuitBreaker._success_counter = None
        CircuitBreaker._rejections_counter = None
        CircuitBreaker._state_changes_counter = None

        # Use isolated registry
        registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.async_utils.REGISTRY", registry)
        yield registry

    async def test_circuit_breaker_flow(self, isolated_metrics):
        """Test complete circuit breaker flow: closed -> open -> half-open -> closed."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            expected_exception=ValueError,
            name="test_breaker",
        )

        # Initial state should be CLOSED
        assert breaker._state == CircuitBreaker.State.CLOSED

        # First failure
        with pytest.raises(ValueError):
            await breaker.call(self._failing_operation, "op1")
        assert breaker._state == CircuitBreaker.State.CLOSED
        assert breaker._failure_count == 1

        # Second failure - should open circuit
        with pytest.raises(ValueError):
            await breaker.call(self._failing_operation, "op2")
        assert breaker._state == CircuitBreaker.State.OPEN
        assert breaker._failure_count == 2

        # Circuit is open - should reject calls
        with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
            await breaker.call(self._successful_operation, "op3")

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Should be in HALF_OPEN state, successful call should close circuit
        result = await breaker.call(self._successful_operation, "op4")
        assert result == "success"
        assert breaker._state == CircuitBreaker.State.CLOSED
        assert breaker._failure_count == 0

    async def test_half_open_failure(self, isolated_metrics):
        """Test circuit breaker going from half-open back to open on failure."""
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.1,
            expected_exception=ValueError,
            name="test_breaker",
        )

        # Open the circuit
        with pytest.raises(ValueError):
            await breaker.call(self._failing_operation, "op1")
        assert breaker._state == CircuitBreaker.State.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Fail in HALF_OPEN state - should go back to OPEN
        with pytest.raises(ValueError):
            await breaker.call(self._failing_operation, "op2")
        assert breaker._state == CircuitBreaker.State.OPEN

    async def test_unexpected_exception_not_counted(self, isolated_metrics):
        """Test that unexpected exceptions don't trigger circuit breaker."""
        breaker = CircuitBreaker(
            failure_threshold=2, expected_exception=ValueError, name="test_breaker"
        )

        # TypeError should not count as failure
        async def type_error_operation() -> None:
            raise TypeError("Different error")

        with pytest.raises(TypeError):
            await breaker.call(type_error_operation, "op1")

        assert breaker._failure_count == 0
        assert breaker._state == CircuitBreaker.State.CLOSED

    async def test_metrics_tracking(self, isolated_metrics):
        """Test that metrics are properly tracked."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            expected_exception=ValueError,
            name="metrics_test",
        )

        # Successful call
        await breaker.call(self._successful_operation, "op1")

        # Failures to open circuit
        with pytest.raises(ValueError):
            await breaker.call(self._failing_operation, "op2")
        with pytest.raises(ValueError):
            await breaker.call(self._failing_operation, "op3")

        # Rejection
        with pytest.raises(RuntimeError):
            await breaker.call(self._successful_operation, "op4")

        # Check metrics exist (actual values would need metric collection)
        assert CircuitBreaker._state_gauge is not None
        assert CircuitBreaker._failures_counter is not None
        assert CircuitBreaker._success_counter is not None
        assert CircuitBreaker._rejections_counter is not None
        assert CircuitBreaker._state_changes_counter is not None

    async def _failing_operation(self) -> None:
        """Helper method that always fails."""
        raise ValueError("Operation failed")

    async def _successful_operation(self) -> str:
        """Helper method that always succeeds."""
        return "success"
