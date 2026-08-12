"""Regression coverage for atomic forced-collection admission (#695)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.manager import CollectorManager


@pytest.mark.asyncio
async def test_second_forced_run_is_rejected_before_first_gets_semaphore() -> None:
    """A queued admitted run owns the per-collector lock immediately."""
    manager = object.__new__(CollectorManager)
    manager._collector_locks = {}
    manager._collector_semaphore = asyncio.Semaphore(0)
    manager.collector_health = {}
    manager._parallel_collections_active = MagicMock()
    manager._collection_errors = MagicMock()
    manager._collection_utilization = MagicMock()

    collector = MagicMock()
    collector.__class__ = type("DeviceCollector", (), {})
    collector.collect = AsyncMock()
    collector.collector_cadence_seconds.return_value = 300.0

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
