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
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
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


class TestCardinalityLoopOffload:
    """The cardinality monitor loop analyzes the registry off the event loop."""

    async def test_loop_offloads_analyze_cardinality(self, exporter: ExporterApp) -> None:
        """One loop iteration calls analyze_cardinality via the serving executor."""
        # Keep the loop's initial delay tiny and let it run exactly one analysis
        # before shutdown.
        exporter.collector_manager.get_tier_interval = lambda tier: 0  # type: ignore[assignment]

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

    def test_serving_executor_distinct_from_sdk_executor(self, exporter: ExporterApp) -> None:
        """Registry serving work and SDK calls run on different pools."""
        assert exporter._serving_executor is not exporter.client.executor
        assert exporter._serving_executor._thread_name_prefix == "registry-serve"
        assert exporter.client.executor._thread_name_prefix == "meraki-sdk"
