"""DNS resolver service for client hostname lookups."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import structlog

from ..core.async_utils import with_timeout
from ..core.config import Settings

logger = structlog.get_logger(__name__)


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
        self._cache: dict[str, str | None] = {}
        self._resolver_configured = False
        self._configure_resolver()

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

    async def resolve_hostname(self, ip: str | None) -> str | None:
        """Resolve hostname from IP address.

        Parameters
        ----------
        ip : str | None
            IP address to resolve.

        Returns
        -------
        str | None
            Hostname (short name without domain) or None if resolution fails.

        """
        if not ip:
            return None

        # Check cache first
        if ip in self._cache:
            logger.debug("Using cached hostname", ip=ip, hostname=self._cache[ip])
            return self._cache[ip]

        try:
            # Validate IP address
            ipaddress.ip_address(ip)
        except ValueError:
            logger.debug("Invalid IP address format", ip=ip)
            self._cache[ip] = None
            return None

        # Perform reverse DNS lookup
        hostname = await self._perform_lookup(ip)

        # Extract short hostname (remove domain)
        if hostname:
            hostname = hostname.split(".")[0]

        # Cache the result
        self._cache[ip] = hostname

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

    async def resolve_multiple(self, ips: list[str]) -> dict[str, str | None]:
        """Resolve multiple IP addresses concurrently.

        Parameters
        ----------
        ips : list[str]
            List of IP addresses to resolve.

        Returns
        -------
        dict[str, str | None]
            Mapping of IP addresses to hostnames.

        """
        # Create tasks for all IPs
        tasks = {ip: self.resolve_hostname(ip) for ip in ips if ip}

        # Resolve concurrently with limited concurrency
        semaphore = asyncio.Semaphore(10)  # Limit concurrent DNS lookups

        async def resolve_with_limit(ip: str) -> tuple[str, str | None]:
            async with semaphore:
                hostname = await self.resolve_hostname(ip)
                return ip, hostname

        results = await asyncio.gather(
            *[resolve_with_limit(ip) for ip in tasks.keys()],
            return_exceptions=True,
        )

        # Build result dictionary
        resolved = {}
        for result in results:
            if isinstance(result, Exception):
                logger.debug("DNS resolution error", error=str(result))
                continue
            if isinstance(result, tuple) and len(result) == 2:
                ip, hostname = result
                resolved[ip] = hostname

        return resolved

    def clear_cache(self) -> None:
        """Clear the DNS cache."""
        self._cache.clear()
        logger.debug("DNS cache cleared")

    @property
    def cache_size(self) -> int:
        """Get current cache size."""
        return len(self._cache)
