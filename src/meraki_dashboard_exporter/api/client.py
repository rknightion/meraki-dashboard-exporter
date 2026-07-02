"""Meraki API client wrapper with async support and comprehensive observability."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import meraki
from prometheus_client import Counter

from ..core.constants.metrics_constants import CollectorMetricName
from ..core.logging import get_logger
from ..core.metrics import LabelName

if TYPE_CHECKING:
    from ..core.config import Settings

logger = get_logger(__name__)


class AsyncMerakiClient:
    """Async wrapper for the Meraki Dashboard API client with comprehensive observability.

    Provides:
    - Async API calls with semaphore-based concurrency control
    - Automatic retry with exponential backoff on rate limits (429)
    - Comprehensive metrics (latency, errors, rate limits)
    - OTEL tracing with detailed span attributes
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
    # _api_requests_total is incremented by services/inventory.py::_make_api_call;
    # _api_retry_attempts by core/collector.py::_track_retry on rate-limit retries.
    _api_requests_total: Counter | None = None
    _api_retry_attempts: Counter | None = None

    def __init__(self, settings: Settings) -> None:
        """Initialize the async Meraki client with settings."""
        self.settings = settings
        self._api: meraki.DashboardAPI | None = None
        self._semaphore = asyncio.Semaphore(settings.api.concurrency_limit)
        self._api_lock = asyncio.Lock()
        self._api_call_count = 0

        # Initialize API metrics
        self._init_metrics()

        logger.debug(
            "Initialized AsyncMerakiClient with observability",
            concurrency_limit=settings.api.concurrency_limit,
            api_timeout=settings.api.timeout,
            max_retries=settings.api.max_retries,
        )

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

            # Request counter
            cls._api_requests_total = Counter(
                CollectorMetricName.API_REQUESTS_TOTAL.value,
                "Total number of outbound Meraki API requests made by THIS exporter process "
                "(monotonic counter), labeled by endpoint/method/status_code",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.METHOD.value,
                    LabelName.STATUS_CODE.value,
                ],
            )

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
        return meraki.DashboardAPI(
            api_key=self.settings.meraki.api_key.get_secret_value(),
            base_url=self.settings.meraki.api_base_url,
            output_log=False,
            suppress_logging=False,
            inherit_logging_config=True,
            single_request_timeout=self.settings.api.timeout,
            maximum_retries=self.settings.api.max_retries,
            action_batch_retry_wait_time=self.settings.api.action_batch_retry_wait,
            nginx_429_retry_wait_time=self.settings.api.rate_limit_retry_wait,
            wait_on_rate_limit=True,
            retry_4xx_error=False,  # Don't retry 4xx errors
            caller="merakidashboardexporter rknightion",
            validate_kwargs=self.settings.api.validate_kwargs,
        )

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
        ``services/inventory.py::_make_api_call``) across every
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

    async def close(self) -> None:
        """Close the API client."""
        logger.debug("Closing AsyncMerakiClient")
        async with self._api_lock:
            self._api = None
