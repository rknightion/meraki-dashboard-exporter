"""Tests for CollectorManager failure accounting when a collector raises (#509).

Encodes the acceptance criteria for "collected nothing is a collection
failure": a coordinator that raises out of ``_collect_impl()`` (including the
new ``NothingCollectedError``) must NOT be recorded as a success by
``CollectorManager`` -- ``failure_streak``/``total_failures`` advance,
``total_successes``/``last_success_time`` do not, the tier is not marked
initially-complete, ``is_ready`` stays False, and the
``meraki_exporter_collector_success_timestamp_seconds`` series for that
collector must never appear in the registry.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.constants.metrics_constants import CollectorMetricName
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError


def _settings() -> Settings:
    """Build minimal real Settings with smoothing disabled (no offset sleeps)."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    settings.api.smoothing_enabled = False
    return settings


@pytest.fixture
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    """Isolate MetricCollector's class-level performance metrics to a fresh registry.

    Mirrors ``tests/helpers/base.py::BaseCollectorTest.isolated_registry`` so the
    stub collector's success-timestamp gauge is deterministically fresh and
    registered, making presence/absence assertions meaningful.
    """
    registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", registry)
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.collector.MetricCollector._metrics_initialized", False
    )
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.collector.MetricCollector._collector_duration", None
    )
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.collector.MetricCollector._collector_errors", None
    )
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.collector.MetricCollector._collector_last_success", None
    )
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.collector.MetricCollector._collector_api_calls", None
    )
    return registry


class _StubCollector(MetricCollector):
    """A real MetricCollector whose _collect_impl can be toggled fail/succeed."""

    update_tier = UpdateTier.FAST

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.should_fail = True
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def _initialize_metrics(self) -> None:
        pass

    async def _collect_impl(self) -> None:
        if self.should_fail:
            raise NothingCollectedError("Stub", attempted=1, failed=1)


def _bare_manager(settings: Settings) -> CollectorManager:
    """Build a CollectorManager with real metrics but no real collectors."""
    mock_client = MagicMock()
    mock_client.api = MagicMock()
    mock_client.get_successful_api_requests.return_value = 5
    with (
        patch.object(CollectorManager, "_initialize_collectors"),
        patch.object(CollectorManager, "_validate_collector_configuration"),
    ):
        return CollectorManager(client=mock_client, settings=settings)


def _register_stub(
    manager: CollectorManager, collector: _StubCollector, name: str = "StubCollector"
) -> None:
    manager.collectors[UpdateTier.FAST] = [collector]  # type: ignore[list-item]
    manager.collector_health[name] = {
        "last_success_time": None,
        "failure_streak": 0,
        "total_runs": 0,
        "total_successes": 0,
        "total_failures": 0,
    }
    manager._collector_locks[name] = asyncio.Lock()


class TestManagerFailureAccounting:
    """A collector that raises (including NothingCollectedError) never counts as success."""

    async def test_repeated_failures_never_recorded_as_success(
        self, isolated_registry: CollectorRegistry
    ) -> None:
        """Two failing cycles: failure bookkeeping advances, success never does."""
        settings = _settings()
        manager = _bare_manager(settings)

        collector = _StubCollector(api=MagicMock(), settings=settings, registry=isolated_registry)
        name = collector.__class__.__name__
        _register_stub(manager, collector, name)

        await manager.collect_tier(UpdateTier.FAST)
        await manager.collect_tier(UpdateTier.FAST)

        health = manager.collector_health[name]
        assert health["failure_streak"] == 2
        assert health["total_failures"] == 2
        assert health["total_successes"] == 0
        assert health["last_success_time"] is None
        assert manager._tier_initial_complete["fast"] is False
        assert manager.is_ready is False

        # The success-timestamp series must never have appeared in the registry.
        success_metric_name = CollectorMetricName.COLLECTOR_SUCCESS_TIMESTAMP_SECONDS.value
        samples = [
            sample
            for metric in isolated_registry.collect()
            for sample in metric.samples
            if sample.name == success_metric_name and sample.labels.get("collector") == name
        ]
        assert samples == []

        # Swap to a succeeding _collect_impl and run once more: recovers cleanly.
        collector.should_fail = False
        await manager.collect_tier(UpdateTier.FAST)

        assert health["failure_streak"] == 0
        assert health["total_successes"] == 1
        assert health["last_success_time"] is not None
        assert manager._tier_initial_complete["fast"] is True

        samples_after = [
            sample
            for metric in isolated_registry.collect()
            for sample in metric.samples
            if sample.name == success_metric_name and sample.labels.get("collector") == name
        ]
        assert len(samples_after) == 1
        assert samples_after[0].value > 0
