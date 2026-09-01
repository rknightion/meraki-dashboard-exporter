"""Regression coverage for #714 terminal shutdown ordering."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.error_handling import StartupConfigurationError


@pytest.mark.asyncio
async def test_shutdown_drains_dependencies_before_sdk_and_serving_pools() -> None:
    """Final OTLP work precedes SDK drain, and serving work is always last."""
    exporter: Any = object.__new__(ExporterApp)
    exporter._shutdown_lock = asyncio.Lock()
    exporter._shutdown_complete = False
    exporter._shutdown_event = asyncio.Event()
    exporter._background_tasks = set()
    exporter._expiration_started = True
    exporter.settings = SimpleNamespace(otel=SimpleNamespace(enabled=True))
    events: list[str] = []
    exporter.expiration_manager = SimpleNamespace(
        stop=AsyncMock(side_effect=lambda: events.append("expiration"))
    )
    exporter.otel_metrics_bridge = SimpleNamespace(
        stop=AsyncMock(side_effect=lambda: events.append("metrics"))
    )
    exporter.tracing = SimpleNamespace(shutdown=lambda: events.append("tracing"))
    exporter.otel_logging = SimpleNamespace(shutdown=lambda: events.append("logging"))
    exporter.data_log_emitter = SimpleNamespace(shutdown=lambda: events.append("data-log"))
    resolver = SimpleNamespace(
        close=AsyncMock(side_effect=lambda **_: events.append("dns") or True)
    )
    exporter.collector_manager = SimpleNamespace(
        collectors=[SimpleNamespace(dns_resolver=resolver)]
    )
    exporter.client = SimpleNamespace(
        close=AsyncMock(side_effect=lambda **_: events.append("sdk") or True)
    )
    exporter._serving_executor = MagicMock()
    exporter._serving_executor.shutdown.side_effect = lambda **_: events.append("serving")

    await exporter._shutdown()
    await exporter._shutdown()

    assert events == [
        "expiration",
        "metrics",
        "tracing",
        "logging",
        "data-log",
        "dns",
        "sdk",
        "serving",
    ]
    exporter._serving_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_executor_drains_share_one_bound_and_keep_loop_responsive() -> None:
    """Blocked executor cleanup cannot multiply the app-level shutdown deadline."""
    exporter: Any = object.__new__(ExporterApp)
    exporter._shutdown_lock = asyncio.Lock()
    exporter._shutdown_complete = False
    exporter._shutdown_event = asyncio.Event()
    exporter._background_tasks = set()
    exporter._expiration_started = False
    exporter.settings = SimpleNamespace(otel=SimpleNamespace(enabled=False))
    exporter.otel_metrics_bridge = SimpleNamespace(stop=AsyncMock())
    exporter.tracing = SimpleNamespace(shutdown=MagicMock())
    exporter.data_log_emitter = SimpleNamespace(shutdown=MagicMock())
    resolver_close = AsyncMock()
    client_close = AsyncMock(return_value=False)

    async def consume_remaining_budget(*, timeout_seconds: float) -> bool:
        await asyncio.sleep(timeout_seconds)
        return False

    resolver_close.side_effect = consume_remaining_budget
    exporter.collector_manager = SimpleNamespace(
        collectors=[SimpleNamespace(dns_resolver=SimpleNamespace(close=resolver_close))]
    )
    exporter.client = SimpleNamespace(close=client_close)
    exporter._serving_executor = ThreadPoolExecutor(max_workers=1)
    release = threading.Event()
    started = threading.Event()

    def blocked_serving_work() -> None:
        started.set()
        release.wait()

    worker = exporter._serving_executor.submit(blocked_serving_work)
    assert started.wait(timeout=1.0)
    heartbeat_ticks = 0

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        while True:
            heartbeat_ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    try:
        with patch("meraki_dashboard_exporter.app.EXECUTOR_SHUTDOWN_TIMEOUT_SECONDS", 0.05):
            await exporter._shutdown()
            await exporter._shutdown()
        assert loop.time() - started_at < 0.15
        assert heartbeat_ticks >= 3
        resolver_close.assert_awaited_once()
        client_close.assert_awaited_once()
        assert client_close.call_args.kwargs["timeout_seconds"] < 0.01
    finally:
        heartbeat_task.cancel()
        release.set()
        await asyncio.to_thread(worker.result, 1.0)


@pytest.mark.asyncio
async def test_lifespan_cleans_resources_when_startup_fails_before_yield() -> None:
    """A deterministic pre-yield failure still runs the complete cleanup path."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    exporter = ExporterApp(settings)
    app = FastAPI()

    with (
        patch(
            "meraki_dashboard_exporter.app.resolve_org_id",
            AsyncMock(side_effect=RuntimeError("startup failed")),
        ),
        pytest.raises(RuntimeError, match="startup failed"),
    ):
        async with exporter.lifespan(app):
            pytest.fail("lifespan yielded after startup failure")

    assert exporter._shutdown_complete is True
    assert exporter.client.executor._shutdown is True
    assert exporter._serving_executor._shutdown is True


@pytest.mark.asyncio
async def test_lifespan_cleans_resources_for_startup_configuration_error() -> None:
    """Verified configuration errors abort pre-yield through the normal cleanup path."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    exporter = ExporterApp(settings)
    app = FastAPI()

    with (
        patch("meraki_dashboard_exporter.app.resolve_org_id", AsyncMock()),
        patch.object(
            exporter.collector_manager,
            "validate_startup_configuration",
            AsyncMock(side_effect=StartupConfigurationError("fix setting")),
        ),
        pytest.raises(StartupConfigurationError, match="fix setting"),
    ):
        async with exporter.lifespan(app):
            pytest.fail("lifespan yielded after configuration failure")

    assert exporter._shutdown_complete is True


@pytest.mark.asyncio
async def test_background_startup_configuration_error_becomes_unhealthy() -> None:
    """The real lifespan callback retains a post-yield startup configuration failure."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    exporter = ExporterApp(settings)
    app = exporter.create_app()

    with (
        patch("meraki_dashboard_exporter.app.resolve_org_id", AsyncMock()),
        patch.object(
            exporter.collector_manager,
            "validate_startup_configuration",
            AsyncMock(),
        ),
        patch.object(exporter.collector_manager, "validate_profile_selection", AsyncMock()),
        patch(
            "meraki_dashboard_exporter.app.DiscoveryService.run_discovery",
            AsyncMock(return_value={}),
        ),
        patch.object(
            exporter.collector_manager,
            "collect_initial",
            AsyncMock(side_effect=StartupConfigurationError("late configuration failure")),
        ),
    ):
        async with exporter.lifespan(app):
            for _ in range(5):
                await asyncio.sleep(0)
                if exporter._startup_configuration_error is not None:
                    break

            assert str(exporter._startup_configuration_error) == "late configuration failure"
            assert exporter._liveness_check() == (True, "startup configuration failed")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/health")
            assert response.status_code == 503
