"""Meraki API client wrapper with async support and comprehensive observability."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import MethodType
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

import httpx
import meraki
from prometheus_client import Counter

from ..core.api_facade import MerakiApiFacade
from ..core.async_utils import shutdown_executor
from ..core.constants.metrics_constants import CollectorMetricName
from ..core.logging import get_logger
from ..core.metrics import LabelName

if TYPE_CHECKING:
    from ..core.config import Settings

logger = get_logger(__name__)


def _install_redirect_auth_boundary(api: Any) -> None:
    """Strip Bearer credentials from every SDK request off the configured origin.

    The Meraki SDK follows redirects manually and intentionally uses one
    persistent ``httpx.Client``.  Its default Authorization header would
    otherwise be merged into a cross-origin follow-up request.  Building the
    request explicitly lets us remove that one header without mutating the
    shared client (which is important when concurrent collector workers are
    still making same-origin requests).
    """
    session = api._session
    base_url = getattr(session, "_base_url", None)
    if not isinstance(base_url, str):
        return
    configured_origin = _origin(base_url)
    original_send = session._send_request

    def send_with_auth_boundary(self: Any, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if _origin(url) == configured_origin:
            return cast(httpx.Response, original_send(method, url, **kwargs))

        request = self._client.build_request(method, url, **kwargs)
        request.headers.pop("Authorization", None)
        return cast(httpx.Response, self._client.send(request, follow_redirects=False))

    session._send_request = MethodType(send_with_auth_boundary, session)


def _origin(url: str) -> tuple[str, str, int | None]:
    """Return the scheme/host/port security origin for a URL."""
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return (scheme, (parsed.hostname or "").lower(), port)


class AsyncMerakiClient:
    """Async wrapper for the Meraki Dashboard API client with comprehensive observability.

    Provides:
    - A dedicated, bounded thread pool for blocking SDK calls (#544), installed
      by app.py as the event loop's default executor so ``asyncio.to_thread``
      SDK call sites run on it, isolated from /metrics serving work
    - SDK 429 retries disabled (#545) - ``core/error_handling.py`` is the
      single rate-limit retry owner (bounded, event-loop, cancellable waits)
    - Comprehensive metrics (requests, errors, retries)
    - Thread-safe API client initialization

    Parameters
    ----------
    settings : Settings
        Application settings containing API configuration.

    """

    # Class-level flag to prevent duplicate metric registration
    _metrics_initialized = False
    _metrics_lock = threading.Lock()
    # Class-level metrics (shared across all instances).
    # _api_requests_total is incremented by MerakiApiFacade for every routed
    # SDK attempt; _api_retry_attempts remains the collector retry metric.
    _api_requests_total: Counter | None = None
    _api_retry_attempts: Counter | None = None
    # Last observed authentication outcome: None = unknown (no auth-signalling
    # response yet), True after any HTTP 200, False after any HTTP 401 (#509).
    _auth_ok: bool | None = None

    def __init__(self, settings: Settings) -> None:
        """Initialize the async Meraki client with settings."""
        self.settings = settings
        self._api: meraki.DashboardAPI | None = None
        self._api_lock = asyncio.Lock()
        self._closed = False
        self._executor_drained: bool | None = None
        self._api_call_count = 0

        # #544: dedicated, sized executor for synchronous SDK calls. app.py
        # installs it as the event loop's default executor so every existing
        # ``asyncio.to_thread(self.api...)`` call site runs here, while the
        # /metrics + registry-iteration work runs on its own small pool - so
        # scrapes never queue behind blocked SDK threads during a 429 storm.
        # This pool size is the real global concurrency ceiling for blocking
        # SDK calls (the per-tier concurrency_limit* knobs are bounded by it);
        # the former ``_semaphore`` (declared, never acquired) was removed.
        try:
            workers = int(getattr(settings.api, "executor_workers", 10))
        except TypeError, ValueError:
            workers = 10
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="meraki-sdk",
        )

        # Initialize API metrics
        self._init_metrics()

        logger.debug(
            "Initialized AsyncMerakiClient with observability",
            concurrency_limit=settings.api.concurrency_limit,
            executor_workers=workers,
            api_timeout=settings.api.timeout,
            max_retries=settings.api.max_retries,
        )

    @property
    def executor(self) -> ThreadPoolExecutor:
        """The dedicated thread pool for blocking Meraki SDK calls (#544)."""
        return self._executor

    def _init_metrics(self) -> None:
        """Initialize API client metrics for comprehensive observability."""
        self._ensure_metrics_initialized()

    @classmethod
    def _ensure_metrics_initialized(cls) -> None:
        """Initialize API client metrics once in a thread-safe manner."""
        if cls._metrics_initialized:
            return

        with cls._metrics_lock:
            if cls._metrics_initialized:
                return

            # NB: no api_duration_seconds histogram (F-077). It was observed only inside
            # the now-removed AsyncMerakiClient._request, which no code path called
            # (collectors use the raw SDK via asyncio.to_thread), so it exported an empty
            # histogram. Removed rather than left dead.

            # The facade owns every outbound attempt.  Keep this class attribute
            # as the compatibility surface used by status/readiness consumers.
            cls._api_requests_total = MerakiApiFacade.requests_total()

            # NB: no api_rate_limit_remaining/_total gauges (F-073). They were
            # registered but never set by any code path (the only place that could
            # populate them from response headers was the dead AsyncMerakiClient._request,
            # see F-077), so they only ever exported zero samples. Removed rather than
            # left as permanently-empty series. (Dashboards referencing them are left for
            # the dedicated dashboard task.)

            # Retry counter
            cls._api_retry_attempts = Counter(
                CollectorMetricName.API_RETRY_ATTEMPTS_TOTAL.value,
                "Total number of API retry attempts",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.RETRY_REASON.value,
                ],
            )

            cls._metrics_initialized = True
            logger.debug("Initialized AsyncMerakiClient metrics")

    async def _get_api_client(self) -> meraki.DashboardAPI:
        """Get or create the API client instance with thread-safe initialization.

        Returns
        -------
        meraki.DashboardAPI
            The Meraki Dashboard API client.

        """
        if self._api is None:
            async with self._api_lock:
                # Double-check after acquiring lock
                if self._api is None:
                    logger.debug(
                        "Creating new Meraki Dashboard API client",
                        base_url=self.settings.meraki.api_base_url,
                        timeout=self.settings.api.timeout,
                        max_retries=self.settings.api.max_retries,
                    )
                    # Create API client in thread to avoid blocking
                    self._api = await asyncio.to_thread(
                        self._create_api_client,
                    )
        return self._api

    def _create_api_client(self) -> meraki.DashboardAPI:
        """Create the Meraki API client (synchronous operation).

        Returns
        -------
        meraki.DashboardAPI
            Newly created API client instance.

        """
        api = meraki.DashboardAPI(
            api_key=self.settings.meraki.api_key.get_secret_value(),
            base_url=self.settings.meraki.api_base_url,
            output_log=False,
            # #633: the exporter's own decorators (@log_api_call /
            # @with_error_handling) are the single authoritative logging layer -
            # they categorize every API error (benign 404 -> debug, real ->
            # error) with structured context. The SDK's RestSession logs every
            # non-retried 4xx at ERROR independently, double-logging benign
            # "no data for this entity" 404s (e.g. mesh statuses on a network
            # with no repeaters). Since retries are owned by the exporter
            # (wait_on_rate_limit=False, retry_4xx_error=False), the SDK's
            # console logging is pure duplication - suppress it fleet-wide.
            suppress_logging=True,
            inherit_logging_config=True,
            single_request_timeout=self.settings.api.timeout,
            maximum_retries=self.settings.api.max_retries,
            action_batch_retry_wait_time=self.settings.api.action_batch_retry_wait,
            nginx_429_retry_wait_time=self.settings.api.rate_limit_retry_wait,
            # #545/#698: single 429 retry owner. With wait_on_rate_limit=False the
            # SDK raises APIError immediately on a 429 (verified against
            # meraki 3.3.0 RestSession.request: the Retry-After branch is only
            # entered when _wait_on_rate_limit is truthy) instead of sleeping
            # int(Retry-After) UNBOUNDED inside the worker thread up to
            # maximum_retries times. MerakiApiFacade owns all 429 retries:
            # bounded (retry_after_max_seconds), on the
            # event loop, cancellable. maximum_retries still governs the SDK's
            # short (1s) connection-error/5xx/JSON-decode retries.
            wait_on_rate_limit=False,
            retry_4xx_error=False,  # Don't retry 4xx errors
            caller="merakidashboardexporter rknightion",
            validate_kwargs=self.settings.api.validate_kwargs,
            # #698: exporter-owned OrgRateLimiter is the only request pacer.
            # This also prevents the SDK from persisting smart-flow state below
            # $HOME, which is unsafe for read-only containers.
            smart_flow_enabled=False,
            # #586: first-class proxy + custom-CA support. Both are forwarded
            # verbatim; the SDK guards each with a truthiness check
            # (``if self._requests_proxy:`` / ``if self._certificate_path:``),
            # so a None/empty value is ignored and the underlying ``requests``
            # session still honours the HTTPS_PROXY/NO_PROXY env-var fallback.
            requests_proxy=self.settings.api.requests_proxy,
            certificate_path=self.settings.api.certificate_path,
        )
        _install_redirect_auth_boundary(api)
        return api

    @property
    def api(self) -> meraki.DashboardAPI:
        """The API client instance (synchronous property for compatibility).

        Returns
        -------
        meraki.DashboardAPI
            The Meraki Dashboard API client.

        """
        if self._api is None:
            # Synchronous fallback for compatibility
            logger.debug("Creating API client synchronously (fallback)")
            self._api = self._create_api_client()
        return self._api

    def get_total_api_requests(self) -> int:
        """Return the total number of Meraki API requests recorded so far.

        Sums the shared ``_api_requests_total`` counter (incremented by
        ``MerakiApiFacade``) across every
        endpoint/method/status_code label combination. This is the real request
        count surfaced on ``/status`` (F-028/F-074); the legacy
        ``_api_call_count`` attribute was initialised to 0 and never incremented.

        Returns
        -------
        int
            Total requests across all label combinations, or 0 if the counter
            has not been initialised yet.

        """
        counter = type(self)._api_requests_total
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

    @classmethod
    def record_auth_outcome(cls, ok: bool) -> None:
        """Record the auth outcome of an API response (200 → True, 401 → False)."""
        cls._auth_ok = ok

    @classmethod
    def get_auth_ok(cls) -> bool | None:
        """Last observed authentication state (None until a 200 or 401 is seen)."""
        return cls._auth_ok

    @classmethod
    def reset_auth_state(cls) -> None:
        """Reset recorded auth state (test isolation helper)."""
        cls._auth_ok = None

    def get_successful_api_requests(self) -> int:
        """Total Meraki API requests that returned HTTP 200 (readiness gate, #509)."""
        counter = type(self)._api_requests_total
        if counter is None:
            return 0
        total = 0.0
        for metric in counter.collect():
            for sample in metric.samples:
                if sample.name.endswith("_created"):
                    continue
                if sample.labels.get(LabelName.STATUS_CODE.value) == "200":
                    total += sample.value
        return int(total)

    async def close(self, *, timeout_seconds: float = 5.0) -> bool:
        """Close the API client and shut down the dedicated SDK executor.

        Terminal: queued SDK futures are cancelled and running SDK work is
        joined off the event loop. The SDK's private HTTP session closes only
        after those workers drain. If the deadline expires, the coordinator
        continues that cleanup in the background while process shutdown moves on.
        """
        logger.debug("Closing AsyncMerakiClient")
        async with self._api_lock:
            if self._closed:
                return bool(self._executor_drained)
            self._closed = True
            api = self._api
            self._api = None

            session = getattr(api, "_session", None)

            def close_session() -> None:
                if session is not None:
                    session.close()
                    logger.info("Shutdown phase complete", phase="sdk_session_closed")

            self._executor_drained = await shutdown_executor(
                self._executor,
                timeout_seconds=timeout_seconds,
                thread_name="meraki-sdk-shutdown",
                on_drained=close_session,
            )
            if self._executor_drained:
                logger.info("Shutdown phase complete", phase="sdk_executor_drained")
            else:
                logger.warning(
                    "SDK executor did not drain before shutdown deadline; cleanup continues",
                    timeout_seconds=timeout_seconds,
                )
            return self._executor_drained
