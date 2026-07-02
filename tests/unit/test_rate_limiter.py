"""Tests for OrgRateLimiter accessors and keying."""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.core.rate_limiter import OrgRateLimiter


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.api.rate_limit_enabled = True
    settings.api.rate_limit_requests_per_second = 10.0
    settings.api.rate_limit_shared_fraction = 1.0
    settings.api.rate_limit_burst = 20
    settings.api.rate_limit_jitter_ratio = 0.1
    return settings


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
