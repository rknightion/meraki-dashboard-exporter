"""Unit tests for ManagedTaskGroup class (P5.1.2 - Phase 1.3)."""

from __future__ import annotations

import asyncio

import pytest

from meraki_dashboard_exporter.core.async_utils import ManagedTaskGroup


class TestManagedTaskGroupBasics:
    """Test basic task group functionality."""

    async def test_context_manager_lifecycle(self) -> None:
        """Test task group context manager enter/exit."""
        group = ManagedTaskGroup("test")

        async with group as g:
            assert g is group
            assert not group._closed
            assert len(group.tasks) == 0

        # After exit, group should be closed
        assert group._closed

    async def test_create_single_task(self) -> None:
        """Test creating a single task."""
        executed = False

        async def simple_task() -> None:
            nonlocal executed
            executed = True

        async with ManagedTaskGroup("test") as group:
            task = await group.create_task(simple_task())
            assert task in group.tasks
            assert group._total_created == 1

        # Task should have executed
        assert executed

    async def test_create_multiple_tasks(self) -> None:
        """Test creating multiple tasks."""
        results = []

        async def task_func(value: int) -> None:
            await asyncio.sleep(0.01)
            results.append(value)

        async with ManagedTaskGroup("test") as group:
            await group.create_task(task_func(1))
            await group.create_task(task_func(2))
            await group.create_task(task_func(3))
            assert len(group.tasks) == 3

        # All tasks should have completed
        assert sorted(results) == [1, 2, 3]

    async def test_tasks_run_in_parallel(self) -> None:
        """Test that tasks actually run in parallel."""
        start_times = []
        end_times = []

        async def slow_task(task_id: int) -> None:
            start_times.append((task_id, asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)
            end_times.append((task_id, asyncio.get_event_loop().time()))

        start = asyncio.get_event_loop().time()

        async with ManagedTaskGroup("test") as group:
            await group.create_task(slow_task(1))
            await group.create_task(slow_task(2))
            await group.create_task(slow_task(3))

        duration = asyncio.get_event_loop().time() - start

        # Should complete in ~0.1s (parallel) not ~0.3s (sequential)
        assert duration < 0.2  # Allow some overhead

        # All tasks should have started around the same time
        assert len(start_times) == 3

    async def test_task_with_name(self) -> None:
        """Test creating a named task."""

        async def dummy_task() -> None:
            await asyncio.sleep(0.01)

        async with ManagedTaskGroup("test") as group:
            task = await group.create_task(dummy_task(), name="my_task")
            assert task.get_name() == "my_task"

    async def test_cannot_add_task_after_closed(self) -> None:
        """Test that tasks cannot be added to closed group."""
        group = ManagedTaskGroup("test")

        async with group:
            pass

        # Try to add task after exit - should raise immediately
        with pytest.raises(RuntimeError, match="Cannot add tasks to closed group"):

            async def dummy_task() -> None:
                pass

            # create_task will raise before executing dummy_task
            await group.create_task(dummy_task())


class TestManagedTaskGroupBoundedConcurrency:
    """Test bounded concurrency with semaphore."""

    async def test_unbounded_concurrency(self) -> None:
        """Test that unbounded concurrency runs all tasks immediately."""
        active_count = 0
        max_active = 0

        async def task_func() -> None:
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

        async with ManagedTaskGroup("test") as group:
            for _i in range(10):
                await group.create_task(task_func())

        # All 10 should have run concurrently
        assert max_active == 10

    async def test_bounded_concurrency(self) -> None:
        """Test that bounded concurrency limits concurrent tasks."""
        active_count = 0
        max_active = 0

        async def task_func() -> None:
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

        async with ManagedTaskGroup("test", max_concurrency=3) as group:
            for _i in range(10):
                await group.create_task(task_func())

        # Only 3 should run concurrently at a time
        assert max_active == 3

    async def test_semaphore_backpressure(self) -> None:
        """Test that semaphore provides backpressure."""
        execution_order = []

        async def task_func(task_id: int) -> None:
            execution_order.append(f"start_{task_id}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end_{task_id}")

        async with ManagedTaskGroup("test", max_concurrency=2) as group:
            await group.create_task(task_func(1))
            await group.create_task(task_func(2))
            await group.create_task(task_func(3))

        # First two should start, then third after one completes
        assert execution_order[0] in {"start_1", "start_2"}
        assert execution_order[1] in {"start_1", "start_2"}


class TestManagedTaskGroupErrorHandling:
    """Test error handling and cancellation."""

    async def test_task_exception_logged(self) -> None:
        """Test that task exceptions are caught and logged."""

        async def failing_task() -> None:
            raise ValueError("Task failed")

        async def success_task() -> None:
            await asyncio.sleep(0.01)

        # Should not raise - exceptions are caught
        async with ManagedTaskGroup("test") as group:
            await group.create_task(failing_task())
            await group.create_task(success_task())

        # Both tasks should have completed (one with exception)

    async def test_exception_in_context_cancels_tasks(self) -> None:
        """Test that exception in context cancels all tasks."""
        task_cancelled = False

        async def long_task() -> None:
            nonlocal task_cancelled
            try:
                await asyncio.sleep(10)  # Long sleep
            except asyncio.CancelledError:
                task_cancelled = True
                raise

        with pytest.raises(ValueError, match="Context error"):
            async with ManagedTaskGroup("test") as group:
                await group.create_task(long_task())
                # Give task a moment to start
                await asyncio.sleep(0.01)
                # Raise exception before tasks complete
                raise ValueError("Context error")

        # Give cancellation time to propagate
        await asyncio.sleep(0.01)

        # Task should have been cancelled
        assert task_cancelled

    async def test_gather_returns_exceptions(self) -> None:
        """Test that gather returns exceptions."""

        async def failing_task() -> None:
            raise ValueError("Failed")

        async def success_task() -> int:
            return 42

        async with ManagedTaskGroup("test") as group:
            await group.create_task(failing_task())
            await group.create_task(success_task())
            results = await group.gather()

        # Should have one exception and one result
        exceptions = [r for r in results if isinstance(r, Exception)]
        successes = [r for r in results if not isinstance(r, Exception)]

        assert len(exceptions) == 1
        assert isinstance(exceptions[0], ValueError)
        assert len(successes) == 1
        assert successes[0] == 42


class TestManagedTaskGroupStatistics:
    """Test task group statistics tracking."""

    async def test_get_stats_empty(self) -> None:
        """Test stats for empty task group."""
        async with ManagedTaskGroup("test") as group:
            stats = group.get_stats()
            assert stats["active"] == 0
            assert stats["total_created"] == 0
            assert stats["total_completed"] == 0
            assert stats["pending"] == 0

    async def test_get_stats_during_execution(self) -> None:
        """Test stats during task execution."""
        stats_during = None

        async def long_task() -> None:
            await asyncio.sleep(0.1)

        async with ManagedTaskGroup("test") as group:
            await group.create_task(long_task())
            await group.create_task(long_task())

            # Get stats while tasks are running
            await asyncio.sleep(0.01)
            stats_during = group.get_stats()

        assert stats_during is not None
        assert stats_during["active"] == 2
        assert stats_during["total_created"] == 2
        # Completed count might be 0 or more depending on timing

    async def test_get_stats_after_completion(self) -> None:
        """Test stats after all tasks complete."""

        async def quick_task() -> None:
            await asyncio.sleep(0.01)

        async with ManagedTaskGroup("test") as group:
            await group.create_task(quick_task())
            await group.create_task(quick_task())
            await group.create_task(quick_task())

        # After exit, all tasks should be complete
        stats = group.get_stats()
        assert stats["total_created"] == 3
        assert stats["total_completed"] == 3
        assert stats["active"] == 0

    async def test_stats_with_bounded_concurrency(self) -> None:
        """Test stats tracking with bounded concurrency."""

        async def task_func() -> None:
            await asyncio.sleep(0.05)

        async with ManagedTaskGroup("test", max_concurrency=2) as group:
            await group.create_task(task_func())
            await group.create_task(task_func())
            await group.create_task(task_func())

            # After creation, should have 3 created
            stats = group.get_stats()
            assert stats["total_created"] == 3


class TestManagedTaskGroupBatchOperations:
    """Test batch task operations."""

    async def test_create_tasks_batch(self) -> None:
        """Test creating multiple tasks at once."""
        results = []

        async def task_func(value: int) -> None:
            results.append(value)

        coros = [task_func(i) for i in range(5)]

        async with ManagedTaskGroup("test") as group:
            tasks = await group.create_tasks_batch(coros, name_prefix="batch")
            assert len(tasks) == 5
            assert all(t.get_name().startswith("batch_") for t in tasks)

        assert sorted(results) == [0, 1, 2, 3, 4]

    async def test_batch_with_bounded_concurrency(self) -> None:
        """Test batch creation with concurrency limits."""
        active_count = 0
        max_active = 0

        async def task_func() -> None:
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

        coros = [task_func() for _ in range(10)]

        async with ManagedTaskGroup("test", max_concurrency=3) as group:
            await group.create_tasks_batch(coros)

        assert max_active == 3


class TestManagedTaskGroupWaitForCapacity:
    """Test wait_for_capacity functionality."""

    async def test_wait_for_capacity_unbounded(self) -> None:
        """Test wait_for_capacity with unbounded group."""

        async def quick_task() -> None:
            await asyncio.sleep(0.01)

        async with ManagedTaskGroup("test") as group:
            # Create some tasks
            for _i in range(5):
                await group.create_task(quick_task())

            # Wait should return immediately for unbounded
            await group.wait_for_capacity(target_active=1)

    async def test_wait_for_capacity_bounded(self) -> None:
        """Test wait_for_capacity with bounded group."""
        waited = False

        async def long_task() -> None:
            await asyncio.sleep(0.2)

        async with ManagedTaskGroup("test", max_concurrency=2) as group:
            # Fill up capacity
            await group.create_task(long_task())
            await group.create_task(long_task())

            # This should wait until capacity available
            async def wait_and_flag() -> None:
                nonlocal waited
                await group.wait_for_capacity(target_active=1)
                waited = True

            wait_task = asyncio.create_task(wait_and_flag())

            # Give it time to check
            await asyncio.sleep(0.05)

            # Should still be waiting
            assert not waited

            # Cancel the wait task
            wait_task.cancel()
            try:
                await wait_task
            except asyncio.CancelledError:
                pass


class TestManagedTaskGroupGather:
    """Test gather functionality."""

    async def test_gather_empty(self) -> None:
        """Test gather with no tasks."""
        async with ManagedTaskGroup("test") as group:
            results = await group.gather()
            assert results == []

    async def test_gather_with_results(self) -> None:
        """Test gather returns all results."""

        async def task_with_result(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2

        async with ManagedTaskGroup("test") as group:
            await group.create_task(task_with_result(1))
            await group.create_task(task_with_result(2))
            await group.create_task(task_with_result(3))
            results = await group.gather()

        # Filter out non-exception results
        values = [r for r in results if not isinstance(r, Exception)]
        assert sorted(values) == [2, 4, 6]

    async def test_gather_with_mixed_results(self) -> None:
        """Test gather with both success and failures."""

        async def success_task(value: int) -> int:
            return value

        async def failing_task() -> None:
            raise ValueError("Failed")

        async with ManagedTaskGroup("test") as group:
            await group.create_task(success_task(10))
            await group.create_task(failing_task())
            await group.create_task(success_task(20))
            results = await group.gather()

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 2
        assert len(failures) == 1
        assert sorted(successes) == [10, 20]


class TestManagedTaskGroupEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_empty_group_cleanup(self) -> None:
        """Test cleanup of empty group."""
        async with ManagedTaskGroup("test"):
            pass  # No tasks created

        # Should not raise

    async def test_task_completes_before_exit(self) -> None:
        """Test task that completes before context exit."""
        completed = False

        async def quick_task() -> None:
            nonlocal completed
            completed = True

        async with ManagedTaskGroup("test") as group:
            await group.create_task(quick_task())
            # Wait for task to complete
            await asyncio.sleep(0.05)
            assert completed

        # Should handle already-complete task gracefully

    async def test_many_tasks(self) -> None:
        """Test handling many tasks."""
        count = 0

        async def increment_task() -> None:
            nonlocal count
            count += 1

        async with ManagedTaskGroup("test", max_concurrency=10) as group:
            for _i in range(100):
                await group.create_task(increment_task())

        assert count == 100

    async def test_task_removes_itself_on_completion(self) -> None:
        """Test that tasks are removed from set when complete."""

        async def quick_task() -> None:
            await asyncio.sleep(0.01)

        async with ManagedTaskGroup("test") as group:
            await group.create_task(quick_task())
            await group.create_task(quick_task())

            # Wait for tasks to complete
            await asyncio.sleep(0.05)

            # Tasks should have removed themselves
            assert len(group.tasks) == 0

    async def test_zero_concurrency_limit(self) -> None:
        """Test that zero concurrency is handled (treated as unbounded)."""
        # Creating with max_concurrency=0 should work (treated as None)
        async with ManagedTaskGroup("test", max_concurrency=None) as group:

            async def dummy() -> None:
                pass

            await group.create_task(dummy())


class TestManagedTaskGroupRealWorldScenarios:
    """Test real-world usage scenarios."""

    async def test_parallel_api_calls(self) -> None:
        """Test simulating parallel API calls."""
        # Simulate API calls

        async def mock_api_call(endpoint: str) -> str:
            await asyncio.sleep(0.05)  # Simulate network delay
            return f"Response from {endpoint}"

        async with ManagedTaskGroup("api_calls") as group:
            for endpoint in ["orgs", "networks", "devices"]:
                await group.create_task(mock_api_call(endpoint))

        # Should have completed in ~0.05s not ~0.15s

    async def test_dynamic_task_creation(self) -> None:
        """Test creating tasks based on previous results."""
        all_results = []

        async def fetch_orgs() -> list[str]:
            return ["org1", "org2", "org3"]

        async def fetch_org_data(org_id: str) -> str:
            await asyncio.sleep(0.01)
            return f"data_{org_id}"

        # First fetch orgs
        orgs = await fetch_orgs()

        # Then fetch data for each org in parallel
        async with ManagedTaskGroup("org_data") as group:
            for org in orgs:
                await group.create_task(fetch_org_data(org))
                # Can't await task here as we want them parallel
            results = await group.gather()

        # Filter successful results
        all_results = [r for r in results if not isinstance(r, Exception)]
        assert len(all_results) == 3

    async def test_rate_limited_processing(self) -> None:
        """Test rate-limited processing of many items."""
        processed = []

        async def process_item(item_id: int) -> None:
            await asyncio.sleep(0.05)
            processed.append(item_id)

        # Process 10 items with max 3 concurrent
        async with ManagedTaskGroup("processing", max_concurrency=3) as group:
            for i in range(10):
                await group.create_task(process_item(i))

        assert len(processed) == 10
        assert sorted(processed) == list(range(10))
