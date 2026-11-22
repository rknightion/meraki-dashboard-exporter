"""Shared progress, retry spacing and capacity rules for resumable fan-outs."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

#: Fallbacks for the per-attempt call budget when settings or the limiter are
#: not readable (test doubles, pre-seam settings). They match the shipped
#: defaults: a 120 s per-fetch deadline and 10 requests/s x 0.8 shared fraction.
_DEFAULT_DEADLINE_SECONDS = 120.0
_DEFAULT_RATE_PER_SECOND = 8.0
_DEFAULT_FAILURE_RETRY_SECONDS = 300.0


def _positive_number(value: Any) -> float | None:
    """Return ``value`` as a float when it is a real positive number, else None.

    Strict ``isinstance`` (no ``float()`` coercion), so mocks and other proxies
    that implement ``__float__`` fall back to the defaults.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if number > 0 and math.isfinite(number) else None


def per_attempt_call_budget(settings: Any, rate_limiter: Any, calls_per_item: int = 1) -> int:
    """Items one resumable fan-out attempt may fetch (#996 frozen formula).

    ``floor(0.5 x per_fetch_deadline_seconds x effective_rate / calls_per_item)``,
    at least 1. The effective rate is the limiter's AIMD-adjusted
    ``effective_rate_per_second()``; without a readable limiter it is
    ``rate_limit_requests_per_second x rate_limit_shared_fraction``. Half the
    deadline leaves room for sharing the budget with other collectors, so an
    attempt normally ends on its own before the per-fetch deadline cancels it.
    At shipped defaults this is 480 single-call items.
    """
    api = getattr(settings, "api", None)
    deadline = _positive_number(getattr(api, "per_fetch_deadline_seconds", None))
    deadline = deadline or _DEFAULT_DEADLINE_SECONDS

    rate: float | None = None
    reader = getattr(rate_limiter, "effective_rate_per_second", None)
    if callable(reader):
        rate = _positive_number(reader())
    if rate is None:
        rps = _positive_number(getattr(api, "rate_limit_requests_per_second", None))
        fraction = _positive_number(getattr(api, "rate_limit_shared_fraction", None))
        if rps is not None and fraction is not None:
            rate = rps * fraction
    rate = rate or _DEFAULT_RATE_PER_SECOND

    per_item = max(1, int(calls_per_item))
    return max(1, math.floor(0.5 * deadline * rate / per_item))


def failure_retry_spacing(settings: Any, interval: float) -> float:
    """Wait before a failed item is retried: ``failure_retry_seconds`` capped at the interval.

    Mirrors the scheduler's group-level failure spacing (#631/#1005) per item.
    """
    scheduler = getattr(settings, "scheduler", None)
    retry = _positive_number(getattr(scheduler, "failure_retry_seconds", None))
    retry = retry or _DEFAULT_FAILURE_RETRY_SECONDS
    if math.isfinite(interval) and interval > 0:
        return min(retry, interval)
    return retry


def sweep_ttl_seconds(
    group_ttl: float | None,
    interval: float,
    item_count: int,
    budget: int,
    cadence: float,
) -> float | None:
    """Series TTL that outlives one full resumable sweep (#996 frozen rule).

    A fleet that fits one attempt keeps the group TTL unchanged. A larger one
    needs ``passes = ceil(items / budget)`` attempts, one per collector wake
    (``cadence``), so an item can wait up to ``interval + passes x cadence``
    between fetches. The TTL scales by the same ratio the group TTL has to its
    interval (``metric_ttl_multiplier``). ``None`` (no scheduler) stays ``None``.
    """
    if group_ttl is None or budget <= 0 or item_count <= budget:
        return group_ttl
    if not math.isfinite(interval) or interval <= 0:
        return group_ttl
    passes = math.ceil(item_count / budget)
    span = interval + passes * max(cadence, 0.0)
    return max(group_ttl, group_ttl * span / interval)


class FanoutCursor:
    """Per-item progress for a resumable fan-out (#996 frozen contract).

    Keeps, per item key, the monotonic time of the last successful fetch and of
    the last attempt. Each attempt prunes the state to the current item list,
    then selects the due items stalest first (never-collected before all
    others) up to the per-attempt budget. An item is stamped only when its
    fetch succeeded; a failed item is retried once ``retry_spacing`` has passed
    since its failed attempt, so a persistently failing item cannot spend the
    budget on every wake.
    """

    def __init__(self) -> None:
        """Start with no progress recorded."""
        self.last_success: dict[str, float] = {}
        self.last_attempt: dict[str, float] = {}

    def prune(self, keys: Iterable[str]) -> None:
        """Drop state for every item no longer in ``keys``."""
        current = set(keys)
        for state in (self.last_success, self.last_attempt):
            for key in [k for k in state if k not in current]:
                del state[key]

    def _is_due(self, key: str, interval: float, retry_spacing: float, now: float) -> bool:
        last_ok = self.last_success.get(key)
        last_try = self.last_attempt.get(key)
        if last_try is not None and (last_ok is None or last_try > last_ok):
            # The newest attempt failed: space the retry.
            if now - last_try < retry_spacing:
                return False
        return last_ok is None or interval <= 0 or (now - last_ok) >= interval

    def select(
        self,
        keys: Sequence[str],
        *,
        interval: float,
        retry_spacing: float,
        limit: int,
        now: float,
    ) -> list[str]:
        """Return at most ``limit`` due keys, stalest first, never-collected first.

        Ties keep the order of ``keys``.
        """
        due = [k for k in keys if self._is_due(k, interval, retry_spacing, now)]
        due.sort(key=lambda k: self.last_success.get(k, -math.inf))
        return due[: max(0, limit)]

    def all_fresh(self, keys: Iterable[str], interval: float, now: float) -> bool:
        """Whether every key has a successful fetch younger than ``interval``."""
        for key in keys:
            last_ok = self.last_success.get(key)
            if last_ok is None or (interval > 0 and (now - last_ok) >= interval):
                return False
        return True

    def record_attempt(self, key: str, now: float) -> None:
        """Record that a fetch for ``key`` is starting."""
        self.last_attempt[key] = now

    def record_success(self, key: str, now: float) -> None:
        """Stamp ``key`` as collected."""
        self.last_success[key] = now
