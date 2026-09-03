"""Tests for offloading synchronous registry iteration to worker threads (F-026/#544).

The ``/metrics`` handler, the root page's ``_get_metrics_stats`` call, and the
cardinality monitor loop all iterate the Prometheus registry synchronously.
That work must run off the event loop, on the app's dedicated serving pool
(``ExporterApp._serving_executor``) - NOT the default executor, which #544
repurposes as the bounded Meraki SDK pool - so scrapes never queue behind
blocked SDK threads during a 429 storm. prometheus_client's registry is
thread-safe.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp, RegistryWorkSaturatedError
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings


@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings for offload testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


@pytest.fixture
def exporter(test_settings: Settings) -> ExporterApp:
    """An ExporterApp instance."""
    return ExporterApp(test_settings)


def _track_serving_submits(exporter: ExporterApp, names: list[str]):
    """Patch the serving executor's submit to record func names then delegate.

    ``loop.run_in_executor(executor, func, *args)`` calls ``executor.submit``
    under the hood, so wrapping submit observes exactly the work routed onto
    the dedicated serving pool.
    """
    real_submit = exporter._serving_executor.submit

    def tracking_submit(func, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        names.append(getattr(func, "__name__", repr(func)))
        return real_submit(func, *args, **kwargs)

    return patch.object(exporter._serving_executor, "submit", side_effect=tracking_submit)


class TestMetricsEndpointOffload:
    """GET /metrics serializes the registry off the event loop, on the serving pool."""

    def test_metrics_offloads_generate_latest(self, exporter: ExporterApp) -> None:
        """generate_latest runs on the serving executor and payload is intact."""
        app = exporter.create_app()
        client = TestClient(app, raise_server_exceptions=True)

        names: list[str] = []
        with _track_serving_submits(exporter, names):
            response = client.get("/metrics")

        assert response.status_code == 200
        assert "generate_latest" in names
        # Payload is still valid Prometheus text exposition.
        assert len(response.content) > 0
        assert b"# HELP" in response.content or b"# TYPE" in response.content

    async def test_metrics_rejects_excess_scrape_without_queueing(
        self, exporter: ExporterApp
    ) -> None:
        """A third scrape fails fast while both registry workers are occupied."""
        app = exporter.create_app()
        loop = asyncio.get_running_loop()
        both_started = asyncio.Event()
        release_workers = threading.Event()
        call_lock = threading.Lock()
        call_count = 0

        def blocking_generate_latest(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            with call_lock:
                call_count += 1
                if call_count == 2:
                    loop.call_soon_threadsafe(both_started.set)
            release_workers.wait(timeout=5.0)
            return b"# HELP bounded_registry_work test\n"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "meraki_dashboard_exporter.app.generate_latest",
                side_effect=blocking_generate_latest,
            ):
                first = asyncio.create_task(client.get("/metrics"))
                second = asyncio.create_task(client.get("/metrics"))
                third: asyncio.Task[Any] | None = None
                try:
                    await asyncio.wait_for(both_started.wait(), timeout=1.0)
                    third = asyncio.create_task(client.get("/metrics"))
                    done, _pending = await asyncio.wait({third}, timeout=0.2)

                    assert third in done, "saturated scrape was queued instead of rejected"
                    response = third.result()
                    assert response.status_code == 503
                    assert response.headers["retry-after"] == "1"
                    assert call_count == 2
                finally:
                    release_workers.set()
                    if third is not None and not third.done():
                        third.cancel()
                    await asyncio.gather(
                        first,
                        second,
                        *((third,) if third else ()),
                        return_exceptions=True,
                    )

        assert first.result().status_code == 200
        assert second.result().status_code == 200


class TestRootEndpointOffload:
    """GET / computes metric stats off the event loop, on the serving pool."""

    def test_root_offloads_get_metrics_stats(self, exporter: ExporterApp) -> None:
        """_get_metrics_stats runs on the serving executor."""
        app = exporter.create_app()
        client = TestClient(app, raise_server_exceptions=True)

        names: list[str] = []
        with _track_serving_submits(exporter, names):
            response = client.get("/")

        assert response.status_code == 200
        assert "_get_metrics_stats" in names


class TestStatusEndpointOffload:
    """GET /status bounds its Prometheus registry read like other HTTP walks."""

    def test_status_offloads_network_filter_registry_read(self, exporter: ExporterApp) -> None:
        """The status registry walk runs on the dedicated serving executor."""
        app = exporter.create_app()
        client = TestClient(app, raise_server_exceptions=True)

        names: list[str] = []
        with _track_serving_submits(exporter, names):
            response = client.get("/status?format=json")

        assert response.status_code == 200
        assert "get_network_filter_status" in names

    async def test_status_rejects_saturated_registry_work(self, exporter: ExporterApp) -> None:
        """A status request fails fast with the established overload contract."""
        exporter._registry_work_slots = asyncio.BoundedSemaphore(1)
        await exporter._registry_work_slots.acquire()
        try:
            transport = ASGITransport(app=exporter.create_app())
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/status?format=json")
        finally:
            exporter._registry_work_slots.release()

        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"

    async def test_cancelled_status_keeps_slot_until_registry_walk_finishes(
        self, exporter: ExporterApp
    ) -> None:
        """Cancelling /status cannot admit another walk over its running thread."""
        exporter._registry_work_slots = asyncio.BoundedSemaphore(1)
        app = exporter.create_app()
        loop = asyncio.get_running_loop()
        worker_started = asyncio.Event()
        worker_finished = threading.Event()
        release_worker = threading.Event()
        original = exporter.status_service.get_network_filter_status

        def blocking_network_filter_status():  # type: ignore[no-untyped-def]
            loop.call_soon_threadsafe(worker_started.set)
            release_worker.wait(timeout=5.0)
            result = original()
            worker_finished.set()
            return result

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch.object(
                exporter.status_service,
                "get_network_filter_status",
                side_effect=blocking_network_filter_status,
            ):
                request = asyncio.create_task(client.get("/status?format=json"))
                await asyncio.wait_for(worker_started.wait(), timeout=1.0)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request

                saturated = await client.get("/status?format=json")
                assert saturated.status_code == 503
                assert saturated.headers["retry-after"] == "1"

                release_worker.set()
                assert await asyncio.to_thread(worker_finished.wait, 1.0)


class TestCardinalityLoopOffload:
    """The cardinality monitor loop analyzes the registry off the event loop."""

    async def test_loop_offloads_analyze_cardinality(self, exporter: ExporterApp) -> None:
        """One loop iteration calls analyze_cardinality via the serving executor."""
        # The loop's fixed initial delay is bypassed by patching asyncio.sleep
        # below, so one analysis runs before the fake_analyze trips shutdown.
        analyzed = asyncio.Event()

        def fake_analyze(*args, **kwargs):  # type: ignore[no-untyped-def]
            analyzed.set()
            exporter._shutdown_event.set()
            return {"metrics": {}}

        exporter.cardinality_monitor.analyze_cardinality = fake_analyze  # type: ignore[method-assign]

        names: list[str] = []
        with (
            patch("asyncio.sleep", AsyncMock()),
            _track_serving_submits(exporter, names),
        ):
            await asyncio.wait_for(exporter._cardinality_monitor_loop(), timeout=5.0)

        assert analyzed.is_set()
        assert "fake_analyze" in names


class TestServingPoolIsolation:
    """#544: the serving pool exists, is small, and is not the SDK pool."""

    async def test_cancelled_waiter_keeps_registry_slot_until_worker_finishes(
        self, exporter: ExporterApp
    ) -> None:
        """Request cancellation cannot admit work over a still-running thread."""
        exporter._registry_work_slots = asyncio.BoundedSemaphore(1)
        loop = asyncio.get_running_loop()
        worker_started = asyncio.Event()
        worker_finished = threading.Event()
        release_worker = threading.Event()

        def blocking_registry_work() -> None:
            loop.call_soon_threadsafe(worker_started.set)
            release_worker.wait(timeout=5.0)
            worker_finished.set()

        request = asyncio.create_task(
            exporter._run_registry_work(blocking_registry_work, wait_for_slot=False)
        )
        await asyncio.wait_for(worker_started.wait(), timeout=1.0)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request

        try:
            with pytest.raises(RegistryWorkSaturatedError):
                await exporter._run_registry_work(lambda: None, wait_for_slot=False)
        finally:
            release_worker.set()
            assert await asyncio.to_thread(worker_finished.wait, 1.0)

    async def test_orphaned_registry_walk_failure_is_surfaced_not_swallowed(
        self, exporter: ExporterApp
    ) -> None:
        """A walk that fails after its caller went away must still be reported.

        Shielding the executor future means a cancelled caller stops awaiting
        it, so nothing raises the failure into a request. asyncio hands the
        orphaned exception to the loop's exception handler instead, and that is
        the behaviour to keep: an exporter whose registry walk started failing
        must not go quiet just because the scraper disconnected first.
        """
        exporter._registry_work_slots = asyncio.BoundedSemaphore(1)
        loop = asyncio.get_running_loop()
        worker_started = asyncio.Event()
        release_worker = threading.Event()
        reported: list[dict[str, Any]] = []
        walk_failure = RuntimeError("registry walk failed after the caller went away")

        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: reported.append(context))
        try:

            def failing_registry_work() -> None:
                loop.call_soon_threadsafe(worker_started.set)
                release_worker.wait(timeout=5.0)
                raise walk_failure

            request = asyncio.create_task(
                exporter._run_registry_work(failing_registry_work, wait_for_slot=False)
            )
            await asyncio.wait_for(worker_started.wait(), timeout=1.0)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request

            release_worker.set()
            # The slot returning proves the walk finished and its future resolved.
            for _ in range(500):
                if not exporter._registry_work_slots.locked():
                    break
                await asyncio.sleep(0.01)
            assert not exporter._registry_work_slots.locked(), (
                "a failing orphaned walk leaked its registry slot"
            )
            await asyncio.sleep(0)
        finally:
            release_worker.set()
            loop.set_exception_handler(previous_handler)

        assert [context["exception"] for context in reported] == [walk_failure], (
            f"the orphaned walk's failure was not surfaced exactly once: {reported}"
        )

    def test_serving_executor_distinct_from_sdk_executor(self, exporter: ExporterApp) -> None:
        """Registry, client-page, and SDK work run on distinct bounded pools."""
        assert exporter._serving_executor is not exporter.client.executor
        assert exporter._client_page_executor is not exporter.client.executor
        assert exporter._client_page_executor is not exporter._serving_executor
        assert exporter._serving_executor._thread_name_prefix == "registry-serve"
        assert exporter._client_page_executor._thread_name_prefix == "client-page"
        assert exporter.client.executor._thread_name_prefix == "meraki-sdk"
