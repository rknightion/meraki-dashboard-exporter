"""Base SNMP collector providing common functionality."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pysnmp.hlapi.v3arch.asyncio import (  # type: ignore[import-untyped]
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    Udp6TransportTarget,
    UdpTransportTarget,
    UsmUserData,
    bulk_cmd,
    get_cmd,
)

from ...core.constants import UpdateTier
from ...core.logging import get_logger
from ...core.logging_helpers import LogContext

if TYPE_CHECKING:
    from typing import TypedDict

    from ...core.config import Settings

    class ErrorDetails(TypedDict):
        """Error details for structured error handling."""

        error_type: str
        error_message: str
        collector: str
        context: dict[str, Any]


logger = get_logger(__name__)


class BaseSNMPCollector(ABC):
    """Base class for SNMP collectors.

    Note: This doesn't inherit from MetricCollector because SNMP collectors
    are managed differently and don't use the Meraki API directly.

    Attributes
    ----------
    update_tier : UpdateTier
        Determines collection frequency (FAST/MEDIUM/SLOW).
        Set this in subclasses to control update frequency.

    """

    # Default to MEDIUM tier - subclasses should override as needed
    update_tier: UpdateTier = UpdateTier.MEDIUM

    def __init__(self, parent: Any, config: Settings) -> None:
        """Initialize SNMP collector.

        Parameters
        ----------
        parent : Any
            Parent coordinator that has metric creation methods.
        config : Settings
            Application configuration.

        """
        self.parent = parent
        self.config = config
        self.snmp_engine = SnmpEngine()
        self.snmp_timeout = config.snmp.timeout
        self.snmp_retries = config.snmp.retries
        self.bulk_max_repetitions = config.snmp.bulk_max_repetitions
        # Error handling is done via decorators
        self._initialize_metrics()

    @abstractmethod
    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for the collector."""

    @abstractmethod
    async def collect_snmp_metrics(self, target: dict[str, Any]) -> None:
        """Collect SNMP metrics from a target.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target information including host, auth details, and metadata.

        """

    async def snmp_get(
        self,
        target: dict[str, Any],
        *oids: str | tuple[int, ...] | ObjectType,
    ) -> list[tuple[str, Any]] | None:
        """Perform SNMP GET operation.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        *oids : str | tuple[int, ...] | ObjectType
            OIDs to retrieve.

        Returns
        -------
        list[tuple[str, Any]] | None
            List of (OID, value) tuples or None on error.

        """
        try:
            transport = await self._create_transport(target)
            auth_data = self._create_auth_data(target)

            # Convert OIDs to ObjectType instances
            object_types = []
            for oid in oids:
                if isinstance(oid, ObjectType):
                    object_types.append(oid)
                elif isinstance(oid, (str, tuple)):
                    object_types.append(ObjectType(ObjectIdentity(oid)))
                else:
                    with LogContext(oid_type=type(oid).__name__):
                        logger.warning("Invalid OID type in SNMP GET")
                    continue

            error_indication, error_status, error_index, var_binds = await get_cmd(
                self.snmp_engine,
                auth_data,
                transport,
                ContextData(),
                *object_types,
            )

            if error_indication:
                with LogContext(
                    host=target.get("host", "unknown"),
                    version=target.get("version", "v2c"),
                    error=str(error_indication),
                ):
                    logger.warning("SNMP GET operation failed")
                return None

            if error_status:
                with LogContext(
                    host=target.get("host", "unknown"),
                    error_status=error_status.prettyPrint(),
                    error_index=error_index,
                ):
                    logger.warning("SNMP GET error status")
                return None

            # Extract results
            results = []
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = self._parse_value(var_bind[1])
                results.append((oid_str, value))

            return results

        except Exception as e:
            error_details: ErrorDetails = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "collector": self.__class__.__name__,
                "context": {"target": target.get("host", "unknown")},
            }
            logger.error(
                "SNMP GET operation failed",
                **error_details["context"],
                error_type=error_details["error_type"],
                error=error_details["error_message"],
            )
            return None

    async def snmp_bulk(
        self,
        target: dict[str, Any],
        oid: str | tuple[int, ...],
        non_repeaters: int = 0,
    ) -> list[tuple[str, Any]] | None:
        """Perform SNMP BULK operation.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        oid : str | tuple[int, ...]
            Starting OID for bulk walk.
        non_repeaters : int, optional
            Number of non-repeating OIDs (default: 0).

        Returns
        -------
        list[tuple[str, Any]] | None
            List of (OID, value) tuples or None on error.

        """
        try:
            transport = await self._create_transport(target)
            auth_data = self._create_auth_data(target)

            object_type = ObjectType(ObjectIdentity(oid))

            error_indication, error_status, error_index, var_binds = await bulk_cmd(
                self.snmp_engine,
                auth_data,
                transport,
                ContextData(),
                non_repeaters,
                self.bulk_max_repetitions,
                object_type,
            )

            if error_indication:
                with LogContext(
                    host=target.get("host", "unknown"),
                    version=target.get("version", "v2c"),
                    error=str(error_indication),
                ):
                    logger.warning("SNMP BULK operation failed")
                return None

            if error_status:
                with LogContext(
                    host=target.get("host", "unknown"),
                    error_status=error_status.prettyPrint(),
                ):
                    logger.warning("SNMP BULK error status")
                return None

            # Extract results
            results = []
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = self._parse_value(var_bind[1])
                results.append((oid_str, value))

            return results

        except Exception as e:
            error_details: ErrorDetails = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "collector": self.__class__.__name__,
                "context": {"target": target.get("host", "unknown")},
            }
            logger.error(
                "SNMP GET operation failed",
                **error_details["context"],
                error_type=error_details["error_type"],
                error=error_details["error_message"],
            )
            return None

    async def _create_transport(
        self, target: dict[str, Any]
    ) -> UdpTransportTarget | Udp6TransportTarget:
        """Create SNMP transport.

        Parameters
        ----------
        target : dict[str, Any]
            Target configuration with host and port.

        Returns
        -------
        UdpTransportTarget | Udp6TransportTarget
            SNMP transport instance.

        """
        host = target["host"]
        port = target.get("port", 161)

        # Check if IPv6
        if ":" in host and "[" not in host:
            # IPv6 address
            return await Udp6TransportTarget.create(
                (host, port),
                timeout=self.snmp_timeout,
                retries=self.snmp_retries,
            )
        else:
            # IPv4 or hostname
            return await UdpTransportTarget.create(
                (host, port),
                timeout=self.snmp_timeout,
                retries=self.snmp_retries,
            )

    def _create_auth_data(self, target: dict[str, Any]) -> CommunityData | UsmUserData:
        """Create SNMP authentication data.

        Parameters
        ----------
        target : dict[str, Any]
            Target configuration with auth details.

        Returns
        -------
        CommunityData | UsmUserData
            SNMP authentication instance.

        """
        version = target.get("version", "v2c")

        if version == "v2c":
            # SNMPv2c only
            community = target.get("community", "public")
            return CommunityData(community, mpModel=1)
        else:
            # SNMPv3
            username = target.get("username", "")
            auth_key = target.get("auth_key")
            priv_key = target.get("priv_key")
            auth_protocol = target.get("auth_protocol", "SHA")
            priv_protocol = target.get("priv_protocol", "AES128")

            return UsmUserData(
                username,
                authKey=auth_key,
                privKey=priv_key,
                authProtocol=auth_protocol,
                privProtocol=priv_protocol,
            )

    def _parse_value(self, value: Any) -> Any:
        """Parse SNMP value to Python type.

        Parameters
        ----------
        value : Any
            SNMP value object.

        Returns
        -------
        Any
            Parsed value.

        """
        # Get string representation
        value_str = value.prettyPrint()

        # Try to determine type and convert
        value_type = value.__class__.__name__

        with LogContext(
            snmp_value_type=value_type,
            raw_value=str(value_str)[:100],  # Truncate for logging
        ):
            logger.debug("Parsing SNMP value")

        if value_type in {"Integer32", "Integer", "Unsigned32", "Gauge32", "Counter32"}:
            try:
                return int(value)
            except (ValueError, TypeError):
                return value_str

        elif value_type == "Counter64":
            try:
                return int(value)
            except (ValueError, TypeError):
                return value_str

        elif value_type == "TimeTicks":
            # TimeTicks are in hundredths of a second
            try:
                return int(value) / 100.0
            except (ValueError, TypeError):
                return value_str

        elif value_type == "OctetString":
            # Check if it's a MAC address (6 bytes)
            if len(value) == 6:
                return ":".join(f"{b:02x}" for b in value)
            # Otherwise return as string
            return value_str

        else:
            # Default to string representation
            return value_str

    async def _process_snmp_targets(
        self, targets: list[dict[str, Any]], concurrent_limit: int
    ) -> None:
        """Process multiple SNMP targets concurrently.

        Parameters
        ----------
        targets : list[dict[str, Any]]
            List of SNMP targets to process.
        concurrent_limit : int
            Maximum concurrent SNMP operations.

        """
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_target(target: dict[str, Any]) -> None:
            async with semaphore:
                await self.collect_snmp_metrics(target)

        tasks = [process_target(target) for target in targets]
        await asyncio.gather(*tasks, return_exceptions=True)
