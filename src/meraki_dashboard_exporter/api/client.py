"""Meraki API client wrapper with async support."""
# mypy: disable-error-code="no-any-return"

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import meraki
from meraki.exceptions import APIError
from opentelemetry import trace

from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..core.config import Settings

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class AsyncMerakiClient:
    """Async wrapper for the Meraki Dashboard API client.

    Parameters
    ----------
    settings : Settings
        Application settings containing API configuration.

    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the async Meraki client with settings."""
        self.settings = settings
        self._api: meraki.DashboardAPI | None = None
        self._semaphore = asyncio.Semaphore(settings.api.concurrency_limit)
        self._api_lock = asyncio.Lock()  # Add lock for API client creation
        self._api_call_count = 0
        logger.debug(
            "Initialized AsyncMerakiClient",
            concurrency_limit=settings.api.concurrency_limit,
            api_timeout=settings.api.timeout,
            max_retries=settings.api.max_retries,
        )

    @property
    def api(self) -> meraki.DashboardAPI:
        """Get or create the API client instance.

        Returns
        -------
        meraki.DashboardAPI
            The Meraki Dashboard API client.

        """
        if self._api is None:
            logger.debug(
                "Creating new Meraki Dashboard API client",
                base_url=self.settings.meraki.api_base_url,
                timeout=self.settings.api.timeout,
                max_retries=self.settings.api.max_retries,
            )
            self._api = meraki.DashboardAPI(
                api_key=self.settings.meraki.api_key.get_secret_value(),
                base_url=self.settings.meraki.api_base_url,
                output_log=False,
                suppress_logging=False,
                inherit_logging_config=True,
                single_request_timeout=self.settings.api.timeout,
                maximum_retries=self.settings.api.max_retries,
                action_batch_retry_wait_time=10,
                nginx_429_retry_wait_time=5,
                wait_on_rate_limit=True,
                retry_4xx_error=False,  # Don't retry 4xx errors
                caller="merakidashboardexporter rknightion",
            )
        return self._api

    async def get_organizations(self) -> list[dict[str, Any]]:
        """Fetch all accessible organizations.

        Returns
        -------
        list[dict[str, Any]]
            List of organization data.

        """
        with tracer.start_as_current_span("get_organizations") as span:
            logger.debug("Fetching all organizations")
            span.set_attribute("api.endpoint", "getOrganizations")

            async with self._semaphore:
                result = await asyncio.to_thread(self.api.organizations.getOrganizations)

            logger.debug("Successfully fetched organizations", count=len(result))
            span.set_attribute("org.count", len(result))
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
        logger.debug("Fetching organization", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(self.api.organizations.getOrganization, org_id)
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
        logger.debug("Fetching networks", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
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
        logger.debug("Fetching devices", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
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
        logger.debug("Fetching device availabilities", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesAvailabilities,
                org_id,
                total_pages="all",
            )
            logger.debug(
                "Successfully fetched device availabilities", org_id=org_id, count=len(result)
            )
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
        logger.debug("Fetching licenses", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationLicenses,
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
        logger.debug("Fetching API request statistics", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationApiRequests,
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
        logger.debug("Fetching switch port statuses", serial=serial)
        async with self._semaphore:
            result = await asyncio.to_thread(self.api.switch.getDeviceSwitchPortsStatuses, serial)
            logger.debug(
                "Successfully fetched switch port statuses", serial=serial, count=len(result)
            )
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
        logger.debug("Fetching wireless device status", serial=serial)
        async with self._semaphore:
            result = await asyncio.to_thread(self.api.wireless.getDeviceWirelessStatus, serial)
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
        logger.debug(
            "Fetching latest sensor readings",
            org_id=org_id,
            serial_filter_count=len(serials) if serials else 0,
        )
        async with self._semaphore:
            kwargs: dict[str, Any] = {"total_pages": "all"}
            if serials:
                kwargs["serials"] = serials
            result = await asyncio.to_thread(
                self.api.sensor.getOrganizationSensorReadingsLatest,
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
        logger.debug("Fetching organization networks", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            logger.debug("Successfully fetched networks", org_id=org_id, count=len(result))
            return result

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
        logger.debug("Fetching network devices", network_id=network_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.networks.getNetworkDevices,
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
        logger.debug("Fetching organization devices", org_id=org_id)
        async with self._semaphore:
            result = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
            )
            logger.debug("Successfully fetched devices", org_id=org_id, count=len(result))
            return result

    async def close(self) -> None:
        """Close the API client."""
        # The Meraki client doesn't have an explicit close method
        logger.debug("Closing AsyncMerakiClient")
        self._api = None

    @asynccontextmanager
    async def api_call_context(self) -> AsyncIterator[None]:
        """Context manager for API calls with error handling.

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
                # Rate limit - this is handled by the SDK but log it
                logger.warning(
                    "Meraki API rate limit hit",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            elif e.status and 400 <= e.status < 500:
                # Client errors - these are usually our fault
                logger.error(
                    "Meraki API client error",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            elif e.status and e.status >= 500:
                # Server errors - these are Meraki's fault
                logger.error(
                    "Meraki API server error",
                    status=e.status,
                    reason=e.reason,
                    message=str(e),
                )
            else:
                # Other errors
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
