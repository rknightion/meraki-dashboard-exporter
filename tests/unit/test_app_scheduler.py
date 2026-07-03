"""Tests for the production collection scheduler in app.py (F-162, F-044).

Covers the per-collector, group-clocked scheduler surface (#631):

* ``_collector_loop`` happy path and its behavior when ``run_collector_once``
  raises (logged and swallowed, no failure-count kill switch — see #528).
* ``_startup_collections`` sequencing and background-task bookkeeping (one
  ``_collector_loop`` task per collector, tracked in ``_collector_tasks``).
* ``_wait_for_first_collection`` gating.
* F-044: the ``_wait_for_first_collection`` task is tracked in
  ``_background_tasks`` and therefore cancelled on lifespan shutdown.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings


@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings for scheduler testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


def _fake_collector(name: str = "FakeCollector", phase_offset: float = 0.0) -> Any:
    """Build a minimal collector stub for the per-collector loop."""
    cls = type(
        name,
        (),
        {
            "get_endpoint_groups": lambda self: (),
            "phase_offset_seconds": lambda self: phase_offset,
        },
    )
    return cls()


# ---------------------------------------------------------------------------
# _collector_loop
# ---------------------------------------------------------------------------


class TestCollectorLoop:
    """Tests for ExporterApp._collector_loop()."""

    async def test_loop_runs_then_exits_on_shutdown(self, test_settings: Settings) -> None:
        """The loop runs the collector and exits cleanly when shutdown is set."""
        exporter = ExporterApp(test_settings)
        exporter._interruptible_sleep = AsyncMock()  # type: ignore[method-assign]
        collector = _fake_collector()

        calls = 0

        async def run_once(coll: Any, *, force: bool = False) -> None:
            nonlocal calls
            calls += 1
            # Stop after the second successful cycle.
            if calls >= 2:
                exporter._shutdown_event.set()

        exporter.collector_manager.run_collector_once = run_once  # type: ignore[method-assign]

        await asyncio.wait_for(
            exporter._collector_loop(collector, initial_run_completed=False),
            timeout=5.0,
        )
        assert calls >= 1

    async def test_run_failure_is_logged_and_loop_continues(self, test_settings: Settings) -> None:
        """A run_collector_once exception is swallowed (logged); the loop keeps running (#528).

        run_collector_once already swallows per-org/per-collector failures at its own
        boundary (#509), so an exception reaching this loop is unexpected and never
        accumulates a streak. Honest health signals live in /ready + failure_streak.
        """
        exporter = ExporterApp(test_settings)
        exporter._interruptible_sleep = AsyncMock()  # type: ignore[method-assign]
        collector = _fake_collector()

        calls = 0

        async def run_once(coll: Any, *, force: bool = False) -> None:
            nonlocal calls
            calls += 1
            if calls >= 3:
                exporter._shutdown_event.set()
            raise RuntimeError("boom")

        exporter.collector_manager.run_collector_once = run_once  # type: ignore[method-assign]

        # Should NOT raise even though every run fails - there is no failure-count
        # threshold left to trip.
        await asyncio.wait_for(
            exporter._collector_loop(collector, initial_run_completed=False),
            timeout=5.0,
        )
        assert calls >= 3
        assert exporter._shutdown_event.is_set()

    async def test_shutdown_before_first_run_skips_collection(
        self, test_settings: Settings
    ) -> None:
        """A shutdown set before entry (with a phase offset) exits before any run."""
        exporter = ExporterApp(test_settings)
        collector = _fake_collector(phase_offset=100.0)
        run_mock = AsyncMock()
        exporter.collector_manager.run_collector_once = run_mock  # type: ignore[method-assign]
        exporter._shutdown_event.set()

        await asyncio.wait_for(
            exporter._collector_loop(collector, initial_run_completed=True),
            timeout=5.0,
        )
        run_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# _wait_for_first_collection
# ---------------------------------------------------------------------------


class TestWaitForFirstCollection:
    """Tests for ExporterApp._wait_for_first_collection()."""

    async def test_returns_immediately_when_already_complete(self, test_settings: Settings) -> None:
        """If the first collection already finished it does not sleep."""
        exporter = ExporterApp(test_settings)
        exporter._first_collection_complete = True

        with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
            await exporter._wait_for_first_collection()

        sleep_mock.assert_not_awaited()

    async def test_waits_then_marks_complete(self, test_settings: Settings) -> None:
        """Otherwise it waits the fixed 1800s fallback then marks complete (#631)."""
        exporter = ExporterApp(test_settings)
        exporter._first_collection_complete = False
        exporter.cardinality_monitor.mark_first_run_complete = MagicMock()  # type: ignore[method-assign]

        with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
            await exporter._wait_for_first_collection()

        sleep_mock.assert_awaited_once_with(1800.0)
        assert exporter._first_collection_complete is True
        exporter.cardinality_monitor.mark_first_run_complete.assert_called_once()


# ---------------------------------------------------------------------------
# _startup_collections + F-044 task tracking
# ---------------------------------------------------------------------------


def _stub_startup(exporter: ExporterApp) -> None:
    """Stub the heavy pieces so _startup_collections runs fast."""
    exporter.collector_manager.collect_initial = AsyncMock()  # type: ignore[method-assign]
    exporter._collector_loop = AsyncMock()  # type: ignore[method-assign]
    # #617: the adaptive scheduler resolve loop is a long-running background
    # task; stub it here so startup-sequencing tests don't spin the real loop
    # (which would poll inventory/API forever and never drain).
    exporter._scheduler_resolve_loop = AsyncMock()  # type: ignore[method-assign]


class TestStartupCollections:
    """Tests for ExporterApp._startup_collections()."""

    async def test_runs_discovery_then_initial_collection(self, test_settings: Settings) -> None:
        """Discovery runs, then the initial sequential collection completes."""
        exporter = ExporterApp(test_settings)
        _stub_startup(exporter)
        exporter._wait_for_first_collection = AsyncMock()  # type: ignore[method-assign]

        with patch(
            "meraki_dashboard_exporter.app.DiscoveryService",
            lambda api, settings: SimpleNamespace(
                run_discovery=AsyncMock(return_value={"orgs": 1})
            ),
        ):
            await exporter._startup_collections()

        exporter.collector_manager.collect_initial.assert_awaited_once()
        assert exporter._first_collection_complete is True
        # One group-clocked loop task per instantiated collector.
        assert exporter._collector_tasks
        assert len(exporter._collector_tasks) == len(exporter.collector_manager.collectors)

    async def test_wait_task_is_tracked_in_background_tasks(self, test_settings: Settings) -> None:
        """F-044: the _wait_for_first_collection task is tracked, not discarded."""
        exporter = ExporterApp(test_settings)
        _stub_startup(exporter)

        started = asyncio.Event()
        release = asyncio.Event()

        async def gated_wait() -> None:
            started.set()
            await release.wait()

        exporter._wait_for_first_collection = gated_wait  # type: ignore[method-assign]

        with patch(
            "meraki_dashboard_exporter.app.DiscoveryService",
            lambda api, settings: SimpleNamespace(
                run_discovery=AsyncMock(return_value={"orgs": 1})
            ),
        ):
            await exporter._startup_collections()

        # The gated wait task has started and is still pending, tracked in the
        # background-task set so shutdown can cancel it.
        await asyncio.wait_for(started.wait(), timeout=2.0)
        pending = [t for t in exporter._background_tasks if not t.done()]
        assert pending, "wait task must be tracked in _background_tasks"

        # Cleanup: release and drain.
        release.set()
        await asyncio.wait_for(
            asyncio.gather(*exporter._background_tasks, return_exceptions=True),
            timeout=2.0,
        )


class TestLifespanCancelsWaitTask:
    """F-044: lifespan shutdown cancels the tracked wait task."""

    async def test_shutdown_cancels_wait_task(self, test_settings: Settings) -> None:
        """The gated wait task receives CancelledError on lifespan exit."""
        exporter = ExporterApp(test_settings)
        _stub_startup(exporter)
        exporter._cardinality_monitor_loop = AsyncMock()  # type: ignore[method-assign]
        exporter.expiration_manager.start = AsyncMock()  # type: ignore[method-assign]
        exporter.expiration_manager.stop = AsyncMock()  # type: ignore[method-assign]
        exporter.client.close = AsyncMock()  # type: ignore[method-assign]

        started = asyncio.Event()
        release = asyncio.Event()
        captured: dict[str, bool] = {}

        async def gated_wait() -> None:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                captured["cancelled"] = True
                raise

        exporter._wait_for_first_collection = gated_wait  # type: ignore[method-assign]

        fastapi_app = exporter.create_app()

        with patch(
            "meraki_dashboard_exporter.app.DiscoveryService",
            lambda api, settings: SimpleNamespace(
                run_discovery=AsyncMock(return_value={"orgs": 1})
            ),
        ):
            stack = AsyncExitStack()
            cm = exporter.lifespan(fastapi_app)
            await asyncio.wait_for(stack.enter_async_context(cm), timeout=2.0)
            # Let the startup background task reach and start the gated wait task.
            await asyncio.wait_for(started.wait(), timeout=2.0)
            # Exiting the lifespan runs the shutdown sweep, which cancels every
            # tracked background task - including the wait task (F-044).
            await asyncio.wait_for(stack.aclose(), timeout=5.0)

        assert captured.get("cancelled") is True
