"""Organization inventory service for caching org/network/device data.

This service provides a shared cache of organization, network, and device
inventory data to reduce redundant API calls across collectors. Implements
TTL-based cache invalidation with different TTLs per update tier.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

import structlog
from meraki.exceptions import APIError
from prometheus_client import Counter

from ..core.constants import UpdateTier
from ..core.constants.metrics_constants import CollectorMetricName
from ..core.metrics import LabelName

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ..core.config import Settings

T = TypeVar("T")

logger = structlog.get_logger(__name__)


class OrganizationInventory:
    """Shared inventory cache for organizations, networks, and devices.

    Reduces API calls by caching inventory data with TTL-based invalidation.
    Different TTLs are used based on data volatility:
    - FAST tier: 5 minutes
    - MEDIUM tier: 15 minutes
    - SLOW tier: 30 minutes

    Examples
    --------
    Basic usage in a collector:
    >>> inventory = OrganizationInventory(api, settings)
    >>> orgs = await inventory.get_organizations()
    >>> networks = await inventory.get_networks(org_id)
    >>> devices = await inventory.get_devices(org_id)

    Manual cache invalidation:
    >>> await inventory.invalidate(org_id)  # Invalidate specific org
    >>> await inventory.invalidate()  # Invalidate all

    """

    # Class-level API metrics counter (shared across instances)
    _api_requests_total: Counter | None = None

    # TTL values in seconds based on update tier
    TTL_FAST = 300  # 5 minutes
    TTL_MEDIUM = 900  # 15 minutes
    TTL_SLOW = 1800  # 30 minutes

    # Shorter TTL for availability data (more dynamic than inventory)
    TTL_AVAILABILITY = 120  # 2 minutes

    # Longer TTL for slow-changing configuration data
    TTL_LICENSE = 1800  # 30 minutes - license data rarely changes
    TTL_CONFIG = 3600  # 60 minutes - org config/security settings rarely change

    def __init__(
        self, api: DashboardAPI, settings: Settings, rate_limiter: Any | None = None
    ) -> None:
        """Initialize the inventory service.

        Parameters
        ----------
        api : DashboardAPI
            Meraki Dashboard API client.
        settings : Settings
            Application settings.
        rate_limiter : Any | None
            Optional rate limiter used to gate API calls.

        """
        self.api = api
        self.settings = settings
        self.rate_limiter = rate_limiter

        # Determine TTL based on fastest tier in use
        # Use MEDIUM tier TTL as a reasonable default
        self._ttl = self.TTL_MEDIUM

        # Cache storage
        self._organizations: list[dict[str, Any]] | None = None
        self._networks: dict[str, list[dict[str, Any]]] = {}
        self._devices: dict[str, list[dict[str, Any]]] = {}
        self._device_availabilities: dict[str, list[dict[str, Any]]] = {}
        self._licenses_overview: dict[str, dict[str, Any]] = {}
        self._login_security: dict[str, dict[str, Any]] = {}

        # Cache timestamps
        self._org_timestamp: float = 0.0
        self._network_timestamps: dict[str, float] = {}
        self._device_timestamps: dict[str, float] = {}
        self._availability_timestamps: dict[str, float] = {}
        self._license_timestamps: dict[str, float] = {}
        self._security_timestamps: dict[str, float] = {}

        # Lock for thread-safe cache updates
        self._lock = asyncio.Lock()

        # Metrics
        self._cache_hits = 0
        self._cache_misses = 0

        logger.info(
            "Initialized organization inventory cache",
            ttl_seconds=self._ttl,
        )

    async def _acquire_rate_limit(self, org_id: str | None, endpoint: str) -> None:
        if self.rate_limiter is None:
            return
        await self.rate_limiter.acquire(org_id, endpoint)

    @classmethod
    def _get_api_metrics(cls) -> Counter:
        """Get or create the API requests counter.

        Uses the same metric name as AsyncMerakiClient so all API calls are
        tracked in a single counter regardless of which component makes them.
        """
        if not hasattr(cls, "_api_requests_total") or cls._api_requests_total is None:
            cls._api_requests_total = Counter(
                CollectorMetricName.API_REQUESTS_TOTAL.value,
                "Total number of Meraki API requests",
                labelnames=[
                    LabelName.ENDPOINT.value,
                    LabelName.METHOD.value,
                    LabelName.STATUS_CODE.value,
                ],
            )
        return cls._api_requests_total

    async def _make_api_call(
        self,
        endpoint: str,
        api_func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Make an API call with metric instrumentation.

        Parameters
        ----------
        endpoint : str
            The API endpoint name for metric labeling.
        api_func : Callable
            The API function to call.
        *args : Any
            Positional arguments to pass to the API function.
        **kwargs : Any
            Keyword arguments to pass to the API function.

        Returns
        -------
        T
            The result from the API call.

        Raises
        ------
        APIError
            Re-raised from the Meraki SDK with metric recorded.
        Exception
            Any other exception with metric recorded as "error".

        """
        counter = self._get_api_metrics()
        try:
            result = await asyncio.to_thread(api_func, *args, **kwargs)
            counter.labels(endpoint=endpoint, method="GET", status_code="200").inc()
            return result
        except APIError as e:
            counter.labels(
                endpoint=endpoint, method="GET", status_code=str(e.status)
            ).inc()
            raise
        except Exception:
            counter.labels(endpoint=endpoint, method="GET", status_code="error").inc()
            raise

    async def get_organizations(
        self,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Get organizations with caching.

        Parameters
        ----------
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        list[dict[str, Any]]
            List of organization data.

        """
        current_time = time.time()

        # Check cache validity
        if (
            not force_refresh
            and self._organizations is not None
            and (current_time - self._org_timestamp) < self._ttl
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for organizations",
                cache_age_seconds=current_time - self._org_timestamp,
            )
            return self._organizations

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for organizations, fetching from API")

        async with self._lock:
            # Double-check after acquiring lock
            if (
                not force_refresh
                and self._organizations is not None
                and (current_time - self._org_timestamp) < self._ttl
            ):
                return self._organizations

            # Fetch from API
            if self.settings.meraki.org_id:
                # Single org mode
                org_id = self.settings.meraki.org_id
                organizations = [
                    {
                        "id": org_id,
                        # Use org_id as a placeholder name when only ID is configured
                        "name": org_id,
                    }
                ]
            else:
                # Multi-org mode
                await self._acquire_rate_limit(None, "getOrganizations")
                orgs_result = await asyncio.to_thread(self.api.organizations.getOrganizations)
                organizations = cast(list[dict[str, Any]], orgs_result)

            # Update cache
            self._organizations = organizations
            self._org_timestamp = current_time

            logger.info(
                "Updated organization cache",
                org_count=len(organizations),
            )

            return organizations

    async def get_networks(
        self,
        org_id: str,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Get networks for an organization with caching.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        list[dict[str, Any]]
            List of network data for the organization.

        """
        current_time = time.time()

        # Check cache validity
        cache_timestamp = self._network_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._networks
            and (current_time - cache_timestamp) < self._ttl
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for networks",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return self._networks[org_id]

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for networks, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._network_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._networks
                and (current_time - cache_timestamp) < self._ttl
            ):
                return self._networks[org_id]

            # Fetch from API
            await self._acquire_rate_limit(org_id, "getOrganizationNetworks")
            networks_result = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            networks = cast(list[dict[str, Any]], networks_result)

            # Update cache
            self._networks[org_id] = networks
            self._network_timestamps[org_id] = current_time

            logger.info(
                "Updated network cache",
                org_id=org_id,
                network_count=len(networks),
            )

            return networks

    async def get_devices(
        self,
        org_id: str,
        network_id: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Get devices for an organization with caching.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str | None
            If provided, filter devices to this network.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        list[dict[str, Any]]
            List of device data for the organization.

        """
        current_time = time.time()

        # Check cache validity
        cache_timestamp = self._device_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._devices
            and (current_time - cache_timestamp) < self._ttl
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for devices",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            devices = self._devices[org_id]
        else:
            # Cache miss - fetch from API
            self._cache_misses += 1
            logger.debug("Cache miss for devices, fetching from API", org_id=org_id)

            async with self._lock:
                # Double-check after acquiring lock
                cache_timestamp = self._device_timestamps.get(org_id, 0.0)
                if (
                    not force_refresh
                    and org_id in self._devices
                    and (current_time - cache_timestamp) < self._ttl
                ):
                    devices = self._devices[org_id]
                else:
                    # Fetch from API
                    await self._acquire_rate_limit(org_id, "getOrganizationDevices")
                    devices_result = await asyncio.to_thread(
                        self.api.organizations.getOrganizationDevices,
                        org_id,
                        total_pages="all",
                    )
                    devices = cast(list[dict[str, Any]], devices_result)

                    # Update cache
                    self._devices[org_id] = devices
                    self._device_timestamps[org_id] = current_time

                    logger.info(
                        "Updated device cache",
                        org_id=org_id,
                        device_count=len(devices),
                    )

        # Filter by network if requested
        if network_id:
            devices = [d for d in devices if d.get("networkId") == network_id]

        return devices

    async def get_device_availabilities(
        self,
        org_id: str,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Get device availabilities for an organization with caching.

        Uses a shorter TTL (2 minutes) than other inventory data since
        availability status is more dynamic.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        list[dict[str, Any]]
            List of device availability data for the organization.

        """
        current_time = time.time()

        # Check cache validity (using shorter TTL for availabilities)
        cache_timestamp = self._availability_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._device_availabilities
            and (current_time - cache_timestamp) < self.TTL_AVAILABILITY
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for device availabilities",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return self._device_availabilities[org_id]

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for device availabilities, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._availability_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._device_availabilities
                and (current_time - cache_timestamp) < self.TTL_AVAILABILITY
            ):
                return self._device_availabilities[org_id]

            # Fetch from API
            await self._acquire_rate_limit(org_id, "getOrganizationDevicesAvailabilities")
            availabilities_result = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesAvailabilities,
                org_id,
                total_pages="all",
            )
            availabilities = cast(list[dict[str, Any]], availabilities_result)

            # Update cache
            self._device_availabilities[org_id] = availabilities
            self._availability_timestamps[org_id] = current_time

            logger.info(
                "Updated device availabilities cache",
                org_id=org_id,
                device_count=len(availabilities),
            )

            return availabilities

    async def invalidate(self, org_id: str | None = None) -> None:
        """Invalidate cache for an organization or all organizations.

        Parameters
        ----------
        org_id : str | None
            If provided, invalidate only this organization's cache.
            If None, invalidate all cached data.

        """
        async with self._lock:
            if org_id is None:
                # Invalidate all
                self._organizations = None
                self._networks.clear()
                self._devices.clear()
                self._device_availabilities.clear()
                self._licenses_overview.clear()
                self._login_security.clear()
                self._org_timestamp = 0.0
                self._network_timestamps.clear()
                self._device_timestamps.clear()
                self._availability_timestamps.clear()
                self._license_timestamps.clear()
                self._security_timestamps.clear()
                logger.info("Invalidated all inventory cache")
            else:
                # Invalidate specific org
                if org_id in self._networks:
                    del self._networks[org_id]
                if org_id in self._devices:
                    del self._devices[org_id]
                if org_id in self._device_availabilities:
                    del self._device_availabilities[org_id]
                if org_id in self._licenses_overview:
                    del self._licenses_overview[org_id]
                if org_id in self._login_security:
                    del self._login_security[org_id]
                if org_id in self._network_timestamps:
                    del self._network_timestamps[org_id]
                if org_id in self._device_timestamps:
                    del self._device_timestamps[org_id]
                if org_id in self._availability_timestamps:
                    del self._availability_timestamps[org_id]
                if org_id in self._license_timestamps:
                    del self._license_timestamps[org_id]
                if org_id in self._security_timestamps:
                    del self._security_timestamps[org_id]
                logger.info("Invalidated inventory cache for organization", org_id=org_id)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns
        -------
        dict[str, Any]
            Dictionary with cache statistics including hit/miss counts and rates.

        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_requests": total_requests,
            "hit_rate_percent": hit_rate,
            "cached_orgs": 1 if self._organizations else 0,
            "cached_networks": len(self._networks),
            "cached_devices": len(self._devices),
            "cached_availabilities": len(self._device_availabilities),
            "cached_licenses": len(self._licenses_overview),
            "cached_security": len(self._login_security),
        }

    def set_ttl_for_tier(self, tier: UpdateTier) -> None:
        """Set cache TTL based on update tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier to base TTL on.

        """
        if tier == UpdateTier.FAST:
            self._ttl = self.TTL_FAST
        elif tier == UpdateTier.MEDIUM:
            self._ttl = self.TTL_MEDIUM
        else:  # SLOW
            self._ttl = self.TTL_SLOW

        logger.info(
            "Updated inventory cache TTL",
            tier=tier.value,
            ttl_seconds=self._ttl,
        )

    async def get_networks_with_device_types(
        self,
        org_id: str,
        product_types: list[str],
    ) -> list[dict[str, Any]]:
        """Get networks that have at least one device of specified types.

        This helper reduces API calls by filtering networks based on cached
        device inventory, so you only make per-network API calls for networks
        that actually have relevant devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        product_types : list[str]
            Product types to filter by (e.g., ["sensor"], ["wireless"], ["switch"]).

        Returns
        -------
        list[dict[str, Any]]
            List of networks that have at least one device of the specified types.

        Examples
        --------
        Get networks with MT sensors:
        >>> networks = await inventory.get_networks_with_device_types(org_id, ["sensor"])

        Get networks with wireless or switch devices:
        >>> networks = await inventory.get_networks_with_device_types(
        ...     org_id, ["wireless", "switch"]
        ... )

        """
        # Get all devices from cache
        devices = await self.get_devices(org_id)

        # Find network IDs that have at least one device of specified types
        network_ids_with_devices = {
            d.get("networkId")
            for d in devices
            if d.get("productType") in product_types and d.get("networkId")
        }

        if not network_ids_with_devices:
            logger.debug(
                "No networks found with specified device types",
                org_id=org_id,
                product_types=product_types,
            )
            return []

        # Get all networks from cache
        networks = await self.get_networks(org_id)

        # Filter to networks that have the device types
        filtered_networks = [n for n in networks if n.get("id") in network_ids_with_devices]

        logger.debug(
            "Filtered networks by device types",
            org_id=org_id,
            product_types=product_types,
            total_networks=len(networks),
            filtered_networks=len(filtered_networks),
        )

        return filtered_networks

    async def get_licenses_overview(
        self,
        org_id: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Get organization license overview with caching.

        Uses a longer TTL (30 minutes) since license data rarely changes.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        dict[str, Any]
            License overview data for the organization.

        """
        current_time = time.time()

        # Check cache validity (using longer TTL for licenses)
        cache_timestamp = self._license_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._licenses_overview
            and (current_time - cache_timestamp) < self.TTL_LICENSE
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for licenses overview",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return self._licenses_overview[org_id]

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for licenses overview, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._license_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._licenses_overview
                and (current_time - cache_timestamp) < self.TTL_LICENSE
            ):
                return self._licenses_overview[org_id]

            # Fetch from API
            try:
                await self._acquire_rate_limit(org_id, "getOrganizationLicensesOverview")
                overview_result = await asyncio.to_thread(
                    self.api.organizations.getOrganizationLicensesOverview,
                    org_id,
                )
                overview = cast(dict[str, Any], overview_result)

                # Update cache
                self._licenses_overview[org_id] = overview
                self._license_timestamps[org_id] = current_time

                logger.info(
                    "Updated licenses overview cache",
                    org_id=org_id,
                )

                return overview
            except Exception:
                # Return empty dict on error, don't cache errors
                logger.debug(
                    "Failed to fetch licenses overview (may not be supported)",
                    org_id=org_id,
                )
                return {}

    async def get_login_security(
        self,
        org_id: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Get organization login security settings with caching.

        Uses a longer TTL (60 minutes) since security settings rarely change.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        dict[str, Any]
            Login security settings for the organization.

        """
        current_time = time.time()

        # Check cache validity (using longer TTL for config data)
        cache_timestamp = self._security_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._login_security
            and (current_time - cache_timestamp) < self.TTL_CONFIG
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for login security",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return self._login_security[org_id]

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for login security, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._security_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._login_security
                and (current_time - cache_timestamp) < self.TTL_CONFIG
            ):
                return self._login_security[org_id]

            # Fetch from API
            try:
                await self._acquire_rate_limit(org_id, "getOrganizationLoginSecurity")
                security_result = await asyncio.to_thread(
                    self.api.organizations.getOrganizationLoginSecurity,
                    org_id,
                )
                security = cast(dict[str, Any], security_result)

                # Update cache
                self._login_security[org_id] = security
                self._security_timestamps[org_id] = current_time

                logger.info(
                    "Updated login security cache",
                    org_id=org_id,
                )

                return security
            except Exception:
                # Return empty dict on error, don't cache errors
                logger.debug(
                    "Failed to fetch login security",
                    org_id=org_id,
                )
                return {}
