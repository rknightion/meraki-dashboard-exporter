"""SNMP coordinator that manages all SNMP collectors."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...api.client import AsyncMerakiClient
from ...core.collector import MetricCollector
from ...core.constants import UpdateTier
from ...core.constants.device_constants import DeviceType
from ...core.logging import get_logger
from ...core.logging_helpers import LogContext
from ...core.registry import register_collector

if TYPE_CHECKING:
    from typing import TypedDict

    from meraki import DashboardAPI

    from ...core.config import Settings
    from .base import BaseSNMPCollector

    class ErrorDetails(TypedDict):
        """Error details for structured error handling."""

        error_type: str
        error_message: str
        collector: str
        context: dict[str, Any]


logger = get_logger(__name__)


class BaseSNMPCoordinator(MetricCollector):
    """Base coordinator for SNMP collectors.

    The update tier determines how frequently SNMP collection runs:
    - FAST: settings.update_intervals.fast (default 60s)
    - MEDIUM: settings.update_intervals.medium (default 300s)
    - SLOW: settings.update_intervals.slow (default 900s)
    """

    # Subclasses must set this
    update_tier: UpdateTier

    def __init__(self, api: DashboardAPI, settings: Settings) -> None:
        """Initialize SNMP coordinator.

        Parameters
        ----------
        api : DashboardAPI
            Meraki Dashboard API client.
        settings : Settings
            Application settings.

        """
        super().__init__(api, settings)
        self.client = AsyncMerakiClient(settings)
        # Error handling done via decorators

        # Check if SNMP is enabled
        if not settings.snmp.enabled:
            with LogContext(snmp_enabled=False):
                logger.info("SNMP collection is disabled")
            self.enabled = False
            return

        self.enabled = True

        # Initialize sub-collectors
        # Initialize collectors based on update tier
        self.collectors: list[BaseSNMPCollector] = []
        self._init_tier_collectors()

        # SNMP configuration
        self.concurrent_device_limit = settings.snmp.concurrent_device_limit
        # Note: device_discovery_interval is not used since we re-discover on each collection
        # The collection frequency is controlled by update_tier (MEDIUM = 300s by default)

        # Cache for SNMP credentials and device info
        self._snmp_cache: dict[str, Any] = {}
        self._last_discovery_time = 0

    def _init_tier_collectors(self) -> None:
        """Initialize collectors for this tier. Override in subclasses."""
        # Subclasses should initialize their collectors
        pass

    def _initialize_metrics(self) -> None:
        """Initialize metrics (required by MetricCollector)."""
        # Metrics are initialized in sub-collectors
        pass

    async def _collect_impl(self) -> None:
        """Collect SNMP metrics from all sources."""
        if not self.enabled:
            return

        try:
            # Get organizations
            orgs = await self._get_organizations()
            if not orgs:
                with LogContext(collector="SNMPCoordinator"):
                    logger.warning("No organizations found for SNMP collection")
                return

            # Collect from each organization
            for org in orgs:
                await self._collect_org_snmp(org)

        except Exception as e:
            error_details: ErrorDetails = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "collector": self.__class__.__name__,
                "context": {"action": "collect"},
            }
            logger.error(
                "SNMP collection failed",
                **error_details["context"],
                error_type=error_details["error_type"],
                error=error_details["error_message"],
            )

    async def _get_organizations(self) -> list[dict[str, Any]]:
        """Get organizations to collect from.

        Returns
        -------
        list[dict[str, Any]]
            List of organization information.

        """
        if self.settings.meraki.org_id:
            # Single organization configured
            org = await self.client.get_organization(self.settings.meraki.org_id)
            return [org] if org else []
        else:
            # Get all organizations
            return await self.client.get_organizations()

    async def _collect_org_snmp(self, org: dict[str, Any]) -> None:
        """Collect SNMP metrics for an organization.

        Parameters
        ----------
        org : dict[str, Any]
            Organization information.

        """
        org_id = org["id"]
        org_name = org["name"]

        try:
            # Get organization SNMP settings
            org_snmp = await self._get_org_snmp_settings(org_id)
            if not org_snmp:
                with LogContext(org_id=org_id, org_name=org_name):
                    logger.debug("No SNMP settings for organization")
                return

            # Log peer IPs for visibility
            peer_ips = org_snmp.get("peerIps", [])
            if peer_ips:
                with LogContext(
                    org_id=org_id,
                    org_name=org_name,
                    peer_ips=peer_ips,
                    peer_ip_count=len(peer_ips),
                ):
                    logger.info("Organization SNMP peer IPs configured")

            # Collect metrics based on the tier's collectors
            await self._collect_tier_metrics(org, org_snmp)

        except Exception as e:
            error_details: ErrorDetails = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "collector": self.__class__.__name__,
                "context": {"org_id": org_id, "org_name": org_name},
            }
            logger.error(
                "SNMP collection failed",
                **error_details["context"],
                error_type=error_details["error_type"],
                error=error_details["error_message"],
            )

    async def _get_org_snmp_settings(self, org_id: str) -> dict[str, Any] | None:
        """Get organization SNMP settings.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any] | None
            SNMP settings or None if not available.

        """
        try:
            return await self.client.get_organization_snmp(org_id)
        except Exception as e:
            with LogContext(
                org_id=org_id,
                error_type=type(e).__name__,
                error=str(e),
            ):
                logger.debug("Failed to get SNMP settings for organization")
            return None

    async def _collect_tier_metrics(self, org: dict[str, Any], org_snmp: dict[str, Any]) -> None:
        """Collect metrics from all collectors registered for this tier.

        Parameters
        ----------
        org : dict[str, Any]
            Organization information.
        org_snmp : dict[str, Any]
            Organization SNMP settings.

        """
        # Collect cloud controller metrics if we have the collector
        if hasattr(self, "collectors"):
            # Import here to avoid circular imports
            from .cloud_controller import CloudControllerSNMPCollector
            from .device_snmp import MRDeviceSNMPCollector, MSDeviceSNMPCollector

            for collector in self.collectors:
                if isinstance(collector, CloudControllerSNMPCollector):
                    await self._collect_cloud_controller_snmp(org, org_snmp)
                elif isinstance(collector, (MRDeviceSNMPCollector, MSDeviceSNMPCollector)):
                    # Device collectors need device-specific handling
                    await self._collect_device_snmp(org)

    async def _collect_cloud_controller_snmp(
        self, org: dict[str, Any], org_snmp: dict[str, Any]
    ) -> None:
        """Collect metrics from cloud controller SNMP.

        Parameters
        ----------
        org : dict[str, Any]
            Organization information.
        org_snmp : dict[str, Any]
            Organization SNMP settings.

        """
        if not org_snmp.get("v2cEnabled") and not org_snmp.get("v3Enabled"):
            with LogContext(org_id=org["id"], org_name=org["name"]):
                logger.debug("SNMP not enabled for organization")
            return

        # Build SNMP target configuration
        target = {
            "host": org_snmp.get("hostname", "snmp.meraki.com"),
            "port": org_snmp.get("port", 16100),
            "org_id": org["id"],
            "org_name": org["name"],
        }

        # Add authentication based on enabled version
        if org_snmp.get("v3Enabled"):
            # Use SNMPv3
            target["version"] = "v3"
            target["username"] = org_snmp.get("v3User", "")
            # Note: We don't have auth/priv keys from the API
            # In a real implementation, these would need to be configured separately
            target["auth_protocol"] = org_snmp.get("v3AuthMode", "SHA")
            target["priv_protocol"] = org_snmp.get("v3PrivMode", "AES128")
        elif org_snmp.get("v2cEnabled"):
            # Use SNMPv2c
            target["version"] = "v2c"
            target["community"] = org_snmp.get("v2CommunityString", "public")

        # Get device information for cloud controller
        devices = await self._get_org_devices(org["id"])
        target["devices"] = devices

        # Collect metrics from the cloud controller collector in this tier
        from .cloud_controller import CloudControllerSNMPCollector

        for collector in self.collectors:
            if isinstance(collector, CloudControllerSNMPCollector):
                await collector.collect_snmp_metrics(target)
                break

    async def _collect_device_snmp(self, org: dict[str, Any]) -> None:
        """Collect SNMP metrics directly from devices.

        Parameters
        ----------
        org : dict[str, Any]
            Organization information.

        """
        # Get all networks in the organization
        networks = await self.client.get_networks(org["id"])

        # Process each network
        tasks = []
        for network in networks:
            task = self._collect_network_device_snmp(org, network)
            tasks.append(task)

        # Run network collections concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _collect_network_device_snmp(
        self, org: dict[str, Any], network: dict[str, Any]
    ) -> None:
        """Collect SNMP metrics from devices in a network.

        Parameters
        ----------
        org : dict[str, Any]
            Organization information.
        network : dict[str, Any]
            Network information.

        """
        network_id = network["id"]
        network_name = network["name"]

        # Get network SNMP settings
        network_snmp = await self._get_network_snmp_settings(network_id)
        if not network_snmp or network_snmp.get("access") == "none":
            with LogContext(
                network_id=network_id,
                network_name=network_name,
                snmp_access=network_snmp.get("access", "none") if network_snmp else "none",
            ):
                logger.debug("SNMP not enabled for network")
            return

        # Get devices in the network
        devices = await self.client.get_network_devices(network_id)

        # Filter for MR and MS devices
        mr_devices = [d for d in devices if d.get("model", "").startswith("MR")]
        ms_devices = [d for d in devices if d.get("model", "").startswith("MS")]

        # Collect from each device type
        tasks = []

        # Import device collectors
        from .device_snmp import MRDeviceSNMPCollector, MSDeviceSNMPCollector

        # Find the appropriate collectors in this tier
        mr_collector = None
        ms_collector = None
        for collector in self.collectors:
            if isinstance(collector, MRDeviceSNMPCollector):
                mr_collector = collector
            elif isinstance(collector, MSDeviceSNMPCollector):
                ms_collector = collector

        # MR devices
        if mr_collector:
            for device in mr_devices:
                target = self._build_device_target(
                    device, network, org, network_snmp, DeviceType.MR
                )
                if target:
                    tasks.append(mr_collector.collect_snmp_metrics(target))

        # MS devices
        if ms_collector:
            for device in ms_devices:
                target = self._build_device_target(
                    device, network, org, network_snmp, DeviceType.MS
                )
                if target:
                    tasks.append(ms_collector.collect_snmp_metrics(target))

        # Process devices with concurrency limit
        if tasks:
            # Create task objects from coroutines
            task_objects = [asyncio.create_task(coro) for coro in tasks]
            await self._process_with_limit(task_objects, self.concurrent_device_limit)

    async def _get_network_snmp_settings(self, network_id: str) -> dict[str, Any] | None:
        """Get network SNMP settings.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        dict[str, Any] | None
            SNMP settings or None if not available.

        """
        try:
            return await self.client.get_network_snmp(network_id)
        except Exception as e:
            with LogContext(
                network_id=network_id,
                error_type=type(e).__name__,
                error=str(e),
            ):
                logger.debug("Failed to get SNMP settings for network")
            return None

    def _build_device_target(
        self,
        device: dict[str, Any],
        network: dict[str, Any],
        org: dict[str, Any],
        network_snmp: dict[str, Any],
        device_type: DeviceType,
    ) -> dict[str, Any] | None:
        """Build SNMP target configuration for a device.

        Parameters
        ----------
        device : dict[str, Any]
            Device information.
        network : dict[str, Any]
            Network information.
        org : dict[str, Any]
            Organization information.
        network_snmp : dict[str, Any]
            Network SNMP settings.
        device_type : DeviceType
            Type of device.

        Returns
        -------
        dict[str, Any] | None
            SNMP target configuration or None if device not reachable.

        """
        # Get device IP address
        ip_address = device.get("lanIp") or device.get("wan1Ip")
        if not ip_address:
            with LogContext(
                device_name=device.get("name", "unknown"),
                device_serial=device.get("serial", "unknown"),
                device_model=device.get("model", "unknown"),
            ):
                logger.debug("No IP address for device")
            return None

        # Build target configuration
        target = {
            "host": ip_address,
            "port": 161,  # Standard SNMP port for devices
            "device_info": {
                "org_id": org["id"],
                "org_name": org["name"],
                "network_id": network["id"],
                "network_name": network["name"],
                "serial": device["serial"],
                "name": device.get("name", device["serial"]),
                "mac": device.get("mac", ""),
                "model": device.get("model", ""),
                "device_type": device_type.value,
            },
        }

        # Add authentication
        if network_snmp.get("access") == "users":
            # SNMPv3
            target["version"] = "v3"
            users = network_snmp.get("users", [])
            if users:
                # Use first configured user
                user = users[0]
                target["username"] = user.get("username", "")
                target["passphrase"] = user.get("passphrase", "")
                # Note: Auth/priv protocols would need to be configured
        else:
            # SNMPv1/v2c
            target["version"] = "v2c"
            target["community"] = network_snmp.get("communityString", "public")

        return target

    async def _get_org_devices(self, org_id: str) -> list[dict[str, Any]]:
        """Get all devices in an organization with SNMP index mapping.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of devices with SNMP indices.

        """
        devices = await self.client.get_devices(org_id)

        # Add SNMP index based on device order
        # In real implementation, this would need proper mapping
        for i, device in enumerate(devices):
            device["index"] = i + 1

        return devices

    async def _process_with_limit(self, tasks: list[asyncio.Task[Any]], limit: int) -> None:
        """Process tasks with concurrency limit.

        Parameters
        ----------
        tasks : list[asyncio.Task]
            Tasks to process.
        limit : int
            Maximum concurrent tasks.

        """
        semaphore = asyncio.Semaphore(limit)

        async def run_with_semaphore(task: asyncio.Task[Any]) -> Any:
            async with semaphore:
                return await task

        wrapped_tasks = [run_with_semaphore(task) for task in tasks]
        await asyncio.gather(*wrapped_tasks, return_exceptions=True)


@register_collector()
class SNMPFastCoordinator(BaseSNMPCoordinator):
    """SNMP coordinator for fast-updating metrics (60s default).

    Use this for:
    - Real-time interface counters
    - Critical status metrics
    - Metrics that change frequently
    """

    update_tier = UpdateTier.FAST

    def _init_tier_collectors(self) -> None:
        """Initialize only fast-updating collectors."""
        # For now, no collectors are assigned to FAST tier
        # Add collectors here as metrics are identified for fast updates
        self.collectors = []

    async def _collect_impl(self) -> None:
        """Collect fast SNMP metrics."""
        if not self.enabled:
            return

        # For now, no fast metrics implemented
        # Will be expanded as fast metrics are identified
        pass


@register_collector()
class SNMPMediumCoordinator(BaseSNMPCoordinator):
    """SNMP coordinator for medium-updating metrics (300s default).

    Use this for:
    - Device status and health
    - Client counts
    - Standard operational metrics
    """

    update_tier = UpdateTier.MEDIUM

    def _init_tier_collectors(self) -> None:
        """Initialize medium-updating collectors."""
        # Most SNMP metrics fall into medium tier
        # Import here to avoid circular imports
        from .cloud_controller import CloudControllerSNMPCollector
        from .device_snmp import MRDeviceSNMPCollector, MSDeviceSNMPCollector

        self.collectors = [
            CloudControllerSNMPCollector(self, self.settings),
            MRDeviceSNMPCollector(self, self.settings),
            MSDeviceSNMPCollector(self, self.settings),
        ]


@register_collector()
class SNMPSlowCoordinator(BaseSNMPCoordinator):
    """SNMP coordinator for slow-updating metrics (900s default).

    Use this for:
    - System information (sysDescr, etc.)
    - Hardware inventory
    - Configuration-related metrics
    """

    update_tier = UpdateTier.SLOW

    def _init_tier_collectors(self) -> None:
        """Initialize only slow-updating collectors."""
        # For now, no collectors are assigned to SLOW tier
        # Add collectors here as metrics are identified for slow updates
        self.collectors = []

    async def _collect_impl(self) -> None:
        """Collect slow SNMP metrics."""
        if not self.enabled:
            return

        # For now, no slow metrics implemented
        # Will be expanded as slow metrics are identified
        pass
