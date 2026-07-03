"""Organization inventory service for caching org/network/device data.

This service provides a shared cache of organization, network, and device
inventory data to reduce redundant API calls across collectors. Implements
TTL-based cache invalidation with different TTLs per update tier.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

import structlog
from meraki.exceptions import APIError
from prometheus_client import Counter, Gauge

from ..api.client import AsyncMerakiClient
from ..core.constants.metrics_constants import CollectorMetricName, NetworkMetricName
from ..core.error_handling import validate_response_format
from ..core.network_filter import NetworkFilter
from ..core.scheduler import OrgShape

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ..core.config import Settings

T = TypeVar("T")

logger = structlog.get_logger(__name__)


class OrganizationInventory:
    """Shared inventory cache for organizations, networks, and devices.

    Reduces API calls by caching inventory data with TTL-based invalidation.
    The general cache TTL is fixed at ``TTL_MEDIUM`` (900s) for every reader --
    there is no per-collector TTL wiring (a prior ``set_ttl_for_tier`` method had
    zero callers and was removed; see #275). Device availability data has its own
    shorter, always-applied ``TTL_AVAILABILITY`` (120s) since it is more dynamic.

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

    # General inventory cache TTL in seconds (the single, tier-independent TTL).
    TTL_MEDIUM = 900  # 15 minutes

    # Shorter TTL for availability data (more dynamic than inventory)
    TTL_AVAILABILITY = 120  # 2 minutes

    # Longer TTL for slow-changing configuration data
    TTL_LICENSE = 1800  # 30 minutes - license data rarely changes

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        rate_limiter: Any | None = None,
        network_filter: NetworkFilter | None = None,
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
        network_filter : NetworkFilter | None
            Optional network filter applied at the read path. The internal
            cache always stores the full API response; filtering happens
            on every call to :meth:`get_networks`, :meth:`get_devices`, and
            :meth:`get_device_availabilities` unless ``unfiltered=True`` is
            passed by the caller.

        """
        self.api = api
        self.settings = settings
        self.rate_limiter = rate_limiter
        self._network_filter = network_filter

        # Determine TTL based on fastest tier in use
        # Use MEDIUM tier TTL as a reasonable default
        self._ttl = self.TTL_MEDIUM

        # Cache storage
        self._organizations: list[dict[str, Any]] | None = None
        self._networks: dict[str, list[dict[str, Any]]] = {}
        self._devices: dict[str, list[dict[str, Any]]] = {}
        self._device_availabilities: dict[str, list[dict[str, Any]]] = {}
        self._licenses_overview: dict[str, dict[str, Any]] = {}
        self._licenses: dict[str, list[dict[str, Any]]] = {}

        # Cache timestamps
        self._org_timestamp: float = 0.0
        self._network_timestamps: dict[str, float] = {}
        self._device_timestamps: dict[str, float] = {}
        self._availability_timestamps: dict[str, float] = {}
        self._license_timestamps: dict[str, float] = {}
        self._license_list_timestamps: dict[str, float] = {}

        # Lock for thread-safe cache updates
        self._lock = asyncio.Lock()

        # Metrics
        self._cache_hits = 0
        self._cache_misses = 0

        # Prometheus gauge for cache sizes
        self._cache_size = Gauge(
            CollectorMetricName.INVENTORY_CACHE_ENTRIES.value,
            "Number of entries in inventory cache",
            ["org_id", "cache_type"],
        )

        # Per-org set of network IDs for which a filter_match series was emitted, so
        # stale series can be removed when a network is deleted (F-079).
        self._filter_match_emitted: dict[str, set[str]] = {}

        # Network-filter observability gauges. ``network_name`` is deliberately
        # omitted from labels to avoid orphan time series on rename.
        self._filter_match_gauge = Gauge(
            NetworkMetricName.NETWORK_FILTER_MATCH.value,
            "1 if the network passes the configured network filter, 0 otherwise.",
            ["org_id", "network_id"],
        )
        self._filter_resolved_gauge = Gauge(
            NetworkMetricName.NETWORK_FILTER_RESOLVED.value,
            "Number of networks included by the configured network filter.",
            ["org_id"],
        )
        self._filter_total_gauge = Gauge(
            NetworkMetricName.NETWORK_FILTER_NETWORKS.value,
            "Number of networks discovered before filtering.",
            ["org_id"],
        )

        logger.info(
            "Initialized organization inventory cache",
            ttl_seconds=self._ttl,
        )

    async def _acquire_rate_limit(self, org_id: str | None, endpoint: str) -> None:
        if self.rate_limiter is None:
            return
        await self.rate_limiter.acquire(org_id, endpoint)

    def _maybe_filter_networks(
        self, networks: list[dict[str, Any]], *, unfiltered: bool
    ) -> list[dict[str, Any]]:
        """Apply the configured network filter unless ``unfiltered`` is True.

        Returns a new list when filtering is active so callers can mutate
        safely; returns the original list otherwise to avoid copies on the
        hot path.
        """
        if unfiltered or self._network_filter is None or not self._network_filter.is_active:
            return networks
        return self._network_filter.apply(networks)

    def _resolved_network_ids(self, org_id: str) -> set[str] | None:
        """Return the set of allowed network IDs for ``org_id``, or None.

        Returns None when no filter is active. Reads from the existing
        ``_networks[org_id]`` cache; callers must ensure the cache has
        been populated (typically via a prior ``get_networks`` call).
        """
        if self._network_filter is None or not self._network_filter.is_active:
            return None
        full = self._networks.get(org_id)
        if full is None:
            return None
        return self._network_filter.resolved_ids(full)

    async def get_allowed_network_ids(
        self, org_id: str, *, force_refresh: bool = False
    ) -> set[str] | None:
        """Return network IDs that pass the configured filter, or None.

        Unlike :meth:`_resolved_network_ids` (sync, may return ``None`` on
        cache miss), this awaits the network cache populate path so callers
        always receive a usable answer when a filter is active. Collectors
        that iterate org-wide SDK responses should use this as an allow-list
        to skip rows whose ``networkId`` falls outside the filter.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass the network cache when populating.

        Returns
        -------
        set[str] | None
            Allowed network IDs, or ``None`` when no filter is active —
            callers should treat ``None`` as "filtering disabled, accept
            every row".

        """
        if self._network_filter is None or not self._network_filter.is_active:
            return None
        networks = await self.get_networks(org_id, force_refresh=force_refresh, unfiltered=True)
        return self._network_filter.resolved_ids(networks)

    def _is_expired(self, timestamp: float, ttl: float) -> bool:
        """Check if a cached entry has expired with jitter.

        Adds ±10% jitter to TTL to prevent thundering herd when multiple
        cache entries expire at the same time.

        Parameters
        ----------
        timestamp : float
            The time the entry was cached (from time.time()).
        ttl : float
            Base TTL in seconds.

        Returns
        -------
        bool
            True if the entry should be considered expired.

        """
        jittered_ttl = ttl * (0.9 + random.random() * 0.2)
        return (time.time() - timestamp) >= jittered_ttl

    @classmethod
    def _get_api_metrics(cls) -> Counter:
        """Get the API requests counter from AsyncMerakiClient.

        Reuses the Counter already registered by AsyncMerakiClient to avoid
        duplicate metric registration errors.
        """
        AsyncMerakiClient._ensure_metrics_initialized()
        if AsyncMerakiClient._api_requests_total is None:
            raise RuntimeError("AsyncMerakiClient metrics not available after initialization.")
        return AsyncMerakiClient._api_requests_total

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
            AsyncMerakiClient.record_auth_outcome(True)
            return result
        except APIError as e:
            counter.labels(endpoint=endpoint, method="GET", status_code=str(e.status)).inc()
            if e.status == 401:
                AsyncMerakiClient.record_auth_outcome(False)
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
            and not self._is_expired(self._org_timestamp, self._ttl)
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
                and not self._is_expired(self._org_timestamp, self._ttl)
            ):
                return self._organizations

            # Fetch from API
            if self.settings.meraki.org_id:
                # Single org mode - fetch the real organization name via
                # getOrganization so org_name labels aren't just the numeric
                # ID (F-116). Fall back to the ID as a placeholder if the
                # lookup fails for any reason (e.g. transient API error).
                org_id = self.settings.meraki.org_id
                try:
                    await self._acquire_rate_limit(org_id, "getOrganization")
                    org_result = await self._make_api_call(
                        "getOrganization",
                        self.api.organizations.getOrganization,
                        org_id,
                    )
                    org_result = validate_response_format(
                        org_result, expected_type=dict, operation="getOrganization"
                    )
                    organizations = [cast(dict[str, Any], org_result)]
                except Exception:
                    logger.debug(
                        "Failed to fetch organization name; using org_id as placeholder",
                        org_id=org_id,
                    )
                    organizations = [
                        {
                            "id": org_id,
                            # Use org_id as a placeholder name when the lookup fails
                            "name": org_id,
                        }
                    ]
            else:
                # Multi-org mode
                await self._acquire_rate_limit(None, "getOrganizations")
                orgs_result = await self._make_api_call(
                    "getOrganizations",
                    self.api.organizations.getOrganizations,
                    total_pages="all",
                )
                orgs_result = validate_response_format(
                    orgs_result, expected_type=list, operation="getOrganizations"
                )
                organizations = cast(list[dict[str, Any]], orgs_result)

            # Update cache
            self._organizations = organizations
            self._org_timestamp = current_time
            self._cache_size.labels(org_id="global", cache_type="organizations").set(
                len(organizations)
            )

            logger.info(
                "Updated organization cache",
                org_count=len(organizations),
            )

            return organizations

    async def get_networks(
        self,
        org_id: str,
        force_refresh: bool = False,
        *,
        unfiltered: bool = False,
    ) -> list[dict[str, Any]]:
        """Get networks for an organization with caching.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.
        unfiltered : bool
            If True, return the full cached list ignoring any configured
            :class:`NetworkFilter`. Defaults to False — most callers want
            the filtered view.

        Returns
        -------
        list[dict[str, Any]]
            List of network data for the organization (filter applied
            unless ``unfiltered=True``).

        """
        current_time = time.time()

        # Check cache validity
        cache_timestamp = self._network_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._networks
            and not self._is_expired(cache_timestamp, self._ttl)
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for networks",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return self._maybe_filter_networks(self._networks[org_id], unfiltered=unfiltered)

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for networks, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._network_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._networks
                and not self._is_expired(cache_timestamp, self._ttl)
            ):
                return self._maybe_filter_networks(self._networks[org_id], unfiltered=unfiltered)

            # Fetch from API
            await self._acquire_rate_limit(org_id, "getOrganizationNetworks")
            networks_result = await self._make_api_call(
                "getOrganizationNetworks",
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            networks_result = validate_response_format(
                networks_result, expected_type=list, operation="getOrganizationNetworks"
            )
            networks = cast(list[dict[str, Any]], networks_result)

            # Update cache (full, unfiltered list — filter applies on read)
            self._networks[org_id] = networks
            self._network_timestamps[org_id] = current_time
            self._cache_size.labels(org_id=org_id, cache_type="networks").set(len(networks))
            self._emit_filter_metrics(org_id, networks)

            logger.info(
                "Updated network cache",
                org_id=org_id,
                network_count=len(networks),
            )

            return self._maybe_filter_networks(networks, unfiltered=unfiltered)

    def _emit_filter_metrics(self, org_id: str, networks: list[dict[str, Any]]) -> None:
        """Emit per-network filter-match metrics and summary gauges.

        Called once per cache refresh. The per-network match gauge is set
        to 1.0 when the network passes the configured filter and 0.0 when
        excluded; when the filter is inactive every network resolves to
        1.0 so dashboards work uniformly across filtered/unfiltered
        deployments.
        """
        total = len(networks)
        if self._network_filter is not None and self._network_filter.is_active:
            allowed_ids = self._network_filter.resolved_ids(networks)
        else:
            allowed_ids = {n.get("id", "") for n in networks if n.get("id")}

        self._filter_total_gauge.labels(org_id=org_id).set(total)
        self._filter_resolved_gauge.labels(org_id=org_id).set(len(allowed_ids))

        current_ids: set[str] = set()
        for n in networks:
            nid = n.get("id", "")
            if not nid:
                continue
            current_ids.add(nid)
            value = 1.0 if nid in allowed_ids else 0.0
            self._filter_match_gauge.labels(org_id=org_id, network_id=nid).set(value)

        # Remove filter_match series for networks that disappeared since the last
        # refresh so deleted networks don't leak stale series indefinitely (F-079).
        for stale_nid in self._filter_match_emitted.get(org_id, set()) - current_ids:
            try:
                self._filter_match_gauge.remove(org_id, stale_nid)
            except KeyError:
                pass
        self._filter_match_emitted[org_id] = current_ids

    async def get_devices(
        self,
        org_id: str,
        network_id: str | None = None,
        force_refresh: bool = False,
        *,
        unfiltered: bool = False,
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
        unfiltered : bool
            If True, return all cached devices ignoring any configured
            :class:`NetworkFilter`. Defaults to False — devices in
            excluded networks are dropped.

        Returns
        -------
        list[dict[str, Any]]
            List of device data for the organization (filter applied
            unless ``unfiltered=True``).

        """
        current_time = time.time()

        # Check cache validity
        cache_timestamp = self._device_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._devices
            and not self._is_expired(cache_timestamp, self._ttl)
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
                    and not self._is_expired(cache_timestamp, self._ttl)
                ):
                    devices = self._devices[org_id]
                else:
                    # Fetch from API
                    await self._acquire_rate_limit(org_id, "getOrganizationDevices")
                    devices_result = await self._make_api_call(
                        "getOrganizationDevices",
                        self.api.organizations.getOrganizationDevices,
                        org_id,
                        total_pages="all",
                    )
                    devices_result = validate_response_format(
                        devices_result, expected_type=list, operation="getOrganizationDevices"
                    )
                    devices = cast(list[dict[str, Any]], devices_result)

                    # Update cache
                    self._devices[org_id] = devices
                    self._device_timestamps[org_id] = current_time
                    self._cache_size.labels(org_id=org_id, cache_type="devices").set(len(devices))

                    logger.info(
                        "Updated device cache",
                        org_id=org_id,
                        device_count=len(devices),
                    )

        # Filter by network if requested
        if network_id:
            devices = [d for d in devices if d.get("networkId") == network_id]

        # Apply NetworkFilter — drops devices whose networkId is excluded.
        if not unfiltered and self._network_filter and self._network_filter.is_active:
            networks = self._networks.get(org_id)
            if networks is None:
                # Cache miss for networks — fetch unfiltered so the resolved
                # set is correct. This is rare in practice because warm_cache
                # populates networks first, but be defensive.
                networks = await self.get_networks(org_id, unfiltered=True)
            allowed_ids = self._network_filter.resolved_ids(networks)
            devices = [d for d in devices if d.get("networkId") in allowed_ids]

        # Return defensive shallow copies so consumers (e.g. collectors/device.py
        # enrichment adding availability_status/networkName/orgId/orgName) can
        # mutate the returned dicts in place without polluting the shared cache
        # for the rest of its TTL (F-078). Enrichment only sets top-level scalar
        # keys, so a shallow copy per device is sufficient and far cheaper than
        # a deep copy.
        return [dict(d) for d in devices]

    async def get_device_availabilities(
        self,
        org_id: str,
        force_refresh: bool = False,
        *,
        unfiltered: bool = False,
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
        unfiltered : bool
            If True, return all cached availability records ignoring any
            configured :class:`NetworkFilter`. Defaults to False —
            availability records for excluded networks are dropped.

        Returns
        -------
        list[dict[str, Any]]
            List of device availability data for the organization (filter
            applied unless ``unfiltered=True``).

        """
        current_time = time.time()

        # Check cache validity (using shorter TTL for availabilities)
        cache_timestamp = self._availability_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._device_availabilities
            and not self._is_expired(cache_timestamp, self.TTL_AVAILABILITY)
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for device availabilities",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return await self._maybe_filter_availabilities(
                org_id, self._device_availabilities[org_id], unfiltered=unfiltered
            )

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for device availabilities, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._availability_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._device_availabilities
                and not self._is_expired(cache_timestamp, self.TTL_AVAILABILITY)
            ):
                return await self._maybe_filter_availabilities(
                    org_id, self._device_availabilities[org_id], unfiltered=unfiltered
                )

            # Fetch from API
            await self._acquire_rate_limit(org_id, "getOrganizationDevicesAvailabilities")
            availabilities_result = await self._make_api_call(
                "getOrganizationDevicesAvailabilities",
                self.api.organizations.getOrganizationDevicesAvailabilities,
                org_id,
                total_pages="all",
            )
            availabilities_result = validate_response_format(
                availabilities_result,
                expected_type=list,
                operation="getOrganizationDevicesAvailabilities",
            )
            availabilities = cast(list[dict[str, Any]], availabilities_result)

            # Update cache (full, unfiltered list — filter applies on read)
            self._device_availabilities[org_id] = availabilities
            self._availability_timestamps[org_id] = current_time
            self._cache_size.labels(org_id=org_id, cache_type="availabilities").set(
                len(availabilities)
            )

            logger.info(
                "Updated device availabilities cache",
                org_id=org_id,
                device_count=len(availabilities),
            )

            return await self._maybe_filter_availabilities(
                org_id, availabilities, unfiltered=unfiltered
            )

    async def _maybe_filter_availabilities(
        self,
        org_id: str,
        availabilities: list[dict[str, Any]],
        *,
        unfiltered: bool,
    ) -> list[dict[str, Any]]:
        """Apply network filter to availability records.

        Availability records expose ``networkId`` either directly or via a
        nested ``network.id`` key, depending on the SDK response shape.
        """
        if unfiltered or self._network_filter is None or not self._network_filter.is_active:
            return availabilities

        networks = self._networks.get(org_id)
        if networks is None:
            networks = await self.get_networks(org_id, unfiltered=True)
        allowed_ids = self._network_filter.resolved_ids(networks)

        def _net_id(record: dict[str, Any]) -> str | None:
            if "networkId" in record:
                return record.get("networkId")
            net = record.get("network") or {}
            return net.get("id")

        return [a for a in availabilities if _net_id(a) in allowed_ids]

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
                self._licenses.clear()
                self._org_timestamp = 0.0
                self._network_timestamps.clear()
                self._device_timestamps.clear()
                self._availability_timestamps.clear()
                self._license_timestamps.clear()
                self._license_list_timestamps.clear()
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
                if org_id in self._licenses:
                    del self._licenses[org_id]
                if org_id in self._network_timestamps:
                    del self._network_timestamps[org_id]
                if org_id in self._device_timestamps:
                    del self._device_timestamps[org_id]
                if org_id in self._availability_timestamps:
                    del self._availability_timestamps[org_id]
                if org_id in self._license_timestamps:
                    del self._license_timestamps[org_id]
                if org_id in self._license_list_timestamps:
                    del self._license_list_timestamps[org_id]
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
            "cached_license_lists": len(self._licenses),
        }

    @staticmethod
    def _log_startup_auth_error(exc: Exception) -> bool:
        """Emit a concise WARNING for a 401 during startup cache warming.

        A Meraki SDK 401 (`APIError` with ``.status == 401``) otherwise reaches
        ``logger.exception`` and dumps a ~2KB frame-locals traceback that buries
        the actionable message. For a 401 we log one plain-English WARNING and
        relegate the full traceback to DEBUG (#589). The auth-outcome latch is
        already recorded upstream in ``_make_api_call``.

        Parameters
        ----------
        exc : Exception
            The exception raised during warming.

        Returns
        -------
        bool
            True if this was a 401 and has been logged; False otherwise (caller
            should fall back to its normal ``logger.exception`` handling).

        """
        if isinstance(exc, APIError) and exc.status == 401:
            logger.warning("Meraki API key rejected (401) - check MERAKI_EXPORTER_MERAKI__API_KEY")
            logger.debug("401 rejection during cache warming", exc_info=True)
            return True
        return False

    async def warm_cache(self, org_ids: list[str] | None = None) -> None:
        """Pre-populate cache for all or specified organizations.

        Called before starting collectors so the first collection cycle
        gets cache hits instead of misses. Fetches organizations, networks,
        and devices for each target organization.

        Parameters
        ----------
        org_ids : list[str] | None
            If provided, only warm cache for these organization IDs.
            If None, warm cache for all organizations.

        """
        try:
            orgs = await self.get_organizations()
        except Exception as exc:
            if not self._log_startup_auth_error(exc):
                logger.exception("Failed to fetch organizations during cache warming")
            return

        target_orgs = [o for o in orgs if org_ids is None or o.get("id") in org_ids]

        for org in target_orgs:
            org_id = org.get("id", "")
            if not org_id:
                continue
            try:
                await self.get_networks(org_id)
                await self.get_devices(org_id)
                logger.info("Warmed cache for organization", org_id=org_id)
            except Exception as exc:
                if not self._log_startup_auth_error(exc):
                    logger.exception(
                        "Failed to warm cache for organization",
                        org_id=org_id,
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
    ) -> dict[str, Any] | None:
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
        dict[str, Any] | None
            License overview data for the organization, or ``None`` if the
            fetch failed (distinct from a legitimately empty ``{}`` response
            — see F-100). Callers must treat ``None`` as "fetch failed, skip
            this cycle" rather than falling through to per-device licensing
            handling.

        """
        current_time = time.time()

        # Check cache validity (using longer TTL for licenses)
        cache_timestamp = self._license_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._licenses_overview
            and not self._is_expired(cache_timestamp, self.TTL_LICENSE)
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
                and not self._is_expired(cache_timestamp, self.TTL_LICENSE)
            ):
                return self._licenses_overview[org_id]

            # Fetch from API
            try:
                await self._acquire_rate_limit(org_id, "getOrganizationLicensesOverview")
                overview_result = await self._make_api_call(
                    "getOrganizationLicensesOverview",
                    self.api.organizations.getOrganizationLicensesOverview,
                    org_id,
                )
                overview_result = validate_response_format(
                    overview_result,
                    expected_type=dict,
                    operation="getOrganizationLicensesOverview",
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
                # Return None (not {}) on error, don't cache errors, so callers
                # can distinguish "fetch failed" from "legitimately empty
                # overview" (F-100) instead of misrouting to the per-device
                # licensing branch.
                logger.debug(
                    "Failed to fetch licenses overview (may not be supported)",
                    org_id=org_id,
                )
                return None

    async def get_licenses(
        self,
        org_id: str,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]] | None:
        """Get the full per-device license list for an organization, cached.

        Mirrors :meth:`get_licenses_overview`'s TTL (30 minutes) since
        license data rarely changes (F-102) — previously this fetch ran
        uncached on every collection cycle while the overview honored a
        30-minute TTL.

        Parameters
        ----------
        org_id : str
            Organization ID.
        force_refresh : bool
            If True, bypass cache and fetch fresh data.

        Returns
        -------
        list[dict[str, Any]] | None
            Per-device license list for the organization, or ``None`` if the
            fetch failed (distinct from a legitimately empty ``[]`` list).

        """
        current_time = time.time()

        # Check cache validity (using the same longer TTL as the overview)
        cache_timestamp = self._license_list_timestamps.get(org_id, 0.0)
        if (
            not force_refresh
            and org_id in self._licenses
            and not self._is_expired(cache_timestamp, self.TTL_LICENSE)
        ):
            self._cache_hits += 1
            logger.debug(
                "Cache hit for licenses",
                org_id=org_id,
                cache_age_seconds=current_time - cache_timestamp,
            )
            return self._licenses[org_id]

        # Cache miss - fetch from API
        self._cache_misses += 1
        logger.debug("Cache miss for licenses, fetching from API", org_id=org_id)

        async with self._lock:
            # Double-check after acquiring lock
            cache_timestamp = self._license_list_timestamps.get(org_id, 0.0)
            if (
                not force_refresh
                and org_id in self._licenses
                and not self._is_expired(cache_timestamp, self.TTL_LICENSE)
            ):
                return self._licenses[org_id]

            # Fetch from API
            try:
                await self._acquire_rate_limit(org_id, "getOrganizationLicenses")
                licenses_result = await self._make_api_call(
                    "getOrganizationLicenses",
                    self.api.organizations.getOrganizationLicenses,
                    org_id,
                    total_pages="all",
                )
                licenses_result = validate_response_format(
                    licenses_result,
                    expected_type=list,
                    operation="getOrganizationLicenses",
                )
                licenses = cast(list[dict[str, Any]], licenses_result)

                # Update cache
                self._licenses[org_id] = licenses
                self._license_list_timestamps[org_id] = current_time

                logger.info(
                    "Updated licenses cache",
                    org_id=org_id,
                    license_count=len(licenses),
                )

                return licenses
            except Exception:
                # Return None (not []) on error, don't cache errors, so
                # callers can distinguish "fetch failed" from "legitimately
                # empty license list".
                logger.debug(
                    "Failed to fetch licenses (may not be supported)",
                    org_id=org_id,
                )
                return None

    async def get_org_shape(self, org_id: str) -> OrgShape:
        """Compute the sizing snapshot for the adaptive scheduler (#617).

        Built entirely from cached inventory reads -- ``get_networks`` and
        ``get_devices`` -- so it costs zero extra API calls in the steady
        state (both hit the 900s inventory cache). Networks are counted from
        the ``NetworkFilter``-enforced view (``get_networks`` applies the
        filter on read), so the shape reflects only the networks the exporter
        actually polls; devices come from the equally-filtered ``get_devices``
        view.

        Networks are classified by their ``productTypes`` list membership and
        devices by their scalar ``productType``. ``physical_mx_count`` counts
        appliance devices whose ``model`` does NOT start with ``"VMX"``
        (case-insensitive) -- i.e. it excludes virtual MX (vMX) instances,
        which have no physical-appliance API cost.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        OrgShape
            Frozen sizing snapshot with all fields populated.

        """
        networks = await self.get_networks(org_id)
        devices = await self.get_devices(org_id)

        def _net_has(product_type: str) -> int:
            return sum(1 for n in networks if product_type in (n.get("productTypes") or []))

        def _dev_is(product_type: str) -> int:
            return sum(1 for d in devices if d.get("productType") == product_type)

        physical_mx_count = sum(
            1
            for d in devices
            if d.get("productType") == "appliance"
            and not str(d.get("model") or "").upper().startswith("VMX")
        )

        # Phase 4B (#326/#624): Catalyst APs are wireless devices with CW* models.
        catalyst_ap_count = sum(
            1
            for d in devices
            if d.get("productType") == "wireless"
            and str(d.get("model") or "").upper().startswith("CW")
        )

        # Phase 4B (#324): APs selected for per-AP signal-quality collection.
        collectors = self.settings.collectors
        if not collectors.collect_ap_signal_quality:
            signal_quality_ap_count = 0
        elif not collectors.ap_signal_quality_tags:
            signal_quality_ap_count = _dev_is("wireless")
        else:
            selected_tags = set(collectors.ap_signal_quality_tags)
            signal_quality_ap_count = sum(
                1
                for d in devices
                if d.get("productType") == "wireless"
                and selected_tags.intersection(d.get("tags") or [])
            )

        return OrgShape(
            org_id=org_id,
            network_count=len(networks),
            wireless_network_count=_net_has("wireless"),
            switch_network_count=_net_has("switch"),
            appliance_network_count=_net_has("appliance"),
            sensor_network_count=_net_has("sensor"),
            camera_network_count=_net_has("camera"),
            cellular_network_count=_net_has("cellularGateway"),
            device_count=len(devices),
            ap_count=_dev_is("wireless"),
            switch_count=_dev_is("switch"),
            appliance_count=_dev_is("appliance"),
            physical_mx_count=physical_mx_count,
            camera_count=_dev_is("camera"),
            sensor_count=_dev_is("sensor"),
            cellular_count=_dev_is("cellularGateway"),
            catalyst_ap_count=catalyst_ap_count,
            signal_quality_ap_count=signal_quality_ap_count,
        )
