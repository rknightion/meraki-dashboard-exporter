"""Tests for CollectorManager readiness success-gating and liveness helpers.

Covers bug-bash findings, re-expressed against the de-tiered (#631) manager:
- F-105: readiness must reflect real collection success, not mere attempts — a
  collector owning an enabled priority-<=3 gated group is only "ready" once it
  has actually completed a successful run.
- F-043: manager exposes last-success / attempted signals for the liveness
  dead-man switch.

The per-tier smoothing/offset clamp tests (old F-018, #591) were deleted with the
tier model: `collect_tier`, `get_tier_interval`, `_get_smoothing_window`,
`_get_collector_offset`, `_run_collector_with_delay`, `_tier_initial_complete`,
and `collector_offsets` no longer exist. The equivalent per-collector phase
offset now lives on `MetricCollector.phase_offset_seconds()`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.scheduler import EndpointGroup, EndpointGroupName


def _settings(**overrides: object) -> Settings:
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    for key, value in overrides.items():
        setattr(settings.api, key, value)
    return settings


def _bare_manager(settings: Settings) -> CollectorManager:
    """Build a CollectorManager with real metrics but no real collectors."""
    mock_client = MagicMock()
    mock_client.api = MagicMock()
    with (
        patch.object(CollectorManager, "_initialize_collectors"),
        patch.object(CollectorManager, "_validate_collector_configuration"),
    ):
        return CollectorManager(client=mock_client, settings=settings)


def _group(name: EndpointGroupName, priority: int, floor: float) -> EndpointGroup:
    return EndpointGroup(
        name=name,
        priority=priority,
        floor_seconds=floor,
        cost_fn=lambda shape: 1.0,
    )


def _readiness_collector(name: str, *, succeeds: bool, group: EndpointGroup) -> Any:
    """Build a collector stub that owns ``group`` and succeeds/fails on collect."""

    async def collect(self: Any) -> None:
        if not succeeds:
            raise RuntimeError("boom")

    cls = type(
        name,
        (),
        {
            "is_active": True,
            "get_endpoint_groups": lambda self: (group,),
            "collect": collect,
            "collector_cadence_seconds": lambda self: 60.0,
            "phase_offset_seconds": lambda self: 0.0,
        },
    )
    return cls()


def _register(manager: CollectorManager, collector: Any, group: EndpointGroup) -> str:
    """Wire a fake collector into the manager + scheduler; return its name."""
    name = collector.__class__.__name__
    manager.scheduler.register_groups([group])
    manager.collectors = [collector]
    manager.collector_health[name] = {
        "last_success_time": None,
        "failure_streak": 0,
        "total_runs": 0,
        "total_successes": 0,
        "total_failures": 0,
    }
    manager._collector_locks[name] = asyncio.Lock()
    return name


# ---------------------------------------------------------------------------
# F-105 — readiness reflects real success, not just an attempted run
# ---------------------------------------------------------------------------


class TestReadinessSuccessGating:
    """run_collector_once only records first-success for a collector that succeeds."""

    async def test_failing_collector_not_ready(self) -> None:
        """A collector whose only run fails is not marked ready (F-105)."""
        manager = _bare_manager(_settings())
        group = _group(EndpointGroupName.MS_PORT_STATUS, priority=3, floor=300)
        collector = _readiness_collector("MSCollector", succeeds=False, group=group)
        name = _register(manager, collector, group)

        await manager.run_collector_once(collector)

        assert name not in manager._collector_succeeded
        assert manager.get_readiness_status()["collectors"][name] is False

    async def test_successful_collector_marks_ready(self) -> None:
        """A collector that completes a successful run is marked ready."""
        manager = _bare_manager(_settings())
        group = _group(EndpointGroupName.MS_PORT_STATUS, priority=3, floor=300)
        collector = _readiness_collector("MSCollector", succeeds=True, group=group)
        name = _register(manager, collector, group)

        await manager.run_collector_once(collector)

        assert name in manager._collector_succeeded
        assert manager.get_readiness_status()["collectors"][name] is True


# ---------------------------------------------------------------------------
# F-043 - manager exposes signals for the liveness dead-man switch
# ---------------------------------------------------------------------------


class TestLivenessSignals:
    """get_last_success_time / has_attempted_collection feed the /health dead-man switch."""

    def test_no_attempts(self) -> None:
        """No collector has run yet: not attempted, no last success."""
        manager = _bare_manager(_settings())
        manager.collector_health = {
            "A": {"total_runs": 0, "last_success_time": None},
            "B": {"total_runs": 0, "last_success_time": None},
        }
        assert manager.has_attempted_collection() is False
        assert manager.get_last_success_time() is None

    def test_attempted_no_success(self) -> None:
        """Attempted but never succeeded: attempted True, last success None."""
        manager = _bare_manager(_settings())
        manager.collector_health = {
            "A": {"total_runs": 3, "last_success_time": None},
        }
        assert manager.has_attempted_collection() is True
        assert manager.get_last_success_time() is None

    def test_returns_latest_success(self) -> None:
        """get_last_success_time returns the most recent success timestamp."""
        manager = _bare_manager(_settings())
        now = time.time()
        manager.collector_health = {
            "A": {"total_runs": 3, "last_success_time": now - 100},
            "B": {"total_runs": 3, "last_success_time": now - 10},
            "C": {"total_runs": 3, "last_success_time": None},
        }
        assert manager.has_attempted_collection() is True
        assert manager.get_last_success_time() == pytest.approx(now - 10)
