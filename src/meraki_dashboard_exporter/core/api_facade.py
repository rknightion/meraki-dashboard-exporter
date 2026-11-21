"""Single entry point for outbound Meraki SDK operations."""

from __future__ import annotations

import asyncio
import copy
import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
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
    limiter, and a paginated fetch is driven here page by page, so each page is
    one paced, counted and individually retried attempt. A 429 is retried at
    most ``max_retries`` times (per page for a paginated fetch) using a jittered
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
                "Total outbound Meraki API request attempts by operation and outcome, "
                "one per page of a paginated fetch.",
                labelnames=[LabelName.OPERATION.value, LabelName.STATUS.value],
            )
        if cls._requests_total is None:
            cls._requests_total = Counter(
                CollectorMetricName.API_REQUESTS_TOTAL.value,
                "Total outbound Meraki API request attempts made by this exporter process, "
                "one per page of a paginated fetch.",
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
        """Execute, pace, meter, retry, deadline-bound, and validate one SDK call.

        A Dashboard SDK list method called with ``total_pages`` other than 1 is a
        paginated fetch. The facade drives its pages itself, one executor hop per
        page, so every page takes one limiter token, records one attempt and
        retries a 429 on its own while the pages already fetched are kept. The
        deadline still bounds the whole logical fetch, and no worker thread is
        left paging after it expires.
        """
        deadline = _numeric_setting(self._settings, "per_fetch_deadline_seconds", 120.0)
        resolved_org_id = _resolve_org_id(operation, args, org_id)

        async with asyncio.timeout(deadline):
            if self._rate_limiter is None:
                raise FacadeRateLimiterUnavailableError(
                    f"{operation} cannot run without an organization rate limiter"
                )
            plan = _capture_page_plan(fn, args, kwargs)
            if plan is None:
                return await self._paced_attempts(
                    operation,
                    resolved_org_id,
                    functools.partial(fn, *args, **kwargs),
                    validate=True,
                )
            result = await self._fetch_pages(operation, resolved_org_id, plan)
            return _validate_generic_response(result, operation)

    async def _fetch_pages(self, operation: str, org_id: str | None, plan: _PagePlan) -> Any:
        """Fetch a paginated SDK resource page by page, mirroring the SDK's merge."""
        plan.metadata["page"] = 1
        page = await self._paced_attempts(
            operation,
            org_id,
            functools.partial(
                _request_page, plan.session, plan.metadata, plan.url, params=plan.params
            ),
        )
        results = page.body
        remaining = plan.total_pages
        while remaining != 1:
            link = page.links.get(plan.direction)
            next_url = link.get("url") if isinstance(link, dict) else None
            if not next_url:
                break
            if results is None:
                break
            if not isinstance(results, list) and not _is_items_page(results):
                raise TypeError(f"{operation} returned an unpaginatable page shape")
            plan.metadata["page"] += 1
            page = await self._paced_attempts(
                operation,
                org_id,
                functools.partial(_request_page, plan.session, plan.metadata, next_url),
            )
            if page.body is None:
                break
            _merge_page(results, page.body)
            remaining -= 1
        return results

    async def _paced_attempts(
        self,
        operation: str,
        org_id: str | None,
        request: Callable[[], Any],
        *,
        validate: bool = False,
    ) -> Any:
        """Run one HTTP request (or one unpaginated SDK call) with pacing and 429 retry."""
        max_retries = int(_numeric_setting(self._settings, "max_retries", 3.0))
        retry_after_cap = _numeric_setting(self._settings, "retry_after_max_seconds", 60.0)
        limiter = self._rate_limiter
        assert limiter is not None
        attempt = 0
        while True:
            await limiter.acquire(org_id, operation)
            try:
                response = await asyncio.get_running_loop().run_in_executor(None, request)
                result = _validate_generic_response(response, operation) if validate else response
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
                limiter.record_throttle_event(org_id, retry_after)
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
            # response object, and a page request only returns on a 2xx. A
            # success is therefore the bounded HTTP-success status used by the
            # established readiness consumer, while failures retain their
            # concrete status.
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


@dataclass(frozen=True)
class _PagePlan:
    """The first request of a paginated SDK fetch, captured without any I/O."""

    session: Any
    metadata: dict[str, Any]
    url: str
    params: Any
    total_pages: int
    direction: str


@dataclass(frozen=True)
class _Page:
    """One decoded page: its JSON body (None for an empty 204) and its Link relations."""

    body: Any
    links: dict[str, Any]


class _PageCaptureAbortedError(Exception):
    """The SDK method tried to reach the session for something other than get_pages."""


class _PageCaptureSession:
    """Session stand-in that records an SDK method's ``get_pages`` arguments.

    Only the read-only attributes the generated SDK methods consult before
    dispatching (``_logger``, ``_validate_kwargs``) reach the real session;
    anything else aborts the capture so the call falls back to the plain path.
    """

    _PASSTHROUGH = frozenset({"_logger", "_validate_kwargs"})

    def __init__(self, session: Any) -> None:
        self._real_session = session

    def __getattr__(self, name: str) -> Any:
        if name in self._PASSTHROUGH:
            return getattr(self._real_session, name)
        raise _PageCaptureAbortedError(name)

    def get_pages(
        self,
        metadata: dict[str, Any],
        url: str,
        params: Any = None,
        total_pages: Any = -1,
        direction: str = "next",
        event_log_end_time: Any = None,
    ) -> _PagePlan | None:
        pages = _normalise_total_pages(total_pages)
        # getNetworkEvents pages by time with an end-time cut-off and an events
        # merge of its own; it keeps the SDK's single-call pagination.
        if (
            pages is None
            or pages == 1
            or direction not in {"next", "prev"}
            or event_log_end_time is not None
            or metadata.get("operation") == "getNetworkEvents"
        ):
            return None
        return _PagePlan(
            session=self._real_session,
            metadata=metadata,
            url=url,
            params=params,
            total_pages=pages,
            direction=direction,
        )


def _normalise_total_pages(total_pages: Any) -> int | None:
    """Apply the SDK's ``total_pages`` reading; None for a value the SDK rejects."""
    if isinstance(total_pages, str):
        if total_pages.lower() == "all":
            return -1
        return int(total_pages) if total_pages.isnumeric() else None
    if isinstance(total_pages, int) and not isinstance(total_pages, bool):
        return total_pages
    return None


def _capture_page_plan(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> _PagePlan | None:
    """Return the page plan of a paginated SDK list call, or None for any other call.

    The generated SDK method runs against a copy of its API section whose
    session only records the ``get_pages`` arguments, so the endpoint's own
    path, query and array-parameter building is reused without sending
    anything. A callable that is not such a method, a call that is not
    paginated, a session in iterator mode, or any capture error leaves the call
    on the single-hop path, which reproduces the SDK's own behaviour.
    """
    if "total_pages" not in kwargs or _normalise_total_pages(kwargs["total_pages"]) == 1:
        return None
    if not inspect.ismethod(fn):
        return None
    section: Any = fn.__self__
    session = getattr(section, "_session", None)
    if session is None or not callable(getattr(session, "request", None)):
        return None
    if getattr(session, "_use_iterator_for_get_pages", False):
        return None
    try:
        capture_section = copy.copy(section)
        capture_section._session = _PageCaptureSession(session)
        plan = fn.__func__(capture_section, *args, **kwargs)
    except Exception:
        return None
    return plan if isinstance(plan, _PagePlan) else None


def _request_page(session: Any, metadata: dict[str, Any], url: str, **kwargs: Any) -> _Page:
    """Send one page request through the SDK session and decode it (worker thread).

    The first page carries the endpoint's query parameters; later pages follow
    the server's Link URL as sent, exactly as the SDK's own page loop does.
    """
    response = session.request(metadata, "GET", url, **kwargs)
    try:
        body = None if response.status_code == 204 else response.json()
        links = dict(response.links)
    finally:
        response.close()
    return _Page(body=body, links=links)


def _is_items_page(page: Any) -> bool:
    """Return whether a page is the SDK's ``{"items": [...]}`` wrapper shape."""
    return isinstance(page, dict) and isinstance(page.get("items"), list)


def _merge_page(results: Any, page: Any) -> None:
    """Append one page to the accumulated result exactly as the SDK's page loop does."""
    if isinstance(results, list):
        results.extend(page)
        return
    results["items"].extend(page["items"])
    if "meta" in results:
        results["meta"]["counts"]["items"]["remaining"] = page["meta"]["counts"]["items"][
            "remaining"
        ]


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
