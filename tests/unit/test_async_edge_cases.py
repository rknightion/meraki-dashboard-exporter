"""Async edge case tests for concurrency scenarios (Wave 2.3).

Tests cover:
- ManagedTaskGroup cancellation via timeout
- Bounded concurrency enforcement using timestamp-based verification
- OrgRateLimiter contention under concurrent access
- Task group exception propagation and cleanup
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.core.async_utils import ManagedTaskGroup
from meraki_dashboard_exporter.core.rate_limiter import OrgRateLimiter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(
    *,
    rate_limit_enabled: bool = True,
    rate_limit_requests_per_second: float = 5.0,
    rate_limit_shared_fraction: float = 1.0,
    rate_limit_burst: int = 1,
    rate_limit_jitter_ratio: float = 0.0,
) -> MagicMock:
    """Build a minimal mock Settings object for OrgRateLimiter."""
    settings = MagicMock()
    settings.api.rate_limit_enabled = rate_limit_enabled
    settings.api.rate_limit_requests_per_second = rate_limit_requests_per_second
    settings.api.rate_limit_shared_fraction = rate_limit_shared_fraction
    settings.api.rate_limit_burst = rate_limit_burst
    settings.api.rate_limit_jitter_ratio = rate_limit_jitter_ratio
    return settings


# ---------------------------------------------------------------------------
# 1. ManagedTaskGroup Cancellation
# ---------------------------------------------------------------------------


class TestManagedTaskGroupCancellation:
    """Verify that cancellation via asyncio.wait_for tears down the group cleanly."""

    async def test_cancel_group_via_wait_for(self) -> None:
        """Tasks are cancelled when the group is interrupted by a timeout."""
        cancelled_count = 0
        started_event = asyncio.Event()

        async def slow_task() -> None:
            nonlocal cancelled_count
            started_event.set()
            try:
                await asyncio.sleep(10)  # long enough to be interrupted
            except asyncio.CancelledError:
                cancelled_count += 1
                raise

        async def run_group() -> None:
            async with ManagedTaskGroup("cancellation_test") as group:
                for _ in range(5):
                    await group.create_task(slow_task())
                # Wait until at least one task has started before timing out
                await started_event.wait()
                await asyncio.sleep(10)  # this will be cancelled by wait_for

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await asyncio.wait_for(run_group(), timeout=0.3)

        # Allow cancellation callbacks to propagate
        await asyncio.sleep(0.05)

        # At least one slow task must have been cancelled
        assert cancelled_count >= 1

    async def test_no_orphaned_tasks_after_cancellation(self) -> None:
        """No tasks linger after the group is cancelled."""
        group_ref: ManagedTaskGroup | None = None

        async def slow_task() -> None:
            await asyncio.sleep(10)

        async def run_group() -> None:
            nonlocal group_ref
            async with ManagedTaskGroup("orphan_check") as group:
                group_ref = group
                for _ in range(3):
                    await group.create_task(slow_task())
                await asyncio.sleep(10)

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await asyncio.wait_for(run_group(), timeout=0.2)

        await asyncio.sleep(0.05)

        assert group_ref is not None
        # All tasks should be done (cancelled or finished)
        for task in group_ref.tasks:
            assert task.done(), "Orphaned task found after cancellation"

    async def test_cancel_does_not_affect_already_completed_tasks(self) -> None:
        """Tasks that complete before cancellation are unaffected."""
        completed = []

        async def fast_task(i: int) -> None:
            await asyncio.sleep(0)  # yield, then complete immediately
            completed.append(i)

        async def slow_task() -> None:
            await asyncio.sleep(10)

        async def run_group() -> None:
            async with ManagedTaskGroup("mixed_tasks") as group:
                for i in range(3):
                    await group.create_task(fast_task(i))
                # Give fast tasks time to complete
                await asyncio.sleep(0.05)
                await group.create_task(slow_task())
                await asyncio.sleep(10)  # triggers cancellation

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await asyncio.wait_for(run_group(), timeout=0.2)

        await asyncio.sleep(0.05)
        # All three fast tasks completed before the timeout
        assert sorted(completed) == [0, 1, 2]


# ---------------------------------------------------------------------------
# 2. Semaphore Exhaustion / Bounded Concurrency
# ---------------------------------------------------------------------------


class TestBoundedConcurrency:
    """Verify that max_concurrency is respected using overlapping time windows."""

    async def test_at_most_max_concurrency_tasks_overlap(self) -> None:
        """Timestamp analysis confirms <= max_concurrency tasks run simultaneously."""
        max_concurrency = 2
        task_count = 6
        task_duration = 0.08  # seconds each task holds the semaphore

        # Each entry: (start_time, end_time)
        intervals: list[tuple[float, float]] = []

        async def timed_task() -> None:
            start = time.monotonic()
            await asyncio.sleep(task_duration)
            end = time.monotonic()
            intervals.append((start, end))

        async with ManagedTaskGroup("bounded", max_concurrency=max_concurrency) as group:
            for _ in range(task_count):
                await group.create_task(timed_task())

        assert len(intervals) == task_count

        # For every moment in time, count how many tasks were active.
        # We check at each task's start time (a dense set of checkpoints).
        for check_time, _ in intervals:
            overlap = sum(1 for s, e in intervals if s <= check_time < e)
            assert overlap <= max_concurrency, (
                f"At time {check_time:.4f}s, {overlap} tasks were running "
                f"(limit is {max_concurrency})"
            )

    async def test_all_tasks_complete_despite_limit(self) -> None:
        """Every submitted task eventually runs even with a tight concurrency cap."""
        completed: list[int] = []

        async def work(i: int) -> None:
            await asyncio.sleep(0.02)
            completed.append(i)

        async with ManagedTaskGroup("all_complete", max_concurrency=2) as group:
            for i in range(8):
                await group.create_task(work(i))

        assert sorted(completed) == list(range(8))

    async def test_active_count_tracks_semaphore_slots(self) -> None:
        """Internal _active_count never exceeds max_concurrency."""
        max_concurrency = 3
        max_observed: list[int] = []

        async def observer_task(group: ManagedTaskGroup) -> None:
            # Record the active count while holding the semaphore slot
            max_observed.append(group._active_count)
            await asyncio.sleep(0.05)

        async with ManagedTaskGroup("active_count", max_concurrency=max_concurrency) as group:
            for _ in range(9):
                await group.create_task(observer_task(group))

        assert max(max_observed) <= max_concurrency


# ---------------------------------------------------------------------------
# 3. Rate Limiter Contention
# ---------------------------------------------------------------------------


class TestRateLimiterContention:
    """Verify OrgRateLimiter enforces throughput limits under concurrent load."""

    async def test_throughput_bounded_under_concurrent_acquire(self) -> None:
        """10 concurrent acquires at 5 req/s should take at least ~1.5s."""
        # burst=1 means no burst benefit beyond a single token.
        # With rate=5/s and burst=1, each token costs 0.2s.
        # 10 tokens at 5/s = 2s minimum, but first token is free (bucket starts full).
        # So 9 waits × 0.2s = 1.8s minimum.  We allow generous lower bound of 1.5s.
        settings = _make_mock_settings(
            rate_limit_requests_per_second=5.0,
            rate_limit_burst=1,
            rate_limit_jitter_ratio=0.0,
        )
        # Reset class-level flag so metrics are re-registered with the clean registry
        OrgRateLimiter._metrics_initialized = False

        limiter = OrgRateLimiter(settings)

        async def acquire_once() -> float:
            return await limiter.acquire(org_id="test_org", endpoint="test")

        start = time.monotonic()
        await asyncio.gather(*(acquire_once() for _ in range(10)))
        elapsed = time.monotonic() - start

        # 10 calls at 5/s with burst=1: first is free, remaining 9 cost 0.2s each.
        assert elapsed >= 1.5, f"Rate limiter too permissive: completed in {elapsed:.3f}s"

    async def test_disabled_rate_limiter_returns_immediately(self) -> None:
        """Disabled limiter imposes no delay at all."""
        settings = _make_mock_settings(rate_limit_enabled=False)
        OrgRateLimiter._metrics_initialized = False

        limiter = OrgRateLimiter(settings)

        start = time.monotonic()
        results = await asyncio.gather(
            *(limiter.acquire(org_id="org1", endpoint="ep") for _ in range(20))
        )
        elapsed = time.monotonic() - start

        assert all(r == 0.0 for r in results)
        assert elapsed < 0.5, f"Disabled limiter should return instantly, took {elapsed:.3f}s"

    async def test_per_org_isolation(self) -> None:
        """Each org_id has its own token bucket; one org's drain doesn't affect another."""
        settings = _make_mock_settings(
            rate_limit_requests_per_second=5.0,
            rate_limit_burst=5,  # generous burst so first 5 calls are free per org
            rate_limit_jitter_ratio=0.0,
        )
        OrgRateLimiter._metrics_initialized = False

        limiter = OrgRateLimiter(settings)

        # Drain org_a's burst budget completely (5 calls), using rate limit freely
        for _ in range(5):
            await limiter.acquire(org_id="org_a", endpoint="ep")

        # org_b has never been touched; its first call should be instant (full bucket)
        start = time.monotonic()
        wait = await limiter.acquire(org_id="org_b", endpoint="ep")
        elapsed = time.monotonic() - start

        assert wait == 0.0, "First call to untouched org_b should not wait"
        assert elapsed < 0.1, f"org_b acquire took unexpectedly long: {elapsed:.3f}s"

    async def test_concurrent_same_org_serialized_by_lock(self) -> None:
        """Concurrent acquires for the same org are serialized (no token double-spend)."""
        settings = _make_mock_settings(
            rate_limit_requests_per_second=100.0,  # fast rate for timing stability
            rate_limit_burst=3,
            rate_limit_jitter_ratio=0.0,
        )
        OrgRateLimiter._metrics_initialized = False

        limiter = OrgRateLimiter(settings)

        # Fire 6 concurrent acquires; burst=3 means first 3 are free, next 3 wait
        results = await asyncio.gather(
            *(limiter.acquire(org_id="org_x", endpoint="ep") for _ in range(6))
        )

        zero_waits = sum(1 for r in results if r == 0.0)
        non_zero_waits = sum(1 for r in results if r > 0.0)

        # Exactly burst=3 calls should be served from the full bucket without waiting.
        # The remaining 3 must have waited.
        assert zero_waits == 3, f"Expected 3 free tokens, got {zero_waits}"
        assert non_zero_waits == 3, f"Expected 3 throttled calls, got {non_zero_waits}"


# ---------------------------------------------------------------------------
# 4. Task Group Exception Handling
# ---------------------------------------------------------------------------


class TestTaskGroupExceptionHandling:
    """Verify exception propagation and cleanup when tasks or the context raises."""

    async def test_exception_in_context_body_cancels_tasks(self) -> None:
        """An exception raised inside the context cancels all running tasks."""
        cancelled_count = 0

        async def long_running() -> None:
            nonlocal cancelled_count
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled_count += 1
                raise

        with pytest.raises(RuntimeError, match="deliberate"):
            async with ManagedTaskGroup("exc_propagation") as group:
                for _ in range(4):
                    await group.create_task(long_running())
                await asyncio.sleep(0.02)  # let tasks start
                raise RuntimeError("deliberate")

        await asyncio.sleep(0.05)
        assert cancelled_count == 4

    async def test_original_exception_propagates_through_exit(self) -> None:
        """The original exception is re-raised after cleanup; it is not swallowed."""

        async def dummy() -> None:
            await asyncio.sleep(0)

        with pytest.raises(ValueError, match="original"):
            async with ManagedTaskGroup("exc_identity") as group:
                await group.create_task(dummy())
                # Yield to event loop so the task has a chance to start before
                # we raise, avoiding a "coroutine never awaited" warning.
                await asyncio.sleep(0)
                raise ValueError("original")

    async def test_task_exception_does_not_propagate_to_caller(self) -> None:
        """An exception inside a task is logged but does NOT surface to the caller.

        ManagedTaskGroup gathers tasks with return_exceptions=True on exit,
        so individual task failures are absorbed.
        """

        async def failing_task() -> None:
            raise ValueError("task error")

        async def ok_task() -> None:
            await asyncio.sleep(0.01)

        # Must not raise
        async with ManagedTaskGroup("task_exc_absorbed") as group:
            await group.create_task(failing_task())
            await group.create_task(ok_task())

    async def test_multiple_task_failures_all_absorbed(self) -> None:
        """All task-level exceptions are absorbed; none surfaces."""

        async def always_fails(i: int) -> None:
            raise RuntimeError(f"failure {i}")

        # Must not raise
        async with ManagedTaskGroup("multi_fail") as group:
            for i in range(5):
                await group.create_task(always_fails(i))

    async def test_group_stats_correct_after_exception(self) -> None:
        """Statistics remain consistent when the context body raises."""

        async def quick() -> None:
            await asyncio.sleep(0.01)

        with pytest.raises(TypeError):
            async with ManagedTaskGroup("stats_exc") as group:
                await group.create_task(quick())
                await group.create_task(quick())
                await asyncio.sleep(0.02)
                raise TypeError("stats test")

        # All 2 tasks were created; they may have completed or been cancelled
        assert group._total_created == 2

    async def test_closed_group_raises_on_create_task(self) -> None:
        """Creating a task on a closed group raises RuntimeError immediately."""
        group = ManagedTaskGroup("closed_group")
        async with group:
            pass  # close the group

        async def unused() -> None:
            pass  # pragma: no cover

        coro = unused()
        try:
            with pytest.raises(RuntimeError, match="Cannot add tasks to closed group"):
                await group.create_task(coro)
        finally:
            coro.close()
