"""Tests for exporter process self-resource gauges (#277).

Covers ``ExporterApp._sample_resource_metrics`` (one-shot psutil sample -> gauge
update) and ``ExporterApp._resource_metrics_loop`` (the lightweight periodic
background task started from ``lifespan``, including the cpu_percent() priming
call and clean cancellation on shutdown).
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
from meraki_dashboard_exporter.core.constants.metrics_constants import CollectorMetricName


@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings for resource-metrics testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


class TestGaugesRegistered:
    """The two frozen enum gauges exist and start unset (0.0)."""

    def test_gauges_registered_with_frozen_names(self, test_settings: Settings) -> None:
        """Gauge names match the orchestrator-frozen ``CollectorMetricName`` values."""
        exporter = ExporterApp(test_settings)

        assert (
            exporter._resource_memory_gauge._name
            == CollectorMetricName.EXPORTER_MEMORY_USAGE_BYTES.value
        )
        assert (
            exporter._resource_cpu_gauge._name
            == CollectorMetricName.EXPORTER_CPU_USAGE_PERCENT.value
        )


class TestSampleResourceMetrics:
    """Tests for ExporterApp._sample_resource_metrics()."""

    def test_sample_sets_both_gauges(self, test_settings: Settings) -> None:
        """A single sample populates both gauges from the (mocked) psutil process."""
        exporter = ExporterApp(test_settings)
        exporter._resource_process = MagicMock(
            memory_info=MagicMock(return_value=SimpleNamespace(rss=123_456_789)),
            cpu_percent=MagicMock(return_value=12.5),
        )

        exporter._sample_resource_metrics()

        assert exporter._resource_memory_gauge._value.get() == 123_456_789
        assert exporter._resource_cpu_gauge._value.get() == 12.5

    def test_sample_swallows_psutil_errors(self, test_settings: Settings) -> None:
        """A psutil failure (e.g. process gone) is logged and swallowed, not raised."""
        exporter = ExporterApp(test_settings)
        exporter._resource_process = MagicMock(
            memory_info=MagicMock(side_effect=RuntimeError("boom")),
        )

        # Must not raise.
        exporter._sample_resource_metrics()

        # Gauges stay at their default (unset) value of 0.0.
        assert exporter._resource_memory_gauge._value.get() == 0.0
        assert exporter._resource_cpu_gauge._value.get() == 0.0


class TestResourceMetricsLoop:
    """Tests for ExporterApp._resource_metrics_loop()."""

    async def test_loop_primes_cpu_percent_before_first_sample(
        self, test_settings: Settings
    ) -> None:
        """cpu_percent() is called once to prime (discarded), then sampled per cycle.

        Interval is 0 so the loop never awaits between iterations (matching
        ``_tiered_collection_loop``'s own zero-interval test convention) - the
        shutdown signal is therefore raised synchronously from within the
        second (real, post-priming) ``cpu_percent()`` call itself, rather than
        via a concurrent task that would never get scheduled.
        """
        exporter = ExporterApp(test_settings)
        exporter._resource_metrics_interval_seconds = 0

        calls: list[str] = []
        cpu_call_count = 0

        def fake_cpu_percent() -> float:
            nonlocal cpu_call_count
            cpu_call_count += 1
            calls.append("cpu_percent")
            if cpu_call_count == 1:
                return 0.0  # the priming call
            exporter._shutdown_event.set()
            return 5.0

        process = MagicMock()
        process.cpu_percent = MagicMock(side_effect=fake_cpu_percent)
        process.memory_info = MagicMock(
            side_effect=lambda: calls.append("memory_info") or SimpleNamespace(rss=42)
        )
        exporter._resource_process = process

        await asyncio.wait_for(exporter._resource_metrics_loop(), timeout=5.0)

        # First call is the priming cpu_percent() call, before any memory_info().
        assert calls[0] == "cpu_percent"
        assert "memory_info" in calls
        assert exporter._resource_memory_gauge._value.get() == 42
        assert exporter._resource_cpu_gauge._value.get() == 5.0

    async def test_loop_exits_promptly_on_shutdown(self, test_settings: Settings) -> None:
        """With shutdown already set, the loop exits without sampling."""
        exporter = ExporterApp(test_settings)
        exporter._resource_metrics_interval_seconds = 60
        exporter._resource_process = MagicMock()
        exporter._shutdown_event.set()

        await asyncio.wait_for(exporter._resource_metrics_loop(), timeout=5.0)

        # Priming still happens (cheap, harmless), but no sample loop iteration runs.
        exporter._resource_process.cpu_percent.assert_called_once()
        exporter._resource_process.memory_info.assert_not_called()


class TestResourceMetricsLifespanWiring:
    """The resource-metrics task is tracked and cancelled like the other loops."""

    async def test_shutdown_cancels_resource_metrics_task(self, test_settings: Settings) -> None:
        """Exiting the lifespan cancels the tracked resource-metrics task cleanly."""
        exporter = ExporterApp(test_settings)
        # Stub out the collection-startup fan-out (#631: per-collector loops +
        # scheduler resolve loop) so this test exercises only the resource-metrics
        # task lifecycle without spinning up real collector loops.
        exporter._startup_collections = AsyncMock()  # type: ignore[method-assign]
        exporter._cardinality_monitor_loop = AsyncMock()  # type: ignore[method-assign]
        exporter.expiration_manager.start = AsyncMock()  # type: ignore[method-assign]
        exporter.expiration_manager.stop = AsyncMock()  # type: ignore[method-assign]
        exporter.client.close = AsyncMock()  # type: ignore[method-assign]

        started = asyncio.Event()
        release = asyncio.Event()
        captured: dict[str, bool] = {}

        async def gated_resource_loop() -> None:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                captured["cancelled"] = True
                raise

        exporter._resource_metrics_loop = gated_resource_loop  # type: ignore[method-assign]

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
            await asyncio.wait_for(started.wait(), timeout=2.0)
            await asyncio.wait_for(stack.aclose(), timeout=5.0)

        assert captured.get("cancelled") is True
