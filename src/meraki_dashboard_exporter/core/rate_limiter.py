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

    #: AIMD floor: the effective client-side budget never drops below this (rps).
    _AIMD_FLOOR_RPS = 0.5
    #: AIMD multiplicative-decrease cooldown: at most one halving per this window.
    _AIMD_COOLDOWN_SECONDS = 30.0

    _metrics_initialized = False
    _wait_seconds: Histogram | None = None
    _throttled_total: Counter | None = None
    _tokens_remaining: Gauge | None = None
    _throttle_backoffs_total: Counter | None = None

    def __init__(self, settings: Settings) -> None:
        """Initialize the organization rate limiter.

        Parameters
        ----------
        settings : Settings
            Application settings with rate limit configuration.

        """
        self.settings = settings
        self.enabled = settings.api.rate_limit_enabled

        base_rps = settings.api.rate_limit_requests_per_second
        share = settings.api.rate_limit_shared_fraction
        # Configured budget (requests_per_second × shared_fraction). ``rate_per_second``
        # is retained as the CONFIGURED baseline for the enable/log path; the token
        # bucket refills at ``effective_rate_per_second()`` (AIMD-adjusted, #617).
        self.rate_per_second = max(0.0, base_rps * share)
        self._configured_rate_per_second = self.rate_per_second
        self.burst = float(max(1, settings.api.rate_limit_burst))
        self.jitter_ratio = settings.api.rate_limit_jitter_ratio

        # --- AIMD 429-feedback state (#617) -----------------------------------
        # Active only in adaptive mode with AIMD enabled; otherwise
        # record_throttle_event is a no-op and effective == configured.
        scheduler = getattr(settings, "scheduler", None)
        mode = getattr(scheduler, "mode", None)
        aimd_enabled = bool(getattr(scheduler, "aimd_enabled", False))
        self._aimd_active = (mode == "adaptive") and aimd_enabled
        self._aimd_backoff_multiplier = (
            float(getattr(scheduler, "aimd_backoff_multiplier", 0.5)) if self._aimd_active else 0.5
        )
        self._aimd_recovery_rps_per_minute = (
            float(getattr(scheduler, "aimd_recovery_rps_per_minute", 0.1))
            if self._aimd_active
            else 0.1
        )
        self._effective_rate = self._configured_rate_per_second
        self._effective_updated_ts = time.monotonic()
        self._last_throttle_ts: float | None = None

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
            aimd_active=self._aimd_active,
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

        OrgRateLimiter._throttle_backoffs_total = Counter(
            CollectorMetricName.SCHEDULER_THROTTLE_BACKOFFS_TOTAL.value,
            "Total AIMD multiplicative-decrease backoff events (#617): each increment "
            "is one 429/Retry-After-driven halving of the effective client-side rate "
            "budget, at most one per 30s cooldown window. Computed feedback signal, not "
            "a Meraki API metric.",
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

                # Refill tokens based on elapsed time. The refill rate is the
                # AIMD-adjusted EFFECTIVE budget (#617), so a 429 storm applies
                # immediate backpressure independent of the scheduler re-solve.
                effective_rate = self.effective_rate_per_second()
                elapsed = max(0.0, now - last)
                tokens = min(self.burst, tokens + elapsed * effective_rate)

                if tokens >= 1.0:
                    tokens -= 1.0
                    self._tokens[key] = tokens
                    self._last_refill[key] = now
                    if OrgRateLimiter._tokens_remaining is not None:
                        OrgRateLimiter._tokens_remaining.labels(org_id=key).set(tokens)
                    return total_wait

                # Need to wait for tokens
                deficit = 1.0 - tokens
                wait_time = deficit / effective_rate
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

    def get_total_throttled(self) -> int:
        """Return the total number of client-side rate-limiter throttle events.

        Sums the shared ``_throttled_total`` counter across every
        org_id/endpoint label combination. This is the real throttle count
        surfaced on ``/status`` (F-028/F-074), replacing the hardcoded ``0``.

        Returns
        -------
        int
            Total throttle events across all label combinations, or 0 if the
            counter has not been initialised yet.

        """
        counter = OrgRateLimiter._throttled_total
        if counter is None:
            return 0
        total = 0.0
        for metric in counter.collect():
            for sample in metric.samples:
                # Skip the Counter's `_created` timestamp gauge sample.
                if sample.name.endswith("_created"):
                    continue
                total += sample.value
        return int(total)

    # --- AIMD 429-feedback control (#617) ------------------------------------

    def configured_rate_per_second(self) -> float:
        """Return the CONFIGURED API budget in requests/second.

        This is ``rate_limit_requests_per_second × rate_limit_shared_fraction``
        and is the ceiling the AIMD-adjusted effective rate recovers toward.
        """
        return self._configured_rate_per_second

    def effective_rate_per_second(self) -> float:
        """Return the current AIMD-adjusted effective budget in requests/second.

        In fixed mode / when AIMD is disabled this is always the configured rate.
        In adaptive mode it is the multiplicatively-decreased rate plus additive
        recovery accrued since the last update (``aimd_recovery_rps_per_minute``
        per clean minute), lazily computed on read and capped at the configured
        rate. The token bucket refills at this rate.
        """
        if not self._aimd_active:
            return self._configured_rate_per_second

        now = time.monotonic()
        elapsed = now - self._effective_updated_ts
        if elapsed > 0 and self._effective_rate < self._configured_rate_per_second:
            recovered = self._effective_rate + (elapsed / 60.0) * self._aimd_recovery_rps_per_minute
            self._effective_rate = min(self._configured_rate_per_second, recovered)
            self._effective_updated_ts = now
        return self._effective_rate

    def record_throttle_event(self, org_id: str | None, retry_after: float | None) -> None:
        """Feed a 429/Retry-After event into the AIMD budget controller (#617).

        Applies a multiplicative decrease (``effective ×= aimd_backoff_multiplier``),
        floored at ``0.5 rps``, at most once per 30s cooldown window (so one 429
        burst halves the budget once, not once per retry). No-op in fixed mode or
        when AIMD is disabled. Increments ``SCHEDULER_THROTTLE_BACKOFFS_TOTAL`` only
        when a decrease is actually applied.

        Parameters
        ----------
        org_id : str | None
            Organization the throttle was observed for (logging only; the budget
            is global per the single-org contract, #585).
        retry_after : float | None
            The already-extracted, capped server Retry-After in seconds, if any.

        """
        if not self._aimd_active:
            return

        now = time.monotonic()
        if (
            self._last_throttle_ts is not None
            and (now - self._last_throttle_ts) < self._AIMD_COOLDOWN_SECONDS
        ):
            # Within the cooldown window: this event belongs to a burst already
            # accounted for by the previous halving. No decrease, no counter inc.
            return

        # Settle any pending recovery up to now, then multiplicatively decrease.
        current = self.effective_rate_per_second()
        new_rate = max(self._AIMD_FLOOR_RPS, current * self._aimd_backoff_multiplier)
        self._effective_rate = new_rate
        self._effective_updated_ts = now
        self._last_throttle_ts = now

        if OrgRateLimiter._throttle_backoffs_total is not None:
            OrgRateLimiter._throttle_backoffs_total.inc()

        logger.warning(
            "AIMD rate-limit backoff applied",
            org_id=org_id or "global",
            retry_after=retry_after,
            effective_rate_per_second=round(new_rate, 3),
            configured_rate_per_second=round(self._configured_rate_per_second, 3),
        )

    def _apply_jitter(self, wait_time: float) -> float:
        if wait_time <= 0:
            return 0.0
        jitter_multiplier = 1.0 + random.uniform(-self.jitter_ratio, self.jitter_ratio)
        return max(0.0, wait_time * jitter_multiplier)
