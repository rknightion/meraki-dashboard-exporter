"""Tests for the adaptive scheduler resolve loop + #596 liveness contract (#617).

Covers Lane A of the #617 build:

* ``_scheduler_resolve_loop`` early-re-solves on AIMD (``needs_resolve``),
  re-solves on the scheduled ``resolve_interval_seconds`` cadence, and cancels
  cleanly on shutdown.
* ``_startup_collections`` wires the resolve loop as a tracked background task.
* #596: the liveness threshold derivation is unaffected by the scheduler mode
  (adaptive vs fixed) - endpoint groups never run faster than their heartbeat,
  so the tier derivation IS the fastest cadence.

The scheduler/inventory seams are owned by other lanes (manager.py / inventory.py)
and are mocked here.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings


@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings; scheduler defaults to adaptive mode."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


def _wire_scheduler(
    exporter: ExporterApp,
    *,
    needs_resolve: bool,
    shape: object,
) -> tuple[MagicMock, MagicMock]:
    """Inject mock scheduler + inventory seams onto the collector manager."""
    scheduler = MagicMock()
    scheduler.needs_resolve.return_value = needs_resolve
    inventory = MagicMock()
    inventory.get_org_shape = AsyncMock(return_value=shape)
    exporter.collector_manager.scheduler = scheduler
    exporter.collector_manager.inventory = inventory
    return scheduler, inventory


class TestSchedulerResolveLoop:
    """ExporterApp._scheduler_resolve_loop()."""

    async def test_early_resolve_on_needs_resolve(self, test_settings: Settings) -> None:
        """When needs_resolve() is True the loop re-solves from a fresh shape."""
        exporter = ExporterApp(test_settings)
        shape = object()
        scheduler, inventory = _wire_scheduler(exporter, needs_resolve=True, shape=shape)

        def _resolve(_shape: object) -> None:
            # Stop the loop after the first (early) resolve.
            exporter._shutdown_event.set()

        scheduler.resolve.side_effect = _resolve

        with patch("asyncio.sleep", AsyncMock()):
            await asyncio.wait_for(exporter._scheduler_resolve_loop(), timeout=5.0)

        inventory.get_org_shape.assert_awaited_with("123456")
        scheduler.resolve.assert_called_once_with(shape)

    async def test_scheduled_resolve_on_interval(self, test_settings: Settings) -> None:
        """With AIMD quiet, the loop still re-solves on the scheduled cadence."""
        test_settings.scheduler.resolve_interval_seconds = 60
        exporter = ExporterApp(test_settings)
        shape = object()
        scheduler, inventory = _wire_scheduler(exporter, needs_resolve=False, shape=shape)

        def _resolve(_shape: object) -> None:
            exporter._shutdown_event.set()

        scheduler.resolve.side_effect = _resolve

        # First tick: 0s elapsed, needs_resolve False => no resolve. After the
        # (patched, instant) 60s wait, seconds_since_resolve reaches the 60s
        # interval and the second tick performs the scheduled resolve.
        with patch("asyncio.sleep", AsyncMock()):
            await asyncio.wait_for(exporter._scheduler_resolve_loop(), timeout=5.0)

        scheduler.resolve.assert_called_once_with(shape)
        inventory.get_org_shape.assert_awaited_once_with("123456")

    async def test_no_immediate_resolve_when_quiet(self, test_settings: Settings) -> None:
        """The first tick does not re-solve (collect_initial already did)."""
        exporter = ExporterApp(test_settings)
        scheduler, inventory = _wire_scheduler(exporter, needs_resolve=False, shape=object())

        ticks = 0
        real_sleep = asyncio.sleep

        async def counting_sleep(_seconds: float) -> None:
            nonlocal ticks
            ticks += 1
            # Let the first full 60s wait (60 one-second increments) elapse, then
            # stop before the second tick would trigger a scheduled resolve.
            if ticks >= 60:
                exporter._shutdown_event.set()
            await real_sleep(0)

        with patch("asyncio.sleep", counting_sleep):
            await asyncio.wait_for(exporter._scheduler_resolve_loop(), timeout=5.0)

        scheduler.resolve.assert_not_called()
        inventory.get_org_shape.assert_not_awaited()

    async def test_resolve_exception_is_swallowed(self, test_settings: Settings) -> None:
        """A get_org_shape/resolve failure is logged, not fatal to the loop."""
        exporter = ExporterApp(test_settings)
        scheduler, inventory = _wire_scheduler(exporter, needs_resolve=True, shape=object())
        inventory.get_org_shape = AsyncMock(side_effect=RuntimeError("boom"))

        calls = 0
        real_sleep = asyncio.sleep

        async def counting_sleep(_seconds: float) -> None:
            nonlocal calls
            calls += 1
            if calls >= 2:
                exporter._shutdown_event.set()
            await real_sleep(0)

        # Must not raise despite the fetch blowing up on the first tick.
        with patch("asyncio.sleep", counting_sleep):
            await asyncio.wait_for(exporter._scheduler_resolve_loop(), timeout=5.0)

        assert inventory.get_org_shape.await_count >= 1
        scheduler.resolve.assert_not_called()

    async def test_cancel_exits_cleanly(self, test_settings: Settings) -> None:
        """Cancellation propagates CancelledError out of the loop."""
        exporter = ExporterApp(test_settings)
        _wire_scheduler(exporter, needs_resolve=False, shape=object())

        task = asyncio.create_task(exporter._scheduler_resolve_loop())
        await asyncio.sleep(0.05)  # let it enter the interruptible wait
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_skips_when_org_id_unresolved(self, test_settings: Settings) -> None:
        """No org_id => loop returns immediately without touching the seams."""
        exporter = ExporterApp(test_settings)
        exporter.settings.meraki.org_id = None
        scheduler, inventory = _wire_scheduler(exporter, needs_resolve=True, shape=object())

        await asyncio.wait_for(exporter._scheduler_resolve_loop(), timeout=5.0)

        inventory.get_org_shape.assert_not_awaited()
        scheduler.resolve.assert_not_called()


class TestStartupWiresResolveLoop:
    """_startup_collections registers the resolve loop as a tracked task."""

    async def test_resolve_loop_task_is_created_and_tracked(self, test_settings: Settings) -> None:
        """After startup a running _scheduler_resolve_loop task is tracked."""
        exporter = ExporterApp(test_settings)
        exporter.collector_manager.collect_initial = AsyncMock()  # type: ignore[method-assign]
        exporter._collector_loop = AsyncMock()  # type: ignore[method-assign]
        exporter._wait_for_first_collection = AsyncMock()  # type: ignore[method-assign]

        started = asyncio.Event()

        async def gated_loop() -> None:
            started.set()
            await asyncio.Event().wait()  # block until cancelled

        exporter._scheduler_resolve_loop = gated_loop  # type: ignore[method-assign]

        from types import SimpleNamespace

        with patch(
            "meraki_dashboard_exporter.app.DiscoveryService",
            lambda api, settings: SimpleNamespace(
                run_discovery=AsyncMock(return_value={"orgs": 1})
            ),
        ):
            await exporter._startup_collections()

        await asyncio.wait_for(started.wait(), timeout=2.0)
        pending = [t for t in exporter._background_tasks if not t.done()]
        assert pending, "resolve loop task must be tracked in _background_tasks"

        # Cleanup: cancel and drain the tracked tasks.
        for task in list(exporter._background_tasks):
            task.cancel()
        await asyncio.gather(*exporter._background_tasks, return_exceptions=True)


class TestLivenessThresholdUnchangedByScheduler:
    """#596: scheduler mode must not perturb the liveness threshold (#617)."""

    def test_threshold_is_3x_fastest_group_in_adaptive_mode(self, test_settings: Settings) -> None:
        """Adaptive mode (default): threshold == 3 × fastest solved group interval."""
        exporter = ExporterApp(test_settings)
        assert exporter.settings.scheduler.mode == "adaptive"
        fastest = exporter.collector_manager.scheduler.fastest_effective_interval_seconds()
        assert exporter._liveness_threshold_seconds() == fastest * 3.0

    def test_threshold_invariant_across_scheduler_mode(self, test_settings: Settings) -> None:
        """Flipping adaptive<->fixed leaves the derived threshold unchanged."""
        exporter = ExporterApp(test_settings)
        baseline = exporter._liveness_threshold_seconds()

        exporter.settings.scheduler.mode = "fixed"
        assert exporter._liveness_threshold_seconds() == baseline

        exporter.settings.scheduler.mode = "adaptive"
        assert exporter._liveness_threshold_seconds() == baseline
