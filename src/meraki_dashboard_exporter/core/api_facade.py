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

_FACADE_RETRY_BASE_SECONDS = 10.0
_FACADE_RETRY_MAX_SECONDS = 60.0
_FACADE_RETRY_JITTER_RATIO = 0.2


class FacadeRateLimitExhaustedError(RetryableAPIError):
    """Terminal 429 outcome already retried by :class:`MerakiApiFacade`."""

    facade_retry_exhausted = True


class FacadeRateLimiterUnavailableError(RuntimeError):
    """A facade owner has no configured limiter and cannot make a paced call."""


class MerakiApiFacade:
    """Stable async facade seam for synchronous Meraki SDK operations.

    It is intentionally the only component that crosses from async exporter code
    to the synchronous Dashboard SDK. Every SDK attempt acquires the owner's
    limiter. A 429 is retried at most ``max_retries`` times using a jittered
    10-second exponential backoff when Dashboard provides no Retry-After;
    supplied Retry-After values are capped by configuration before jitter.

    ``meraki_exporter_api_requests_total`` is the compatibility HTTP-attempt
    counter: its ``method`` is derived from the SDK operation name and its
    ``status_code`` label is emitted only for HTTP outcomes. The detailed
    ``meraki_exporter_api_request_attempts_total`` records every SDK attempt,
    using ``status=exception`` when no HTTP response exists. Each facade-owned
    429 retry increments ``meraki_exporter_api_retry_total`` exactly once.
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
        org_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute, pace, meter, retry, deadline-bound, and validate one SDK call."""
        deadline = _numeric_setting(self._settings, "per_fetch_deadline_seconds", 120.0)
        max_retries = int(_numeric_setting(self._settings, "max_retries", 3.0))
        retry_after_cap = _numeric_setting(self._settings, "retry_after_max_seconds", 60.0)
        resolved_org_id = _resolve_org_id(operation, args, org_id)
        attempt = 0

        async with asyncio.timeout(deadline):
            while True:
                if self._rate_limiter is None:
                    raise FacadeRateLimiterUnavailableError(
                        f"{operation} cannot run without an organization rate limiter"
                    )
                await self._rate_limiter.acquire(resolved_org_id, operation)
                try:
                    response = await asyncio.get_running_loop().run_in_executor(
                        None, functools.partial(fn, *args, **kwargs)
                    )
                    result = _validate_generic_response(response, operation)
                except Exception as exc:
                    http_status = _http_status_from_exception(exc)
                    self._record_attempt(
                        operation,
                        attempt_status=http_status or "exception",
                        http_status=http_status,
                    )
                    if not _is_rate_limit_error(exc):
                        raise
                    if attempt >= max_retries:
                        raise FacadeRateLimitExhaustedError(
                            f"{operation} exhausted facade attempts"
                        ) from exc

                    retry_after = _get_retry_after_seconds(exc)
                    if retry_after is not None:
                        retry_after = min(max(retry_after, 0.0), retry_after_cap)
                    self._rate_limiter.record_throttle_event(resolved_org_id, retry_after)
                    _record_facade_retry(operation)
                    delay = (
                        retry_after
                        if retry_after is not None
                        else min(
                            _FACADE_RETRY_BASE_SECONDS * (2**attempt),
                            _FACADE_RETRY_MAX_SECONDS,
                        )
                    )
                    await asyncio.sleep(_apply_jitter(delay, _FACADE_RETRY_JITTER_RATIO))
                    attempt += 1
                    continue

                # SDK endpoint methods return decoded payloads rather than the
                # response object. A successful SDK return is therefore the
                # bounded HTTP-success status used by the established readiness
                # consumer, while failures retain their concrete status.
                self._record_attempt(operation, attempt_status="200", http_status="200")
                return result

    def _record_attempt(
        self,
        operation: str,
        *,
        attempt_status: str,
        http_status: str | None,
    ) -> None:
        """Record both the new detailed attempt metric and legacy counter."""
        attempts_total = type(self)._attempts_total
        assert attempts_total is not None
        attempts_total.labels(operation=operation, status=attempt_status).inc()
        if http_status is not None:
            type(self).requests_total().labels(
                endpoint=operation,
                method=_http_method_from_operation(operation),
                status_code=http_status,
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


def _resolve_org_id(
    operation: str, args: tuple[Any, ...], explicit_org_id: str | None
) -> str | None:
    """Resolve a pacing key without treating an arbitrary identifier as an org ID."""
    context = structlog.contextvars.get_contextvars()
    if isinstance(explicit_org_id, str) and explicit_org_id:
        return explicit_org_id
    context_org_id = context.get("org_id")
    if isinstance(context_org_id, str) and context_org_id:
        return context_org_id
    if operation.startswith("getOrganization") and args and isinstance(args[0], str):
        return args[0]
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


def _http_status_from_exception(exc: Exception) -> str | None:
    """Return an HTTP status only when the exception supplies a valid one."""
    status = getattr(exc, "status", None)
    if not isinstance(status, int | str):
        return None
    try:
        numeric_status = int(status)
    except TypeError, ValueError:
        return None
    return str(numeric_status) if 100 <= numeric_status <= 599 else None


def _http_method_from_operation(operation: str) -> str:
    """Derive the bounded HTTP method family used by the Dashboard SDK operation."""
    verb = operation.lower()
    if verb.startswith(("get", "list")):
        return "GET"
    if verb.startswith("create"):
        return "POST"
    if verb.startswith(("update", "set")):
        return "PUT"
    if verb.startswith("delete"):
        return "DELETE"
    return "UNKNOWN"


def _record_facade_retry(operation: str) -> None:
    """Increment the API-client compatibility retry counter without an import cycle."""
    from ..api.client import AsyncMerakiClient

    AsyncMerakiClient.record_retry_attempt(operation, "http_429_rate_limit")
