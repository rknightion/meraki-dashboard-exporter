"""Tests for async utilities and patterns."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from meraki_dashboard_exporter.core.async_utils import (
    AsyncRetry,
    ManagedTaskGroup,
    chunked_async_iter,
    managed_resource,
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
                await asyncio.sleep(1)  # Long running task
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
            await asyncio.sleep(0.5)
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

        retry = AsyncRetry(max_attempts=3, base_delay=0.01, exponential_base=2.0)

        with pytest.raises(ValueError):
            await retry.execute(operation, "test op")

        # First delay should be ~0 (first attempt)
        # Second delay should be ~0.01 (base_delay)
        # Third delay should be ~0.02 (base_delay * 2)
        assert len(delays) == 3
        assert delays[1] >= 0.009  # Allow small variance
        assert delays[2] >= 0.019


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

        async for _chunk in chunked_async_iter(items, chunk_size=2, delay_between_chunks=0.02):
            times.append(asyncio.get_event_loop().time())

        # Should have delays between chunks (but not after last)
        assert len(times) == 3
        assert times[1] - times[0] >= 0.019
        assert times[2] - times[1] >= 0.019

    async def test_empty_list(self):
        """Test chunking empty list."""
        chunks = []
        async for chunk in chunked_async_iter([], chunk_size=5):
            chunks.append(chunk)

        assert chunks == []
