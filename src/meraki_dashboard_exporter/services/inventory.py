"""Organization inventory service for caching org/network/device data.

This service provides a shared cache of organization, network, and device
inventory data to reduce redundant API calls across collectors. Implements
TTL-based cache invalidation with different TTLs per update tier.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

import structlog

from ..core.constants import UpdateTier

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ..core.config import Settings

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

    # TTL values in seconds based on update tier
    TTL_FAST = 300  # 5 minutes
    TTL_MEDIUM = 900  # 15 minutes
    TTL_SLOW = 1800  # 30 minutes

    def __init__(self, api: DashboardAPI, settings: Settings) -> None:
        """Initialize the inventory service.

        Parameters
        ----------
        api : DashboardAPI
            Meraki Dashboard API client.
        settings : Settings
            Application settings.

        """
        self.api = api
        self.settings = settings

        # Determine TTL based on fastest tier in use
        # Use MEDIUM tier TTL as a reasonable default
        self._ttl = self.TTL_MEDIUM

        # Cache storage
        self._organizations: list[dict[str, Any]] | None = None
        self._networks: dict[str, list[dict[str, Any]]] = {}
        self._devices: dict[str, list[dict[str, Any]]] = {}

        # Cache timestamps
        self._org_timestamp: float = 0.0
        self._network_timestamps: dict[str, float] = {}
        self._device_timestamps: dict[str, float] = {}

        # Lock for thread-safe cache updates
        self._lock = asyncio.Lock()

        # Metrics
        self._cache_hits = 0
        self._cache_misses = 0

        logger.info(
            "Initialized organization inventory cache",
            ttl_seconds=self._ttl,
        )

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
                self._org_timestamp = 0.0
                self._network_timestamps.clear()
                self._device_timestamps.clear()
                logger.info("Invalidated all inventory cache")
            else:
                # Invalidate specific org
                if org_id in self._networks:
                    del self._networks[org_id]
                if org_id in self._devices:
                    del self._devices[org_id]
                if org_id in self._network_timestamps:
                    del self._network_timestamps[org_id]
                if org_id in self._device_timestamps:
                    del self._device_timestamps[org_id]
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
