"""Single entry point for outbound Meraki SDK operations."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any

import structlog
from prometheus_client import Counter

from .constants.metrics_constants import CollectorMetricName
from .error_handling import (
    RetryableAPIError,
    _apply_jitter,
    _get_retry_after_seconds,
    _is_rate_limit_error,
    validate_response_format,
)
from .metrics import LabelName


class FacadeRateLimitExhaustedError(RetryableAPIError):
    """Terminal 429 outcome already retried by :class:`MerakiApiFacade`."""

    facade_retry_exhausted = True


class MerakiApiFacade:
    """Stable async facade seam for synchronous Meraki SDK operations.

    It is intentionally the only component that crosses from async exporter code
    to the synchronous Dashboard SDK.  One logical call may make multiple SDK
    attempts when Dashboard returns 429; every attempt is paced and metered.
    """

    _attempts_total: Counter | None = None
    _requests_total: Counter | None = None

    def __init__(
        self,
        *,
        settings: Any | None = None,
        rate_limiter: Any | None = None,
    ) -> None:
        """Bind the facade to the settings and limiter of its owner."""
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._ensure_metrics()

    @classmethod
    def _ensure_metrics(cls) -> None:
        """Register the facade metrics once per Prometheus registry."""
        if cls._attempts_total is None:
            cls._attempts_total = Counter(
                CollectorMetricName.EXPORTER_API_REQUEST_ATTEMPTS_TOTAL.value,
                "Total outbound Meraki SDK request attempts by operation and outcome.",
                labelnames=[LabelName.OPERATION.value, LabelName.STATUS.value],
            )
        if cls._requests_total is None:
            cls._requests_total = Counter(
                CollectorMetricName.API_REQUESTS_TOTAL.value,
                "Total outbound Meraki SDK request attempts made by this exporter process.",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.METHOD.value,
                    LabelName.STATUS_CODE.value,
                ],
            )

    @classmethod
    def requests_total(cls) -> Counter:
        """Return the compatibility counter used by status/readiness consumers."""
        cls._ensure_metrics()
        assert cls._requests_total is not None
        return cls._requests_total

    async def call(
        self,
        operation: str,
        fn: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute, pace, meter, retry, deadline-bound, and validate one SDK call."""
        deadline = _numeric_setting(self._settings, "per_fetch_deadline_seconds", 120.0)
        max_retries = int(_numeric_setting(self._settings, "max_retries", 3.0))
        retry_after_cap = _numeric_setting(self._settings, "retry_after_max_seconds", 60.0)
        org_id = _resolve_org_id(args, kwargs)
        attempt = 0

        async with asyncio.timeout(deadline):
            while True:
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire(org_id, operation)
                try:
                    response = await asyncio.get_running_loop().run_in_executor(
                        None, functools.partial(fn, *args, **kwargs)
                    )
                    result = _validate_generic_response(response, operation)
                except Exception as exc:
                    status = _status_from_exception(exc)
                    self._record_attempt(operation, status)
                    if not _is_rate_limit_error(exc):
                        raise
                    if attempt >= max_retries:
                        raise FacadeRateLimitExhaustedError(
                            f"{operation} exhausted facade attempts"
                        ) from exc

                    retry_after = _get_retry_after_seconds(exc)
                    if retry_after is not None:
                        retry_after = min(retry_after, retry_after_cap)
                    if self._rate_limiter is not None:
                        self._rate_limiter.record_throttle_event(org_id, retry_after)
                    delay = retry_after if retry_after is not None else min(2**attempt, 60)
                    await asyncio.sleep(_apply_jitter(delay, 0.2))
                    attempt += 1
                    continue

                # SDK endpoint methods return decoded payloads rather than the
                # response object. A successful SDK return is therefore the
                # bounded HTTP-success status used by the established readiness
                # consumer, while failures retain their concrete status.
                self._record_attempt(operation, "200")
                return result

    def _record_attempt(self, operation: str, status: str) -> None:
        """Record both the new detailed attempt metric and legacy counter."""
        attempts_total = type(self)._attempts_total
        assert attempts_total is not None
        attempts_total.labels(operation=operation, status=status).inc()
        type(self).requests_total().labels(
            endpoint=operation,
            method="unknown",
            status_code=status,
        ).inc()


def facade_for(owner: Any) -> MerakiApiFacade:
    """Create a facade bound to a collector/service and its inherited limiter."""
    owner_vars = vars(owner)
    current = owner_vars.get("collector") or owner
    settings = None
    limiter = None
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        current_vars = vars(current)
        settings = settings or current_vars.get("settings")
        limiter = limiter or current_vars.get("rate_limiter")
        current = current_vars.get("parent")
    return MerakiApiFacade(settings=settings, rate_limiter=limiter)


def _resolve_org_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    """Extract an org ID when the SDK operation's natural first argument is one."""
    context = structlog.contextvars.get_contextvars()
    explicit = kwargs.get("org_id") or kwargs.get("organization_id") or context.get("org_id")
    if isinstance(explicit, str) and explicit:
        return explicit
    if args and isinstance(args[0], str):
        candidate = args[0]
        if candidate.startswith(("org_", "O_")) or candidate.isdigit() or len(candidate) == 18:
            return candidate
    return None


def _numeric_setting(settings: Any | None, name: str, default: float) -> float:
    """Read a numeric API setting while tolerating lightweight test doubles."""
    value = getattr(getattr(settings, "api", None), name, default)
    return float(value) if isinstance(value, int | float) else default


def _validate_generic_response(response: Any, operation: str) -> Any:
    """Normalise the SDK's exhausted-retry error shape without guessing a schema."""
    expected_type = type(response)
    if isinstance(response, dict) and isinstance(response.get("items"), list):
        expected_type = list
    validate_response_format(response, expected_type, operation)
    # Preserve wrapper metadata such as packet-capture totals. Individual
    # fetchers still own their response schema and may unwrap ``items``.
    return response


def _status_from_exception(exc: Exception) -> str:
    """Return the bounded status label value for an SDK failure."""
    status = getattr(exc, "status", None)
    return str(status) if status is not None else type(exc).__name__
