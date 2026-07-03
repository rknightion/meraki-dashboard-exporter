"""Acceptance tests for the #631 de-tiering (FAST/MEDIUM/SLOW removed).

Covers the frozen acceptance criteria that are best expressed as focused unit
tests: solved cadence == floor with no budget pressure, solver determinism
without the tier param, the failure-retry attempt-tracking layer, the manual
force-run gate bypass, and the config-surface changes (stale-env-var warning
#631, build-metadata allowlist #634).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.core.scheduler import (
    EndpointGroup,
    EndpointGroupName,
    EndpointScheduler,
    OrgShape,
    solve_intervals,
)


def _settings(
    *, failure_retry: int = 300, overrides: dict[str, int] | None = None
) -> SimpleNamespace:
    """A namespace settings object the scheduler reads dynamically."""
    return SimpleNamespace(
        scheduler=SimpleNamespace(
            mode="adaptive",
            target_utilization=0.7,
            max_stretch_factor=4.0,
            max_interval_seconds=3600,
            resolve_interval_seconds=900,
            failure_retry_seconds=failure_retry,
            aimd_enabled=True,
            aimd_backoff_multiplier=0.5,
            aimd_recovery_rps_per_minute=0.1,
            aimd_resolve_hysteresis=0.2,
            group_interval_overrides=overrides or {},
        ),
        api=SimpleNamespace(
            rate_limit_requests_per_second=10.0,
            rate_limit_shared_fraction=0.8,
            model_fields_set=set(),
        ),
        monitoring=SimpleNamespace(metric_ttl_multiplier=2.0),
    )


def _rate_limiter(effective_rps: float = 1000.0) -> MagicMock:
    """A rate limiter double with an effectively-unlimited budget (no stretch)."""
    rl = MagicMock()
    rl.effective_rate_per_second.return_value = effective_rps
    return rl


def _small_shape() -> OrgShape:
    """A tiny org so estimated demand is far below any budget (no stretching)."""
    return OrgShape(
        org_id="org1",
        network_count=2,
        wireless_network_count=1,
        switch_network_count=1,
        appliance_network_count=0,
        sensor_network_count=1,
        camera_network_count=0,
        cellular_network_count=0,
        device_count=5,
        ap_count=2,
        switch_count=2,
        appliance_count=0,
        physical_mx_count=0,
        camera_count=0,
        sensor_count=1,
        cellular_count=0,
    )


# Representative groups at the three floors the acceptance criteria pin.
_GROUPS = (
    EndpointGroup(
        name=EndpointGroupName.MT_SENSOR_READINGS,
        priority=2,
        floor_seconds=60,
        cost_fn=lambda shape: 2.0,
    ),
    EndpointGroup(
        name=EndpointGroupName.DEVICE_AVAILABILITY,
        priority=1,
        floor_seconds=120,
        cost_fn=lambda shape: 1.0,
    ),
    EndpointGroup(
        name=EndpointGroupName.NH_CONNECTION_STATS,
        priority=3,
        floor_seconds=1800,
        cost_fn=lambda shape: float(shape.wireless_network_count),
    ),
)


class TestSolvedCadenceEqualsFloor:
    """No budget pressure ⇒ every group runs at exactly its volatility floor."""

    def _resolved(self) -> EndpointScheduler:
        sched = EndpointScheduler(_settings(), _rate_limiter())  # type: ignore[arg-type]
        sched.register_groups(_GROUPS)
        sched.resolve(_small_shape())
        return sched

    def test_device_availability_cadence_120(self) -> None:
        """Device availability cadence 120."""
        assert self._resolved().interval_for(EndpointGroupName.DEVICE_AVAILABILITY) == 120

    def test_mt_sensor_readings_cadence_60(self) -> None:
        """Mt sensor readings cadence 60."""
        assert self._resolved().interval_for(EndpointGroupName.MT_SENSOR_READINGS) == 60

    def test_floor_1800_group_cadence_1800(self) -> None:
        """Floor 1800 group cadence 1800."""
        assert self._resolved().interval_for(EndpointGroupName.NH_CONNECTION_STATS) == 1800

    def test_nothing_stretched_under_generous_budget(self) -> None:
        """Nothing stretched under generous budget."""
        sched = self._resolved()
        for g in _GROUPS:
            assert sched.interval_for(g.name) == g.floor_seconds


class TestSolverDeterminismWithoutTier:
    """solve_intervals is pure/deterministic and no longer takes tier_intervals."""

    def test_identical_inputs_identical_output(self) -> None:
        """Identical inputs identical output."""
        shape = _small_shape()
        args = (_GROUPS, shape, 8.0, 0.7, {}, 4.0, 3600.0)
        first = solve_intervals(*args)
        second = solve_intervals(*args)
        assert first == second

    def test_pre_solve_interval_is_floor(self) -> None:
        """Pre solve interval is floor."""
        # Before any resolve(), interval_for falls back to the group's floor
        # (there is no tier heartbeat any more).
        sched = EndpointScheduler(_settings(), _rate_limiter())  # type: ignore[arg-type]
        sched.register_groups(_GROUPS)
        assert sched.interval_for(EndpointGroupName.DEVICE_AVAILABILITY) == 120
        assert sched.interval_for(EndpointGroupName.NH_CONNECTION_STATS) == 1800


class TestFailureRetrySpacing:
    """Failed fetches re-attempt after failure_retry_seconds (not immediately, #631)."""

    def _sched(self) -> EndpointScheduler:
        sched = EndpointScheduler(_settings(failure_retry=300), _rate_limiter())  # type: ignore[arg-type]
        sched.register_groups(_GROUPS)
        sched.resolve(_small_shape())
        return sched

    def test_failed_fetch_retries_after_failure_retry_not_immediately(self) -> None:
        """Failed fetch retries after failure retry not immediately."""
        sched = self._sched()
        g = EndpointGroupName.NH_CONNECTION_STATS  # interval 1800, failure_retry 300
        # First attempt at t=0 is due (never ran); records the attempt. No
        # mark_ran ⇒ the fetch "failed".
        assert sched.should_run(g, now=0.0) is True
        # Immediately after: NOT due (hot-loop prevented).
        assert sched.should_run(g, now=1.0) is False
        # Just before failure_retry elapses: still not due.
        assert sched.should_run(g, now=299.0) is False
        # At failure_retry: due again (re-attempt), long before the 1800s interval.
        assert sched.should_run(g, now=300.0) is True

    def test_successful_cadence_not_delayed_by_failure_retry(self) -> None:
        """Successful cadence not delayed by failure retry."""
        # A fast group (floor 60) that SUCCEEDS must keep its 60s cadence, never
        # be forced to failure_retry_seconds (300).
        sched = self._sched()
        g = EndpointGroupName.MT_SENSOR_READINGS  # interval 60
        assert sched.should_run(g, now=0.0) is True
        sched.mark_ran(g, now=0.5)  # success
        # Due again ~54s after the last success (60 * 0.9), and crucially NOT
        # delayed to failure_retry_seconds (300) — a successful cadence is never
        # gated by the failure-retry spacing.
        assert sched.should_run(g, now=55.0) is True

    def test_next_due_reflects_failure_retry_floor(self) -> None:
        """Next due reflects failure retry floor."""
        sched = self._sched()
        g = EndpointGroupName.NH_CONNECTION_STATS
        sched.should_run(g, now=0.0)  # attempt, no success
        # next_due is floored at last_attempt + failure_retry (300), not now.
        assert sched.next_due(g, now=1.0) == pytest.approx(300.0)


class TestForceRunGate:
    """A forced run opens every gate regardless of the schedule (#631)."""

    def test_force_run_bypasses_scheduler_gate(self) -> None:
        """Force run bypasses scheduler gate."""
        from meraki_dashboard_exporter.core.collector import MetricCollector

        collector = MagicMock(spec=MetricCollector)
        collector.scheduler = MagicMock()
        collector.scheduler.should_run.return_value = False
        collector._force_run = True
        # Call the real unbound helper against our mock.
        assert (
            MetricCollector._should_run_group(collector, EndpointGroupName.DEVICE_AVAILABILITY)
            is True
        )

    def test_no_force_run_defers_to_scheduler(self) -> None:
        """No force run defers to scheduler."""
        from meraki_dashboard_exporter.core.collector import MetricCollector

        collector = MagicMock(spec=MetricCollector)
        collector.scheduler = MagicMock()
        collector.scheduler.should_run.return_value = False
        collector._force_run = False
        assert (
            MetricCollector._should_run_group(collector, EndpointGroupName.DEVICE_AVAILABILITY)
            is False
        )


class TestRemovedEnvVarWarning:
    """Removed tier env vars are reported with migration guidance (#631)."""

    def test_find_removed_env_vars_maps_to_replacements(self) -> None:
        """Find removed env vars maps to replacements."""
        from meraki_dashboard_exporter.core.config_models import find_removed_env_vars

        env = {
            "MERAKI_EXPORTER_UPDATE_INTERVALS__FAST": "60",
            "MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_SLOW": "2",
            "MERAKI_EXPORTER_MERAKI__API_KEY": "x" * 40,  # not removed
        }
        found = dict(find_removed_env_vars(env))
        assert (
            found["MERAKI_EXPORTER_UPDATE_INTERVALS__FAST"]
            == "MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES"
        )
        assert (
            found["MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_SLOW"]
            == "MERAKI_EXPORTER_COLLECTORS__MAX_CONCURRENT_COLLECTORS"
        )
        assert "MERAKI_EXPORTER_MERAKI__API_KEY" not in found

    def test_removed_and_build_metadata_vars_not_flagged_as_unrecognized(self) -> None:
        """Removed and build metadata vars not flagged as unrecognized."""
        # Removed vars are reported separately; build metadata (#634) is known.
        from meraki_dashboard_exporter.core.config import Settings
        from meraki_dashboard_exporter.core.config_models import find_unrecognized_env_vars

        env = {
            "MERAKI_EXPORTER_UPDATE_INTERVALS__FAST": "60",  # removed, not "unrecognized"
            "MERAKI_EXPORTER_VERSION": "abc123",  # #634 build metadata
            "MERAKI_EXPORTER_COMMIT": "deadbeef",  # #634 build metadata
            "MERAKI_EXPORTER_TYPO__FOO": "1",  # a real typo
        }
        unrecognized = find_unrecognized_env_vars(env, Settings)
        assert "MERAKI_EXPORTER_UPDATE_INTERVALS__FAST" not in unrecognized
        assert "MERAKI_EXPORTER_VERSION" not in unrecognized
        assert "MERAKI_EXPORTER_COMMIT" not in unrecognized
        assert "MERAKI_EXPORTER_TYPO__FOO" in unrecognized


class TestBuildMetadataNotRedacted:
    """Build-metadata env vars print in clear in the config summary (#634)."""

    @pytest.mark.parametrize("key", ["MERAKI_EXPORTER_VERSION", "MERAKI_EXPORTER_COMMIT"])
    def test_version_commit_not_masked(self, key: str) -> None:
        """Version commit not masked."""
        from meraki_dashboard_exporter.core.config_logger import mask_sensitive_value

        assert mask_sensitive_value(key, "v1.2.3-abcdef") == "v1.2.3-abcdef"
