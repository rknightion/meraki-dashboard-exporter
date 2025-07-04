"""Meraki API client wrapper with async support."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import meraki
from meraki.exceptions import APIError

from ..core.constants import DEFAULT_MAX_RETRIES, DEFAULT_RATE_LIMIT_RETRY_WAIT
from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..core.config import Settings

logger = get_logger(__name__)


class AsyncMerakiClient:
    """Async wrapper for the Meraki Dashboard API client.

    Parameters
    ----------
    settings : Settings
        Application settings containing API configuration.

    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._api: meraki.DashboardAPI | None = None
        self._semaphore = asyncio.Semaphore(5)  # Rate limiting to avoid connection pool issues

    @property
    def api(self) -> meraki.DashboardAPI:
        """Get or create the API client instance.

        Returns
        -------
        meraki.DashboardAPI
            The Meraki Dashboard API client.

        """
        if self._api is None:
            self._api = meraki.DashboardAPI(
                api_key=self.settings.api_key.get_secret_value(),
                output_log=False,
                suppress_logging=True,
                single_request_timeout=self.settings.api_timeout,
                maximum_retries=DEFAULT_MAX_RETRIES,
                wait_on_rate_limit=True,
                retry_4xx_error=True,
                retry_4xx_error_wait_time=DEFAULT_RATE_LIMIT_RETRY_WAIT,
            )
        return self._api

    async def get_organizations(self) -> list[dict[str, Any]]:
        """Fetch all accessible organizations.

        Returns
        -------
        list[dict[str, Any]]
            List of organization data.

        """
        async with self._semaphore:
            return await asyncio.to_thread(self.api.organizations.getOrganizations)

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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.organizations.getOrganization, org_id
            )

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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )

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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
            )

    async def get_device_statuses(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch device statuses for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of device status data.

        """
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesStatuses,
                org_id,
                total_pages="all",
            )

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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.organizations.getOrganizationLicenses,
                org_id,
                total_pages="all",
            )

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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.organizations.getOrganizationApiRequests,
                org_id,
                total_pages="all",
            )

    async def get_switch_port_statuses(
        self, serial: str
    ) -> list[dict[str, Any]]:
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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.switch.getDeviceSwitchPortsStatuses, serial
            )

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
        async with self._semaphore:
            return await asyncio.to_thread(
                self.api.wireless.getDeviceWirelessStatus, serial
            )

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
        async with self._semaphore:
            kwargs = {"total_pages": "all"}
            if serials:
                kwargs["serials"] = serials
            return await asyncio.to_thread(
                self.api.sensor.getOrganizationSensorReadingsLatest,
                org_id,
                **kwargs,
            )

    async def close(self) -> None:
        """Close the API client."""
        # The Meraki client doesn't have an explicit close method
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
