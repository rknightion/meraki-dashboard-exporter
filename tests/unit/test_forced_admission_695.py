"""Regression coverage for atomic forced-collection admission (#695)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.manager import CollectorManager


def _bare_manager(limit: int) -> CollectorManager:
    manager = object.__new__(CollectorManager)
    manager._collector_locks = {}
    manager._collector_semaphore = asyncio.Semaphore(limit)
    manager.collector_health = {}
    manager._collector_succeeded = set()
    manager._parallel_collections_active = MagicMock()
    manager._collection_errors = MagicMock()
    manager._collector_failure_streak = MagicMock()
    manager._collection_utilization = MagicMock()
    manager._task_metrics = MagicMock()
    return manager


def _collector(name: str, collect: AsyncMock | None = None) -> MagicMock:
    collector = MagicMock()
    collector.__class__ = type(name, (), {})
    collector.collect = collect or AsyncMock()
    collector.collector_cadence_seconds.return_value = 300.0
    return collector


def _health() -> dict[str, float | int | None]:
    return {
        "last_success_time": None,
        "failure_streak": 0,
        "total_runs": 0,
        "total_successes": 0,
        "total_failures": 0,
    }


@pytest.mark.asyncio
async def test_second_forced_run_is_rejected_before_first_gets_semaphore() -> None:
    """A queued admitted run owns the per-collector lock immediately."""
    manager = _bare_manager(0)
    collector = _collector("DeviceCollector")

    first = asyncio.create_task(manager._run_collector_with_timeout(collector, 30, force=True))
    await asyncio.sleep(0)
    second = asyncio.create_task(manager._run_collector_with_timeout(collector, 30, force=True))
    await asyncio.sleep(0)

    assert manager._collector_locks["DeviceCollector"].locked()
    assert second.done()

    manager._collector_semaphore.release()
    await first
    await second
    collector.collect.assert_awaited_once()


@pytest.mark.asyncio
async def test_queued_collector_expiry_is_saturation_not_endpoint_failure() -> None:
    """A concurrent queue expiry never starts or poisons the queued collector."""
    manager = _bare_manager(1)
    release = asyncio.Event()
    blocker_started = asyncio.Event()

    async def block() -> None:
        blocker_started.set()
        await release.wait()

    blocker = _collector("BlockerCollector", AsyncMock(side_effect=block))
    queued = _collector("QueuedCollector")
    manager.collector_health = {
        "BlockerCollector": _health(),
        "QueuedCollector": _health(),
    }

    blocker_task = asyncio.create_task(manager._run_collector_with_timeout(blocker, 1.0))
    await blocker_started.wait()
    await manager._run_collector_with_timeout(queued, 0.02)

    queued.collect.assert_not_awaited()
    assert manager.collector_health["QueuedCollector"] == _health()
    manager._task_metrics.expired_before_start.labels.assert_called_with(
        phase="collector_admission"
    )
    manager._task_metrics.expired_before_start.labels.return_value.inc.assert_called_once_with()

    release.set()
    await blocker_task


@pytest.mark.asyncio
async def test_queue_wait_and_execution_share_one_wall_clock_budget() -> None:
    """Execution receives only the configured run budget left after admission."""
    manager = _bare_manager(0)
    body_started = asyncio.Event()
    body_cancelled = asyncio.Event()

    async def slow_body() -> None:
        body_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            body_cancelled.set()
            raise

    collector = _collector("SlowCollector", AsyncMock(side_effect=slow_body))
    manager.collector_health = {"SlowCollector": _health()}

    async def release_admission() -> None:
        await asyncio.sleep(0.12)
        manager._collector_semaphore.release()

    releaser = asyncio.create_task(release_admission())
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    await manager._run_collector_with_timeout(collector, 0.25)
    elapsed = loop.time() - started_at
    await releaser

    assert body_started.is_set()
    assert body_cancelled.is_set()
    assert 0.20 <= elapsed < 0.32
