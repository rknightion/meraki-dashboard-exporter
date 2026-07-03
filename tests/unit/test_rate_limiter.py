"""Tests for OrgRateLimiter accessors and keying."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.core.rate_limiter import OrgRateLimiter

_MONOTONIC = "meraki_dashboard_exporter.core.rate_limiter.time.monotonic"


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.api.rate_limit_enabled = True
    settings.api.rate_limit_requests_per_second = 10.0
    settings.api.rate_limit_shared_fraction = 1.0
    settings.api.rate_limit_burst = 20
    settings.api.rate_limit_jitter_ratio = 0.1
    return settings


def _make_aimd_settings(
    *,
    mode: str = "adaptive",
    aimd_enabled: bool = True,
    backoff: float = 0.5,
    recovery: float = 0.0,
    rps: float = 10.0,
    share: float = 0.8,
) -> MagicMock:
    """Build a settings mock wired for AIMD (#617).

    ``recovery`` defaults to 0 so backoff tests get clean halving arithmetic
    without recovery drift.
    """
    settings = MagicMock()
    settings.api.rate_limit_enabled = True
    settings.api.rate_limit_requests_per_second = rps
    settings.api.rate_limit_shared_fraction = share
    settings.api.rate_limit_burst = 20
    settings.api.rate_limit_jitter_ratio = 0.0
    settings.scheduler.mode = mode
    settings.scheduler.aimd_enabled = aimd_enabled
    settings.scheduler.aimd_backoff_multiplier = backoff
    settings.scheduler.aimd_recovery_rps_per_minute = recovery
    return settings


def _backoff_counter_total() -> float:
    counter = OrgRateLimiter._throttle_backoffs_total
    assert counter is not None
    total = 0.0
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_created"):
                continue
            total += sample.value
    return total


class TestThrottledAccessor:
    """F-028/F-074: expose the real throttle-event total."""

    def test_get_total_throttled_reflects_increments(self) -> None:
        """The accessor sums the shared throttled counter across labels."""
        limiter = OrgRateLimiter(_make_settings())

        before = limiter.get_total_throttled()

        assert OrgRateLimiter._throttled_total is not None
        OrgRateLimiter._throttled_total.labels(org_id="org1", endpoint="getX").inc()
        OrgRateLimiter._throttled_total.labels(org_id="org2", endpoint="getY").inc(2)

        assert limiter.get_total_throttled() == before + 3


class TestOrgKeying:
    """acquire() buckets by the provided org, not the shared 'global' key."""

    async def test_acquire_with_org_id_keys_by_org(self) -> None:
        """A supplied org_id creates a per-org bucket, not the global one."""
        limiter = OrgRateLimiter(_make_settings())

        await limiter.acquire("org_scoped", "getSomething")

        assert "org_scoped" in limiter._tokens
        assert "global" not in limiter._tokens

    async def test_acquire_without_org_id_falls_back_to_global(self) -> None:
        """A None org_id lands in the shared global bucket (the pre-fix behavior)."""
        limiter = OrgRateLimiter(_make_settings())

        await limiter.acquire(None, "getSomething")

        assert "global" in limiter._tokens


class TestConfiguredRate:
    """configured_rate_per_second() == requests_per_second × shared_fraction."""

    def test_configured_rate_is_rps_times_share(self) -> None:
        """configured_rate_per_second() multiplies rps by the shared fraction."""
        limiter = OrgRateLimiter(_make_aimd_settings(rps=10.0, share=0.8))
        assert limiter.configured_rate_per_second() == pytest.approx(8.0)

    def test_effective_starts_at_configured(self) -> None:
        """The effective rate starts equal to the configured rate."""
        limiter = OrgRateLimiter(_make_aimd_settings(rps=10.0, share=0.8))
        assert limiter.effective_rate_per_second() == pytest.approx(8.0)


class TestAIMDInactive:
    """No-op AIMD paths.

    In fixed mode / aimd_enabled=False, record_throttle_event is a no-op and
    effective == configured.
    """

    def test_fixed_mode_record_is_noop(self) -> None:
        """Fixed mode: a throttle event leaves the effective rate unchanged."""
        limiter = OrgRateLimiter(
            _make_aimd_settings(mode="fixed", aimd_enabled=True, rps=10.0, share=0.8)
        )
        limiter.record_throttle_event("org", 5.0)
        assert limiter.effective_rate_per_second() == pytest.approx(8.0)
        assert limiter.effective_rate_per_second() == pytest.approx(
            limiter.configured_rate_per_second()
        )

    def test_aimd_disabled_record_is_noop(self) -> None:
        """aimd_enabled=False: a throttle event leaves the effective rate unchanged."""
        limiter = OrgRateLimiter(
            _make_aimd_settings(mode="adaptive", aimd_enabled=False, rps=10.0, share=0.8)
        )
        limiter.record_throttle_event("org", 5.0)
        assert limiter.effective_rate_per_second() == pytest.approx(8.0)


class TestAIMDBackoff:
    """Multiplicative decrease: one halving per 30s cooldown window, floored at 0.5."""

    def test_single_event_halves_once(self) -> None:
        """A single throttle event halves the effective rate once."""
        limiter = OrgRateLimiter(_make_aimd_settings(backoff=0.5, rps=10.0, share=0.8))
        assert limiter.effective_rate_per_second() == pytest.approx(8.0)
        limiter.record_throttle_event("org", 1.0)
        assert limiter.effective_rate_per_second() == pytest.approx(4.0)

    def test_burst_within_cooldown_halves_once(self) -> None:
        """A burst of events inside the 30s cooldown halves the rate only once."""
        with patch(_MONOTONIC) as mono:
            mono.return_value = 1000.0
            limiter = OrgRateLimiter(_make_aimd_settings(backoff=0.5, rps=10.0, share=0.8))
            limiter.record_throttle_event("org", 1.0)  # 8.0 -> 4.0
            for offset in (0.1, 5.0, 29.9):  # all within the 30s cooldown window
                mono.return_value = 1000.0 + offset
                limiter.record_throttle_event("org", 1.0)  # no-op
            mono.return_value = 1029.9
            assert limiter.effective_rate_per_second() == pytest.approx(4.0)

    def test_second_event_after_cooldown_halves_again(self) -> None:
        """An event past the 30s cooldown applies a second halving."""
        with patch(_MONOTONIC) as mono:
            mono.return_value = 1000.0
            limiter = OrgRateLimiter(_make_aimd_settings(backoff=0.5, rps=10.0, share=0.8))
            limiter.record_throttle_event("org", 1.0)  # 8.0 -> 4.0
            mono.return_value = 1031.0  # > 30s later
            limiter.record_throttle_event("org", 1.0)  # 4.0 -> 2.0
            mono.return_value = 1031.0
            assert limiter.effective_rate_per_second() == pytest.approx(2.0)

    def test_effective_floored_at_half_rps(self) -> None:
        """Repeated halvings clamp the effective rate at the 0.5 rps floor."""
        with patch(_MONOTONIC) as mono:
            t = 0.0
            mono.return_value = t
            limiter = OrgRateLimiter(_make_aimd_settings(backoff=0.5, rps=10.0, share=0.8))
            for _ in range(12):  # 8 -> 4 -> 2 -> 1 -> 0.5 -> 0.5 ...
                mono.return_value = t
                limiter.record_throttle_event("org", 1.0)
                t += 31.0  # clear cooldown each time
            mono.return_value = t
            assert limiter.effective_rate_per_second() == pytest.approx(0.5)


class TestAIMDRecovery:
    """Additive increase: +recovery_rps_per_minute per clean minute, capped at configured."""

    def test_recovery_adds_over_clean_minutes(self) -> None:
        """Effective rate recovers additively over clean minutes after a backoff."""
        with patch(_MONOTONIC) as mono:
            mono.return_value = 0.0
            limiter = OrgRateLimiter(
                _make_aimd_settings(backoff=0.5, recovery=0.1, rps=10.0, share=0.8)
            )
            limiter.record_throttle_event("org", 1.0)  # 8.0 -> 4.0 at t=0
            mono.return_value = 600.0  # 10 clean minutes -> +1.0 rps
            assert limiter.effective_rate_per_second() == pytest.approx(5.0)

    def test_recovery_capped_at_configured(self) -> None:
        """Recovery never exceeds the configured rate no matter how long it runs."""
        with patch(_MONOTONIC) as mono:
            mono.return_value = 0.0
            limiter = OrgRateLimiter(
                _make_aimd_settings(backoff=0.5, recovery=0.1, rps=10.0, share=0.8)
            )
            limiter.record_throttle_event("org", 1.0)  # 8.0 -> 4.0
            mono.return_value = 1_000_000.0  # absurdly long clean period
            assert limiter.effective_rate_per_second() == pytest.approx(8.0)


class TestBackoffCounter:
    """SCHEDULER_THROTTLE_BACKOFFS_TOTAL increments once per applied MD event."""

    def test_counter_increments_per_md_event_not_per_call(self) -> None:
        """The backoff counter counts applied halvings, not cooldown no-ops."""
        with patch(_MONOTONIC) as mono:
            mono.return_value = 0.0
            limiter = OrgRateLimiter(_make_aimd_settings(backoff=0.5, rps=10.0, share=0.8))
            before = _backoff_counter_total()
            limiter.record_throttle_event("org", 1.0)  # MD -> +1
            mono.return_value = 5.0
            limiter.record_throttle_event("org", 1.0)  # cooldown no-op -> no inc
            mono.return_value = 40.0
            limiter.record_throttle_event("org", 1.0)  # MD -> +1
            assert _backoff_counter_total() - before == pytest.approx(2.0)

    def test_counter_not_incremented_in_fixed_mode(self) -> None:
        """Fixed mode records no backoff events on the counter."""
        limiter = OrgRateLimiter(_make_aimd_settings(mode="fixed", aimd_enabled=True))
        before = _backoff_counter_total()
        limiter.record_throttle_event("org", 1.0)
        assert _backoff_counter_total() - before == pytest.approx(0.0)


class TestBucketRefillUsesEffective:
    """The token bucket refills at effective_rate_per_second() (rate_limiter.py:106,118)."""

    async def test_acquire_reads_effective_rate(self) -> None:
        """acquire() computes the bucket refill from effective_rate_per_second()."""
        limiter = OrgRateLimiter(_make_aimd_settings(rps=10.0, share=1.0))
        spy = MagicMock(wraps=limiter.effective_rate_per_second)
        limiter.effective_rate_per_second = spy  # type: ignore[method-assign]

        await limiter.acquire("org", "getSomething")

        assert spy.called
