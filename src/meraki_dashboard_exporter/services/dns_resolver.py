"""DNS resolver service for client hostname lookups."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass

import structlog

from ..core.async_utils import AsyncRetry, with_timeout
from ..core.config import Settings

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """DNS cache entry with TTL."""

    hostname: str | None
    timestamp: float
    client_id: str | None = None
    description: str | None = None


class DNSResolver:
    """Service for performing reverse DNS lookups on client IP addresses."""

    def __init__(self, settings: Settings):
        """Initialize DNS resolver.

        Parameters
        ----------
        settings : Settings
            Application settings.

        """
        self.settings = settings
        self.dns_server = settings.clients.dns_server
        self.timeout = settings.clients.dns_timeout
        self.cache_ttl = settings.clients.dns_cache_ttl
        self._cache: dict[str, CacheEntry] = {}
        self._client_tracking: dict[str, dict[str, str]] = {}  # client_id -> {ip, description}
        self._resolver_configured = False
        self._retry = AsyncRetry(max_attempts=3, base_delay=1.0, max_delay=5.0)
        self._configure_resolver()

        # Statistics tracking
        self._stats = {
            "total_lookups": 0,
            "successful_lookups": 0,
            "failed_lookups": 0,
            "cache_hits": 0,
        }

    def _configure_resolver(self) -> None:
        """Configure DNS resolver with custom server if provided."""
        if self.dns_server:
            try:
                # Validate DNS server IP
                ipaddress.ip_address(self.dns_server)
                self._resolver_configured = True
                logger.info("Using custom DNS server", dns_server=self.dns_server)
            except ValueError:
                logger.error(
                    "Invalid DNS server address, using system default",
                    dns_server=self.dns_server,
                )
                self.dns_server = None

    def track_client(self, client_id: str, ip: str | None, description: str | None) -> bool:
        """Track client information to detect changes.

        Parameters
        ----------
        client_id : str
            Client ID.
        ip : str | None
            Client IP address.
        description : str | None
            Client description.

        Returns
        -------
        bool
            True if client info changed, False otherwise.

        """
        current_info = {"ip": ip or "", "description": description or ""}
        previous_info = self._client_tracking.get(client_id)

        if previous_info != current_info:
            self._client_tracking[client_id] = current_info
            if previous_info and previous_info.get("ip") != current_info["ip"]:
                # IP changed, invalidate cache for old IP
                old_ip = previous_info.get("ip")
                if old_ip and old_ip in self._cache:
                    logger.info(
                        "Client IP changed, invalidating DNS cache",
                        client_id=client_id,
                        old_ip=old_ip,
                        new_ip=ip,
                    )
                    del self._cache[old_ip]
            return True
        return False

    def _is_cache_valid(self, entry: CacheEntry) -> bool:
        """Check if a cache entry is still valid.

        Parameters
        ----------
        entry : CacheEntry
            Cache entry to check.

        Returns
        -------
        bool
            True if entry is still valid, False otherwise.

        """
        age = time.time() - entry.timestamp
        return age < self.cache_ttl

    async def resolve_hostname(self, ip: str | None, client_id: str | None = None) -> str | None:
        """Resolve hostname from IP address.

        Parameters
        ----------
        ip : str | None
            IP address to resolve.
        client_id : str | None
            Client ID for tracking.

        Returns
        -------
        str | None
            Hostname (short name without domain) or None if resolution fails.

        """
        if not ip:
            return None

        self._stats["total_lookups"] += 1

        # Check cache first
        if ip in self._cache:
            entry = self._cache[ip]
            if self._is_cache_valid(entry):
                logger.debug(
                    "Using cached hostname",
                    ip=ip,
                    hostname=entry.hostname,
                    age=int(time.time() - entry.timestamp),
                )
                self._stats["cache_hits"] += 1
                return entry.hostname
            else:
                logger.debug("Cache entry expired", ip=ip, age=int(time.time() - entry.timestamp))
                del self._cache[ip]

        try:
            # Validate IP address
            ipaddress.ip_address(ip)
        except ValueError:
            logger.debug("Invalid IP address format", ip=ip)
            self._cache[ip] = CacheEntry(hostname=None, timestamp=time.time(), client_id=client_id)
            self._stats["failed_lookups"] += 1
            return None

        # Perform reverse DNS lookup with retry
        hostname = await self._retry.execute(
            lambda: self._perform_lookup(ip),
            operation=f"DNS lookup for {ip}",
        )

        # Track success/failure
        if hostname:
            self._stats["successful_lookups"] += 1
            # Extract short hostname (remove domain)
            hostname = hostname.split(".")[0]
        else:
            self._stats["failed_lookups"] += 1

        # Cache the result
        self._cache[ip] = CacheEntry(
            hostname=hostname,
            timestamp=time.time(),
            client_id=client_id,
        )

        return hostname

    async def _perform_lookup(self, ip: str) -> str | None:
        """Perform the actual DNS lookup.

        Parameters
        ----------
        ip : str
            IP address to resolve.

        Returns
        -------
        str | None
            Full hostname or None if resolution fails.

        """
        try:
            # Use custom DNS server if configured
            if self.dns_server:
                return await self._custom_dns_lookup(ip)
            else:
                # Use system default resolver
                return await with_timeout(
                    self._system_dns_lookup(ip),
                    timeout=self.timeout,
                    operation=f"DNS lookup for {ip}",
                    default=None,
                )
        except Exception as e:
            logger.debug("DNS lookup failed", ip=ip, error=str(e))
            return None

    async def _system_dns_lookup(self, ip: str) -> str | None:
        """Perform DNS lookup using system resolver.

        Parameters
        ----------
        ip : str
            IP address to resolve.

        Returns
        -------
        str | None
            Hostname or None if resolution fails.

        """
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            hostname, _, _ = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            logger.debug("Resolved hostname", ip=ip, hostname=hostname)
            return hostname
        except (socket.herror, socket.gaierror, OSError) as e:
            logger.debug("System DNS lookup failed", ip=ip, error=str(e))
            return None

    async def _custom_dns_lookup(self, ip: str) -> str | None:
        """Perform DNS lookup using custom DNS server.

        Parameters
        ----------
        ip : str
            IP address to resolve.

        Returns
        -------
        str | None
            Hostname or None if resolution fails.

        Note
        ----
        This implementation still uses the system resolver but could be
        extended to use a specific DNS library like dnspython if needed.

        """
        # For now, fall back to system resolver
        # Future: Could use dnspython to query specific DNS server
        logger.debug(
            "Custom DNS lookup not fully implemented, using system resolver",
            ip=ip,
            dns_server=self.dns_server,
        )
        return await self._system_dns_lookup(ip)

    async def resolve_multiple(
        self,
        clients: list[tuple[str, str | None, str | None]],
    ) -> dict[str, str | None]:
        """Resolve multiple IP addresses concurrently with client tracking.

        Parameters
        ----------
        clients : list[tuple[str, str | None, str | None]]
            List of (client_id, ip, description) tuples.

        Returns
        -------
        dict[str, str | None]
            Mapping of IP addresses to hostnames.

        """
        if not clients:
            logger.debug("No clients to resolve")
            return {}

        # Track client changes and filter IPs to resolve
        ips_to_resolve = []
        for client_id, ip, description in clients:
            if ip:
                # Track client info changes
                self.track_client(client_id, ip, description)
                ips_to_resolve.append((client_id, ip))

        if not ips_to_resolve:
            return {}

        logger.info(
            "Starting DNS resolution",
            total_clients=len(clients),
            ips_to_resolve=len(ips_to_resolve),
        )

        # Resolve concurrently with limited concurrency (reduced from 10 to 5)
        semaphore = asyncio.Semaphore(5)  # Limit concurrent DNS lookups

        async def resolve_with_limit(client_id: str, ip: str) -> tuple[str, str | None]:
            async with semaphore:
                hostname = await self.resolve_hostname(ip, client_id)
                return ip, hostname

        results = await asyncio.gather(
            *[resolve_with_limit(client_id, ip) for client_id, ip in ips_to_resolve],
            return_exceptions=True,
        )

        # Build result dictionary
        resolved = {}
        successful = 0
        failed = 0
        cached = 0

        for result in results:
            if isinstance(result, Exception):
                logger.debug("DNS resolution error", error=str(result))
                failed += 1
                continue
            if isinstance(result, tuple) and len(result) == 2:
                ip, hostname = result
                resolved[ip] = hostname
                if hostname:
                    successful += 1
                else:
                    failed += 1

        # Count cached entries
        for _, ip, _ in clients:
            if ip and ip in self._cache and self._is_cache_valid(self._cache[ip]):
                cached += 1

        logger.info(
            "Completed DNS resolution batch",
            total=len(clients),
            resolved=successful,
            failed=failed,
            cached=cached,
            cache_size=len(self._cache),
        )

        return resolved

    def clear_cache(self) -> None:
        """Clear the DNS cache."""
        old_size = len(self._cache)
        self._cache.clear()
        self._client_tracking.clear()
        # Reset statistics
        self._stats = {
            "total_lookups": 0,
            "successful_lookups": 0,
            "failed_lookups": 0,
            "cache_hits": 0,
        }
        logger.info("DNS cache cleared", entries_cleared=old_size)

    @property
    def cache_size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns
        -------
        dict[str, int]
            Cache statistics including size, valid entries, and expired entries.

        """
        total = len(self._cache)
        valid = 0
        expired = 0

        current_time = time.time()
        for entry in self._cache.values():
            if current_time - entry.timestamp < self.cache_ttl:
                valid += 1
            else:
                expired += 1

        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": expired,
            "tracked_clients": len(self._client_tracking),
            "cache_ttl_seconds": self.cache_ttl,
            "total_lookups": self._stats["total_lookups"],
            "successful_lookups": self._stats["successful_lookups"],
            "failed_lookups": self._stats["failed_lookups"],
            "cache_hits": self._stats["cache_hits"],
        }

    def get_lookup_stats(self) -> dict[str, int]:
        """Get DNS lookup statistics.

        Returns
        -------
        dict[str, int]
            DNS lookup statistics.

        """
        return self._stats.copy()
