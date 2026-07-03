"""Tests for the production collection scheduler in app.py (F-162, F-044).

Covers the previously-untested scheduler surface:

* ``_startup_collections`` sequencing and background-task bookkeeping.
* ``_tiered_collection_loop`` happy path and its behavior when
  ``collect_tier`` raises (logged and swallowed, no failure-count kill
  switch - see #528).
* ``_wait_for_first_collection`` gating.
* F-044: the ``_wait_for_first_collection`` task is tracked in
  ``_background_tasks`` and therefore cancelled on lifespan shutdown.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.constants import UpdateTier


@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings for scheduler testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


# ---------------------------------------------------------------------------
# _tiered_collection_loop
# ---------------------------------------------------------------------------


class TestTieredCollectionLoop:
    """Tests for ExporterApp._tiered_collection_loop()."""

    async def test_loop_collects_then_exits_on_shutdown(self, test_settings: Settings) -> None:
        """The loop calls collect_tier and exits cleanly when shutdown is set."""
        exporter = ExporterApp(test_settings)
        exporter.collector_manager.get_tier_interval = lambda tier: 0  # type: ignore[assignment]

        calls = 0

        async def collect(tier: UpdateTier) -> None:
            nonlocal calls
            calls += 1
            # Stop after the second successful cycle.
            if calls >= 2:
                exporter._shutdown_event.set()

        exporter.collector_manager.collect_tier = collect  # type: ignore[method-assign]

        await asyncio.wait_for(
            exporter._tiered_collection_loop(UpdateTier.FAST, initial_delay=0.0),
            timeout=5.0,
        )
        assert calls >= 1

    async def test_collect_tier_failure_is_logged_and_loop_continues(
        self, test_settings: Settings
    ) -> None:
        """A collect_tier exception is swallowed (logged) and the loop keeps running (#528).

        The dead 10-consecutive-failure kill switch was removed: collect_tier already
        swallows per-org/per-collector failures at its own boundary (#509), so an
        exception reaching this loop is unexpected and never actually accumulated a
        streak. Honest health signals live in /ready + failure_streak instead.
        """
        exporter = ExporterApp(test_settings)
        exporter.collector_manager.get_tier_interval = lambda tier: 0  # type: ignore[assignment]

        calls = 0

        async def collect(tier: UpdateTier) -> None:
            nonlocal calls
            calls += 1
            if calls >= 3:
                exporter._shutdown_event.set()
            raise RuntimeError("boom")

        exporter.collector_manager.collect_tier = collect  # type: ignore[method-assign]

        # Should NOT raise even though every call fails - there is no failure-count
        # threshold left to trip.
        await asyncio.wait_for(
            exporter._tiered_collection_loop(UpdateTier.FAST, initial_delay=0.0),
            timeout=5.0,
        )
        assert calls >= 3
        assert exporter._shutdown_event.is_set()

    async def test_initial_delay_is_interruptible(self, test_settings: Settings) -> None:
        """A shutdown during the initial delay exits before any collection."""
        exporter = ExporterApp(test_settings)
        exporter.collector_manager.get_tier_interval = lambda tier: 60  # type: ignore[assignment]
        exporter.collector_manager.collect_tier = AsyncMock()  # type: ignore[method-assign]
        exporter._shutdown_event.set()

        await asyncio.wait_for(
            exporter._tiered_collection_loop(UpdateTier.SLOW, initial_delay=100.0),
            timeout=5.0,
        )
        exporter.collector_manager.collect_tier.assert_not_awaited()


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
        """Otherwise it waits one slow interval (+buffer) then marks complete."""
        exporter = ExporterApp(test_settings)
        exporter._first_collection_complete = False
        exporter.collector_manager.get_tier_interval = lambda tier: 900  # type: ignore[assignment]
        exporter.cardinality_monitor.mark_first_run_complete = MagicMock()  # type: ignore[method-assign]

        with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
            await exporter._wait_for_first_collection()

        sleep_mock.assert_awaited_once_with(905)  # 900 + 5s buffer
        assert exporter._first_collection_complete is True
        exporter.cardinality_monitor.mark_first_run_complete.assert_called_once()


# ---------------------------------------------------------------------------
# _startup_collections + F-044 task tracking
# ---------------------------------------------------------------------------


def _stub_startup(exporter: ExporterApp) -> None:
    """Stub the heavy pieces so _startup_collections runs fast."""
    exporter.collector_manager.collect_initial = AsyncMock()  # type: ignore[method-assign]
    exporter.collector_manager.get_tier_interval = lambda tier: 60  # type: ignore[assignment]
    exporter._tiered_collection_loop = AsyncMock()  # type: ignore[method-assign]
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
        # One tier task per UpdateTier member.
        assert len(exporter._tier_tasks) == len(list(UpdateTier))

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
