"""Meraki API client wrapper with async support and comprehensive observability."""
# mypy: disable-error-code="no-any-return"

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, TypeVar

import meraki
from meraki.exceptions import APIError
from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram

from ..core.constants.metrics_constants import CollectorMetricName
from ..core.logging import get_logger
from ..core.metrics import LabelName

if TYPE_CHECKING:
    from ..core.config import Settings

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

T = TypeVar("T")


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
    # Class-level metrics (shared across all instances)
    _api_request_duration: Histogram | None = None
    _api_requests_total: Counter | None = None
    _api_rate_limit_remaining: Gauge | None = None
    _api_rate_limit_total: Gauge | None = None
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
        """Initialize API client metrics for comprehensive observability.

        Uses class-level metrics to prevent duplicate registration when
        multiple AsyncMerakiClient instances are created.
        """
        # Only initialize metrics once at class level to prevent duplicates
        if not AsyncMerakiClient._metrics_initialized:
            # Request duration histogram
            AsyncMerakiClient._api_request_duration = Histogram(
                CollectorMetricName.API_REQUEST_DURATION_SECONDS.value,
                "Duration of Meraki API requests in seconds",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.METHOD.value,
                    LabelName.STATUS_CODE.value,
                ],
                buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
            )

            # Request counter
            AsyncMerakiClient._api_requests_total = Counter(
                CollectorMetricName.API_REQUESTS_TOTAL.value,
                "Total number of Meraki API requests",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.METHOD.value,
                    LabelName.STATUS_CODE.value,
                ],
            )

            # Rate limit gauges
            AsyncMerakiClient._api_rate_limit_remaining = Gauge(
                CollectorMetricName.API_RATE_LIMIT_REMAINING.value,
                "Remaining rate limit for Meraki API",
                labelnames=[LabelName.ORG_ID.value],
            )

            AsyncMerakiClient._api_rate_limit_total = Gauge(
                CollectorMetricName.API_RATE_LIMIT_TOTAL.value,
                "Total rate limit for Meraki API",
                labelnames=[LabelName.ORG_ID.value],
            )

            # Retry counter
            AsyncMerakiClient._api_retry_attempts = Counter(
                CollectorMetricName.API_RETRY_ATTEMPTS_TOTAL.value,
                "Total number of API retry attempts",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.RETRY_REASON.value,
                ],
            )

            AsyncMerakiClient._metrics_initialized = True
            logger.debug("Initialized AsyncMerakiClient metrics")
        else:
            logger.debug("Reusing existing AsyncMerakiClient metrics")

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
        )

    @property
    def api(self) -> meraki.DashboardAPI:
        """Get the API client instance (synchronous property for compatibility).

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

    async def _request(
        self,
        endpoint_name: str,
        api_func: Callable[..., T],
        *args: Any,
        max_retries: int | None = None,
        span_name: str | None = None,
        result_hook: Callable[[T, Any], None] | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute an API request with retry logic, metrics, and observability.

        Parameters
        ----------
        endpoint_name : str
            Name of the API endpoint (for metrics and logging).
        api_func : Callable[..., T]
            The API function to call.
        *args : Any
            Positional arguments for the API function.
        max_retries : int | None
            Maximum retry attempts (defaults to settings.api.max_retries).
        span_name : str | None
            Optional tracing span name (defaults to endpoint_name).
        result_hook : Callable[[T, Any], None] | None
            Optional callback invoked on successful responses for span enrichment.
        **kwargs : Any
            Keyword arguments for the API function.

        Returns
        -------
        T
            The API response.

        Raises
        ------
        APIError
            If the API call fails after all retries.

        """
        if max_retries is None:
            max_retries = self.settings.api.max_retries

        # Ensure API client is initialized
        await self._get_api_client()

        # Metrics are initialized in __init__, but assert for type safety
        assert self._api_request_duration is not None
        assert self._api_requests_total is not None
        assert self._api_retry_attempts is not None
        api_request_duration = self._api_request_duration
        api_requests_total = self._api_requests_total
        api_retry_attempts = self._api_retry_attempts

        retry_count = 0
        last_error: Exception | None = None

        span_name = span_name or endpoint_name

        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("api.endpoint", endpoint_name)
            span.set_attribute("api.max_retries", max_retries)

            while retry_count <= max_retries:
                start_time = time.time()
                status_code = "unknown"

                try:
                    # Execute API call with semaphore
                    async with self._semaphore:
                        result = await asyncio.to_thread(api_func, *args, **kwargs)

                    # Success - record metrics
                    duration = time.time() - start_time
                    status_code = "200"

                    api_request_duration.labels(
                        endpoint=endpoint_name,
                        method="GET",  # Most Meraki API calls are GET
                        status_code=status_code,
                    ).observe(duration)

                    api_requests_total.labels(
                        endpoint=endpoint_name,
                        method="GET",
                        status_code=status_code,
                    ).inc()

                    span.set_attribute("api.status_code", status_code)
                    span.set_attribute("api.duration_seconds", duration)
                    span.set_attribute("api.retry_count", retry_count)

                    if result_hook:
                        result_hook(result, span)

                    logger.debug(
                        "API request successful",
                        endpoint=endpoint_name,
                        duration_seconds=f"{duration:.3f}",
                        retry_count=retry_count,
                    )

                    return result

                except APIError as e:
                    duration = time.time() - start_time
                    status_code = str(e.status) if e.status else "unknown"
                    last_error = e

                    # Record metrics for failed request
                    api_request_duration.labels(
                        endpoint=endpoint_name,
                        method="GET",
                        status_code=status_code,
                    ).observe(duration)

                    api_requests_total.labels(
                        endpoint=endpoint_name,
                        method="GET",
                        status_code=status_code,
                    ).inc()

                    span.set_attribute("api.status_code", status_code)
                    span.set_attribute("api.error", str(e))

                    # Handle rate limit (429) with retry
                    if e.status == 429 and retry_count < max_retries:
                        retry_count += 1
                        wait_time = min(
                            self.settings.api.rate_limit_retry_wait * (2**retry_count),
                            60,  # Max 60 seconds
                        )

                        api_retry_attempts.labels(
                            endpoint=endpoint_name,
                            retry_reason="rate_limit",
                        ).inc()

                        logger.warning(
                            "Rate limit hit, retrying",
                            endpoint=endpoint_name,
                            retry_count=retry_count,
                            max_retries=max_retries,
                            wait_seconds=wait_time,
                            status=e.status,
                        )

                        span.add_event(
                            "rate_limit_retry",
                            attributes={
                                "retry_count": retry_count,
                                "wait_seconds": wait_time,
                            },
                        )

                        await asyncio.sleep(wait_time)
                        continue

                    # Don't retry other errors
                    logger.error(
                        "API request failed",
                        endpoint=endpoint_name,
                        status=e.status,
                        reason=e.reason,
                        error=str(e),
                        retry_count=retry_count,
                    )
                    raise

                except Exception as e:
                    duration = time.time() - start_time
                    last_error = e

                    # Record metrics for unexpected error
                    api_request_duration.labels(
                        endpoint=endpoint_name,
                        method="GET",
                        status_code="error",
                    ).observe(duration)

                    api_requests_total.labels(
                        endpoint=endpoint_name,
                        method="GET",
                        status_code="error",
                    ).inc()

                    span.set_attribute("api.error", str(e))
                    span.set_attribute("api.error_type", type(e).__name__)

                    logger.error(
                        "Unexpected error during API call",
                        endpoint=endpoint_name,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

            # If we get here, we've exhausted all retries
            if last_error:
                logger.error(
                    "API request failed after all retries",
                    endpoint=endpoint_name,
                    retry_count=retry_count,
                    max_retries=max_retries,
                )
                raise last_error

            # Should never reach here
            raise RuntimeError(f"API request failed for {endpoint_name}")

    async def get_organizations(self) -> list[dict[str, Any]]:
        """Fetch all accessible organizations.

        Returns
        -------
        list[dict[str, Any]]
            List of organization data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganizations",
            api_client.organizations.getOrganizations,
            span_name="get_organizations",
            result_hook=lambda orgs, span: span.set_attribute("org.count", len(orgs)),
        )
        logger.debug("Successfully fetched organizations", count=len(result))
        return result

    async def get_organization(self, org_id: str) -> dict[str, Any]:
        """Fetch a specific organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any]
            Organization data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganization",
            api_client.organizations.getOrganization,
            org_id,
        )
        logger.debug(
            "Successfully fetched organization",
            org_id=org_id,
            org_name=result.get("name", "unknown"),
        )
        return result

    async def get_networks(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch all networks in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of network data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganizationNetworks",
            api_client.organizations.getOrganizationNetworks,
            org_id,
            total_pages="all",
        )
        logger.debug("Successfully fetched networks", org_id=org_id, count=len(result))
        return result

    async def get_devices(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch all devices in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of device data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganizationDevices",
            api_client.organizations.getOrganizationDevices,
            org_id,
            total_pages="all",
        )
        logger.debug("Successfully fetched devices", org_id=org_id, count=len(result))
        return result

    async def get_device_availabilities(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch device availabilities for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of device availability data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganizationDevicesAvailabilities",
            api_client.organizations.getOrganizationDevicesAvailabilities,
            org_id,
            total_pages="all",
        )
        logger.debug("Successfully fetched device availabilities", org_id=org_id, count=len(result))
        return result

    async def get_licenses(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch license information for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of license data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganizationLicenses",
            api_client.organizations.getOrganizationLicenses,
            org_id,
            total_pages="all",
        )
        logger.debug("Successfully fetched licenses", org_id=org_id, count=len(result))
        return result

    async def get_api_requests(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch API request statistics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            API request statistics.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getOrganizationApiRequests",
            api_client.organizations.getOrganizationApiRequests,
            org_id,
            total_pages="all",
        )
        logger.debug(
            "Successfully fetched API request statistics", org_id=org_id, count=len(result)
        )
        return result

    async def get_switch_port_statuses(self, serial: str) -> list[dict[str, Any]]:
        """Fetch switch port statuses.

        Parameters
        ----------
        serial : str
            Device serial number.

        Returns
        -------
        list[dict[str, Any]]
            List of port status data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getDeviceSwitchPortsStatuses",
            api_client.switch.getDeviceSwitchPortsStatuses,
            serial,
        )
        logger.debug("Successfully fetched switch port statuses", serial=serial, count=len(result))
        return result

    async def get_wireless_status(self, serial: str) -> dict[str, Any]:
        """Fetch wireless device status.

        Parameters
        ----------
        serial : str
            Device serial number.

        Returns
        -------
        dict[str, Any]
            Wireless status data.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getDeviceWirelessStatus",
            api_client.wireless.getDeviceWirelessStatus,
            serial,
        )
        logger.debug(
            "Successfully fetched wireless status",
            serial=serial,
            ssid_count=len(result.get("basicServiceSets", [])),
        )
        return result

    async def get_sensor_readings_latest(
        self, org_id: str, serials: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch latest sensor readings for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        serials : list[str] | None
            Optional list of device serial numbers to filter by.

        Returns
        -------
        list[dict[str, Any]]
            List of sensor reading data.

        """
        api_client = await self._get_api_client()
        kwargs: dict[str, Any] = {"total_pages": "all"}
        if serials:
            kwargs["serials"] = serials

        result = await self._request(
            "getOrganizationSensorReadingsLatest",
            api_client.sensor.getOrganizationSensorReadingsLatest,
            org_id,
            **kwargs,
        )
        logger.debug(
            "Successfully fetched sensor readings",
            org_id=org_id,
            sensor_count=len(result),
            total_readings=sum(len(s.get("readings", [])) for s in result),
        )
        return result

    async def get_organization_networks(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch networks for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of networks.

        """
        return await self.get_networks(org_id)

    async def get_network_devices(self, network_id: str) -> list[dict[str, Any]]:
        """Fetch devices for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]]
            List of devices.

        """
        api_client = await self._get_api_client()
        result = await self._request(
            "getNetworkDevices",
            api_client.networks.getNetworkDevices,
            network_id,
        )
        logger.debug("Successfully fetched devices", network_id=network_id, count=len(result))
        return result

    async def get_organization_devices(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch all devices for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of devices.

        """
        return await self.get_devices(org_id)

    async def close(self) -> None:
        """Close the API client."""
        logger.debug("Closing AsyncMerakiClient")
        async with self._api_lock:
            self._api = None

    @asynccontextmanager
    async def api_call_context(self) -> AsyncIterator[None]:
        """Context manager for API calls with error handling (legacy compatibility).

        Yields
        ------
        None
            Yields control to the caller.

        """
        try:
            yield
        except APIError as e:
            # Log at appropriate level based on status code
            if e.status == 429:
                logger.warning(
                    "Meraki API rate limit hit",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            elif e.status and 400 <= e.status < 500:
                logger.error(
                    "Meraki API client error",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            elif e.status and e.status >= 500:
                logger.error(
                    "Meraki API server error",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            else:
                logger.error(
                    "Meraki API error",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            raise
        except Exception as e:
            logger.error("Unexpected error during API call", error=str(e))
            raise
