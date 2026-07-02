"""Tests for offloading synchronous registry iteration to worker threads (F-026).

The ``/metrics`` handler, the root page's ``_get_metrics_stats`` call, and the
cardinality monitor loop all iterate the Prometheus registry synchronously.
That work must run via ``asyncio.to_thread`` so it does not block the event
loop. prometheus_client's registry is thread-safe.
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


def _tracking_to_thread(names: list[str]):
    """Return a to_thread replacement that records func names then delegates."""
    real = asyncio.to_thread

    async def tracking(func, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        names.append(getattr(func, "__name__", repr(func)))
        return await real(func, *args, **kwargs)

    return tracking


class TestMetricsEndpointOffload:
    """GET /metrics serializes the registry off the event loop."""

    def test_metrics_offloads_generate_latest(self, exporter: ExporterApp) -> None:
        """generate_latest runs through asyncio.to_thread and payload is intact."""
        app = exporter.create_app()
        client = TestClient(app, raise_server_exceptions=True)

        names: list[str] = []
        with patch("asyncio.to_thread", side_effect=_tracking_to_thread(names)):
            response = client.get("/metrics")

        assert response.status_code == 200
        assert "generate_latest" in names
        # Payload is still valid Prometheus text exposition.
        assert len(response.content) > 0
        assert b"# HELP" in response.content or b"# TYPE" in response.content


class TestRootEndpointOffload:
    """GET / computes metric stats off the event loop."""

    def test_root_offloads_get_metrics_stats(self, exporter: ExporterApp) -> None:
        """_get_metrics_stats runs through asyncio.to_thread."""
        app = exporter.create_app()
        client = TestClient(app, raise_server_exceptions=True)

        names: list[str] = []
        with patch("asyncio.to_thread", side_effect=_tracking_to_thread(names)):
            response = client.get("/")

        assert response.status_code == 200
        assert "_get_metrics_stats" in names


class TestCardinalityLoopOffload:
    """The cardinality monitor loop analyzes the registry off the event loop."""

    async def test_loop_offloads_analyze_cardinality(self, exporter: ExporterApp) -> None:
        """One loop iteration calls analyze_cardinality via asyncio.to_thread."""
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
            patch("asyncio.to_thread", side_effect=_tracking_to_thread(names)),
        ):
            await asyncio.wait_for(exporter._cardinality_monitor_loop(), timeout=5.0)

        assert analyzed.is_set()
        assert "fake_analyze" in names
