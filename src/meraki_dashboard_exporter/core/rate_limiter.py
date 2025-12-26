"""Client-side rate limiter for Meraki API calls."""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram

from .constants.metrics_constants import CollectorMetricName
from .logging import get_logger
from .metrics import LabelName

if TYPE_CHECKING:
    from .config import Settings

logger = get_logger(__name__)


class OrgRateLimiter:
    """Per-organization token bucket rate limiter for API calls."""

    _metrics_initialized = False
    _wait_seconds: Histogram | None = None
    _throttled_total: Counter | None = None
    _tokens_remaining: Gauge | None = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.api.rate_limit_enabled

        base_rps = settings.api.rate_limit_requests_per_second
        share = settings.api.rate_limit_shared_fraction
        self.rate_per_second = max(0.0, base_rps * share)
        self.burst = float(max(1, settings.api.rate_limit_burst))
        self.jitter_ratio = settings.api.rate_limit_jitter_ratio

        self._lock = asyncio.Lock()
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = {}

        self._init_metrics()

        logger.info(
            "Initialized rate limiter",
            enabled=self.enabled,
            rate_per_second=self.rate_per_second,
            burst=self.burst,
            share_fraction=share,
        )

    def _init_metrics(self) -> None:
        if OrgRateLimiter._metrics_initialized:
            return

        OrgRateLimiter._wait_seconds = Histogram(
            CollectorMetricName.API_RATE_LIMITER_WAIT_SECONDS.value,
            "Seconds spent waiting for client-side rate limiter",
            labelnames=[LabelName.ORG_ID.value, LabelName.ENDPOINT.value],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60],
        )

        OrgRateLimiter._throttled_total = Counter(
            CollectorMetricName.API_RATE_LIMITER_THROTTLED_TOTAL.value,
            "Total number of client-side rate limiter waits",
            labelnames=[LabelName.ORG_ID.value, LabelName.ENDPOINT.value],
        )

        OrgRateLimiter._tokens_remaining = Gauge(
            CollectorMetricName.API_RATE_LIMITER_TOKENS.value,
            "Estimated remaining tokens in client-side rate limiter bucket",
            labelnames=[LabelName.ORG_ID.value],
        )

        OrgRateLimiter._metrics_initialized = True

    async def acquire(self, org_id: str | None, endpoint: str) -> float:
        """Acquire a token for the given organization.

        Returns the total wait time in seconds if throttled.
        """
        if not self.enabled or self.rate_per_second <= 0:
            return 0.0

        key = org_id or "global"
        total_wait = 0.0

        while True:
            async with self._lock:
                now = time.monotonic()
                last = self._last_refill.get(key, now)
                tokens = self._tokens.get(key, self.burst)

                # Refill tokens based on elapsed time
                elapsed = max(0.0, now - last)
                tokens = min(self.burst, tokens + elapsed * self.rate_per_second)

                if tokens >= 1.0:
                    tokens -= 1.0
                    self._tokens[key] = tokens
                    self._last_refill[key] = now
                    if OrgRateLimiter._tokens_remaining is not None:
                        OrgRateLimiter._tokens_remaining.labels(org_id=key).set(tokens)
                    return total_wait

                # Need to wait for tokens
                deficit = 1.0 - tokens
                wait_time = deficit / self.rate_per_second
                wait_time = self._apply_jitter(wait_time)
                total_wait += wait_time

                if OrgRateLimiter._throttled_total is not None:
                    OrgRateLimiter._throttled_total.labels(
                        org_id=key,
                        endpoint=endpoint,
                    ).inc()

                if OrgRateLimiter._wait_seconds is not None:
                    OrgRateLimiter._wait_seconds.labels(
                        org_id=key,
                        endpoint=endpoint,
                    ).observe(wait_time)

                # Store state before releasing lock
                self._tokens[key] = tokens
                self._last_refill[key] = now

            await asyncio.sleep(wait_time)

    def _apply_jitter(self, wait_time: float) -> float:
        if wait_time <= 0:
            return 0.0
        jitter_multiplier = 1.0 + random.uniform(-self.jitter_ratio, self.jitter_ratio)
        return max(0.0, wait_time * jitter_multiplier)
