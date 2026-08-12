"""Regression coverage for bounded task admission and collector queue expiry (#710)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.manager import (
    CollectorManager,
    calculate_collector_admission_limit,
)
from meraki_dashboard_exporter.core.async_utils import ManagedTaskGroup, get_task_admission_metrics
from tests.fixtures.fleet import PRESET_PARAMETERS, FleetPreset


@pytest.mark.parametrize(
    ("collectors", "fanout", "workers", "expected"),
    [(5, 5, 10, 2), (1, 5, 10, 1), (5, 5, 32, 5)],
)
def test_collector_admission_is_aligned_with_executor_capacity(
    collectors: int,
    fanout: int,
    workers: int,
    expected: int,
) -> None:
    """Outer admission cannot create an invisible SDK executor queue."""
    settings = SimpleNamespace(
        collectors=SimpleNamespace(max_concurrent_collectors=collectors),
        api=SimpleNamespace(concurrency_limit=fanout, executor_workers=workers),
    )

    assert calculate_collector_admission_limit(settings) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("preset", [FleetPreset.CAMPUS, FleetPreset.DENSE_SWITCH])
async def test_bounded_admission_does_not_allocate_the_full_fleet_fanout(
    preset: FleetPreset,
) -> None:
    """CAMPUS and DENSE-SWITCH producers pause at the configured worker bound."""
    parameters = PRESET_PARAMETERS[preset]
    fanout = parameters.networks_per_org * sum(parameters.devices_per_network.values())
    worker_limit = 3
    release_workers = asyncio.Event()
    workers_at_limit = asyncio.Event()
    constructed = 0
    active = 0
    peak_active = 0

    async def worker() -> None:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        if active == worker_limit:
            workers_at_limit.set()
        await release_workers.wait()
        active -= 1

    async with ManagedTaskGroup("fleet_admission", max_concurrency=worker_limit) as group:

        async def produce() -> None:
            nonlocal constructed
            for _ in range(fanout):
                constructed += 1
                await group.create_task(worker())

        producer = asyncio.create_task(produce())
        await asyncio.wait_for(workers_at_limit.wait(), timeout=1)
        await asyncio.sleep(0)

        stats = group.get_stats()
        assert not producer.done()
        assert constructed <= worker_limit + 1
        assert len(group.tasks) == worker_limit
        assert stats["active"] == worker_limit
        assert stats["pending"] == 1
        assert peak_active == worker_limit

        release_workers.set()
        await producer

    assert constructed == fanout
    assert peak_active == worker_limit


def _bare_manager() -> CollectorManager:
    """Construct only the manager state used by admission tests."""
    manager = object.__new__(CollectorManager)
    manager._collector_locks = {}
    manager._collector_semaphore = asyncio.Semaphore(1)
    manager.collector_health = {}
    manager._collector_succeeded = set()
    manager._parallel_collections_active = MagicMock()
    manager._collection_errors = MagicMock()
    manager._collection_utilization = MagicMock()
    manager._collector_failure_streak = MagicMock()
    manager._task_metrics = get_task_admission_metrics()
    return manager


def _collector() -> MagicMock:
    """Return a minimal collector compatible with manager execution bookkeeping."""
    collector = MagicMock()
    collector.__class__ = type("QueueTestCollector", (), {})
    collector.collect = AsyncMock()
    collector.collector_cadence_seconds.return_value = 300.0
    return collector


@pytest.mark.asyncio
async def test_collector_admission_expiry_is_distinct_from_upstream_timeout() -> None:
    """A run that cannot start is not reported as a slow collector execution."""
    manager = _bare_manager()
    collection_errors = MagicMock()
    manager._collection_errors = collection_errors
    collector = _collector()
    collector_name = collector.__class__.__name__
    manager.collector_health[collector_name] = {
        "last_success_time": None,
        "failure_streak": 0,
        "total_runs": 0,
        "total_successes": 0,
        "total_failures": 0,
    }

    await manager._collector_semaphore.acquire()
    await manager._run_collector_with_timeout(collector, timeout=0)

    collector.collect.assert_not_awaited()
    collection_errors.labels.assert_called_with(
        collector=collector_name,
        error_type="TaskExpiredBeforeStartError",
    )
    assert manager.collector_health[collector_name]["total_failures"] == 1
    assert not manager._collector_locks[collector_name].locked()

    manager._collector_semaphore.release()

    async def slow_collection() -> None:
        await asyncio.sleep(1)

    collector.collect.side_effect = slow_collection
    await manager._run_collector_with_timeout(collector, timeout=0)

    assert collection_errors.labels.call_args_list[-1].kwargs == {
        "collector": collector_name,
        "error_type": "TimeoutError",
    }
