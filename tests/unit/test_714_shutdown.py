"""Regression coverage for #714 terminal shutdown ordering."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings


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
    resolver = SimpleNamespace(close=lambda: events.append("dns"))
    exporter.collector_manager = SimpleNamespace(
        collectors=[SimpleNamespace(dns_resolver=resolver)]
    )
    exporter.client = SimpleNamespace(close=AsyncMock(side_effect=lambda: events.append("sdk")))
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
async def test_lifespan_cleans_resources_when_startup_fails_before_yield(
    fast_test_settings: Settings,
) -> None:
    """A deterministic pre-yield failure still runs the complete cleanup path."""
    exporter = ExporterApp(fast_test_settings)
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
