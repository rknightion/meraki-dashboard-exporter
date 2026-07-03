"""Tests for CollectorManager scheduling clamp, readiness success-gating, and liveness helpers.

Covers bug-bash findings:
- F-018: smoothing offsets must not stretch a tier's cadence past its interval.
- F-105: /ready (tier readiness) must reflect real collection success, not mere attempts.
- F-043: manager exposes last-success / attempted signals for the liveness dead-man switch.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.constants import UpdateTier


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
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.api = MagicMock()
    with (
        patch.object(CollectorManager, "_initialize_collectors"),
        patch.object(CollectorManager, "_validate_collector_configuration"),
    ):
        return CollectorManager(client=mock_client, settings=settings)


class _SucceedingCollector:
    is_active = True

    async def collect(self) -> None:
        return None


class _FailingCollector:
    is_active = True

    async def collect(self) -> None:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# F-018 - smoothing offsets must not stretch tier cadence past the interval
# ---------------------------------------------------------------------------


class TestSmoothingOffsetClamp:
    """The maximum smoothing offset must stay strictly within the tier interval."""

    def test_smoothing_window_never_exceeds_half_interval_default(self) -> None:
        """With default settings the smoothing window stays within half the interval."""
        settings = _settings()  # defaults: smoothing_enabled True, window_ratio 0.8
        manager = _bare_manager(settings)

        for tier in UpdateTier:
            interval = manager.get_tier_interval(tier)
            window = manager._get_smoothing_window(tier)
            assert window <= interval * 0.5 + 1e-9, (
                f"{tier}: window {window} exceeds half interval {interval}"
            )
            assert window < interval

    def test_smoothing_window_capped_with_ratio_one(self) -> None:
        """Even at the maximum window ratio the offset stays bounded within the interval."""
        settings = _settings(smoothing_window_ratio=1.0)
        manager = _bare_manager(settings)

        for tier in UpdateTier:
            interval = manager.get_tier_interval(tier)
            window = manager._get_smoothing_window(tier)
            assert window <= interval * 0.5 + 1e-9
            assert window < interval

    def test_collector_offset_within_interval(self) -> None:
        """Every collector's derived offset stays within half the tier interval."""
        settings = _settings(smoothing_window_ratio=1.0)
        manager = _bare_manager(settings)

        for tier in UpdateTier:
            interval = manager.get_tier_interval(tier)
            for name in ("DeviceCollector", "NetworkHealthCollector", "OrganizationCollector"):
                offset = manager._get_collector_offset(name, tier)
                assert 0.0 <= offset <= interval * 0.5 + 1e-9
                assert offset < interval


# ---------------------------------------------------------------------------
# #591 - initial collection must skip the smoothing offset delay
# ---------------------------------------------------------------------------


class TestInitialCollectionSkipsSmoothing:
    """The first collection cycle of each tier must run without the smoothing offset.

    The deterministic per-collector offset adds up to 0.5x the tier interval of
    latency on every startup/rolling restart, delaying /ready. Smoothing must
    apply only from the 2nd cycle onward; steady-state cadence is unchanged.
    """

    def _prepare(self, manager: CollectorManager, collector: object) -> str:
        import asyncio

        name = collector.__class__.__name__
        manager.collectors[UpdateTier.FAST] = [collector]  # type: ignore[list-item]
        manager.collector_health[name] = {
            "last_success_time": None,
            "failure_streak": 0,
            "total_runs": 0,
            "total_successes": 0,
            "total_failures": 0,
        }
        manager._collector_locks[name] = asyncio.Lock()
        return name

    async def test_first_cycle_skips_offset(self) -> None:
        """On the very first cycle the offset passed to each collector is 0."""
        settings = _settings(smoothing_enabled=True)
        manager = _bare_manager(settings)
        collector = _SucceedingCollector()
        name = self._prepare(manager, collector)

        # Sanity: this collector has a non-zero configured smoothing offset.
        assert manager._get_collector_offset(name, UpdateTier.FAST) > 0
        assert manager._tier_initial_complete["fast"] is False

        captured: list[float] = []

        async def _capture(coll, tier, timeout, offset, window):  # type: ignore[no-untyped-def]
            captured.append(offset)

        with patch.object(manager, "_run_collector_with_delay", side_effect=_capture):
            await manager.collect_tier(UpdateTier.FAST)

        assert captured == [0.0]
        assert manager.collector_offsets[(name, "fast")] == 0.0

    async def test_subsequent_cycle_applies_offset(self) -> None:
        """Once the tier's initial cycle is complete, the real offset is applied."""
        settings = _settings(smoothing_enabled=True)
        manager = _bare_manager(settings)
        collector = _SucceedingCollector()
        name = self._prepare(manager, collector)

        # Simulate the initial cycle already having completed.
        manager._tier_initial_complete["fast"] = True
        expected = manager._get_collector_offset(name, UpdateTier.FAST)
        assert expected > 0

        captured: list[float] = []

        async def _capture(coll, tier, timeout, offset, window):  # type: ignore[no-untyped-def]
            captured.append(offset)

        with patch.object(manager, "_run_collector_with_delay", side_effect=_capture):
            await manager.collect_tier(UpdateTier.FAST)

        assert captured == [expected]
        assert manager.collector_offsets[(name, "fast")] == expected


# ---------------------------------------------------------------------------
# F-105 - tier readiness reflects real success, not just an attempted cycle
# ---------------------------------------------------------------------------


class TestReadinessSuccessGating:
    """collect_tier must only mark a tier ready once a collector actually succeeds."""

    async def test_all_collectors_fail_tier_not_ready(self) -> None:
        """A tier where every collector fails is not marked ready (F-105)."""
        import asyncio

        settings = _settings(smoothing_enabled=False)
        manager = _bare_manager(settings)

        collector = _FailingCollector()
        name = collector.__class__.__name__
        manager.collectors[UpdateTier.FAST] = [collector]  # type: ignore[list-item]
        manager.collector_health[name] = {
            "last_success_time": None,
            "failure_streak": 0,
            "total_runs": 0,
            "total_successes": 0,
            "total_failures": 0,
        }
        manager._collector_locks[name] = asyncio.Lock()

        await manager.collect_tier(UpdateTier.FAST)

        assert manager._tier_initial_complete["fast"] is False
        assert manager.get_readiness_status()["collectors"]["fast"] is False

    async def test_successful_collector_marks_tier_ready(self) -> None:
        """A tier with a succeeding collector is marked ready."""
        import asyncio

        settings = _settings(smoothing_enabled=False)
        manager = _bare_manager(settings)

        collector = _SucceedingCollector()
        name = collector.__class__.__name__
        manager.collectors[UpdateTier.FAST] = [collector]  # type: ignore[list-item]
        manager.collector_health[name] = {
            "last_success_time": None,
            "failure_streak": 0,
            "total_runs": 0,
            "total_successes": 0,
            "total_failures": 0,
        }
        manager._collector_locks[name] = asyncio.Lock()

        await manager.collect_tier(UpdateTier.FAST)

        assert manager._tier_initial_complete["fast"] is True
        assert manager.get_readiness_status()["collectors"]["fast"] is True

    async def test_empty_tier_still_marks_ready(self) -> None:
        """A tier with no collectors is trivially ready."""
        settings = _settings(smoothing_enabled=False)
        manager = _bare_manager(settings)

        manager.collectors[UpdateTier.FAST] = []
        await manager.collect_tier(UpdateTier.FAST)

        assert manager._tier_initial_complete["fast"] is True


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
