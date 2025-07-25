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

        # Log initialization
        tier_value = "unknown"
        if hasattr(self, "update_tier"):
            tier_value = self.update_tier.value

        with LogContext(
            coordinator=self.__class__.__name__,
            tier=tier_value,
            snmp_enabled=settings.snmp.enabled,
        ):
            logger.info("Initializing SNMP coordinator")

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

        # Connection state tracking to avoid retrying failed methods
        self._org_snmp_versions: dict[str, str] = {}  # org_id -> working version
        self._failed_org_v3: set[str] = set()  # org_ids where v3 failed
        self._device_connectivity_tested = False

        # Only run startup tests from FAST coordinator to avoid duplicates
        # (since all our collectors are now in FAST tier by default)
        if self.enabled and getattr(self, "update_tier", None) == UpdateTier.FAST:
            asyncio.create_task(self._run_startup_tests())

    async def _run_startup_tests(self) -> None:
        """Run SNMP connectivity tests on startup."""
        await asyncio.sleep(2)  # Small delay to let other components initialize

        with LogContext(component="SNMP"):
            logger.info("Running SNMP connectivity tests...")

        try:
            # Test organization SNMP
            orgs = await self._get_organizations()
            if orgs:
                org = orgs[0]  # Test with first org
                org_snmp = await self._get_org_snmp_settings(org["id"])
                if org_snmp and (org_snmp.get("v2cEnabled") or org_snmp.get("v3Enabled")):
                    await self._test_org_snmp_connectivity(org, org_snmp)

                # Test device SNMP (only if we're a tier that handles devices)
                if hasattr(self, "collectors") and self.collectors:
                    from .device_snmp import MRDeviceSNMPCollector, MSDeviceSNMPCollector

                    has_device_collectors = any(
                        isinstance(c, (MRDeviceSNMPCollector, MSDeviceSNMPCollector))
                        for c in self.collectors
                    )
                    if has_device_collectors:
                        await self._test_device_snmp_connectivity(org)

        except Exception as e:
            logger.error(f"SNMP startup tests failed: {e}")

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
        with LogContext(
            coordinator=self.__class__.__name__,
            tier=getattr(self, "update_tier", UpdateTier.FAST).value,
        ):
            logger.debug("SNMP collection starting")

        if not self.enabled:
            with LogContext(
                coordinator=self.__class__.__name__,
                tier=getattr(self, "update_tier", UpdateTier.FAST).value,
            ):
                logger.debug("SNMP collection skipped - disabled")
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
                    logger.debug("Organization SNMP peer IPs configured")

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
        # Check if SNMP is enabled at all
        if not org_snmp.get("v2cEnabled") and not org_snmp.get("v3Enabled"):
            with LogContext(org_id=org["id"], org_name=org["name"]):
                logger.warning(
                    "Organization SNMP is disabled. Please enable SNMP in Meraki Dashboard: "
                    "Organization > Settings > SNMP"
                )
            return

        # Build SNMP target configuration
        target = {
            "host": org_snmp.get("hostname", "snmp.meraki.com"),
            "port": org_snmp.get("port", 16100),
            "org_id": org["id"],
            "org_name": org["name"],
        }

        # Check if we already know which version works from startup tests
        org_id = org["id"]
        if org_id in self._org_snmp_versions:
            working_version = self._org_snmp_versions[org_id]
            if working_version == "v3":
                target["version"] = "v3"
                target["username"] = org_snmp.get("v3User", "")
                target["auth_protocol"] = org_snmp.get("v3AuthMode", "SHA")
                target["priv_protocol"] = org_snmp.get("v3PrivMode", "AES128")
                if self.settings.snmp.org_v3_auth_password:
                    target["auth_key"] = self.settings.snmp.org_v3_auth_password.get_secret_value()
                if self.settings.snmp.org_v3_priv_password:
                    target["priv_key"] = self.settings.snmp.org_v3_priv_password.get_secret_value()
            else:  # v2c
                target["version"] = "v2c"
                target["community"] = org_snmp.get("v2CommunityString", "public")
        # No cached version, determine which to use
        # Skip v3 if we know it failed before
        elif org_snmp.get("v3Enabled") and org_id not in self._failed_org_v3:
            # Use SNMPv3
            target["version"] = "v3"
            target["username"] = org_snmp.get("v3User", "")
            target["auth_protocol"] = org_snmp.get("v3AuthMode", "SHA")
            target["priv_protocol"] = org_snmp.get("v3PrivMode", "AES128")

            # Get auth/priv passwords from environment variables
            if self.settings.snmp.org_v3_auth_password:
                target["auth_key"] = self.settings.snmp.org_v3_auth_password.get_secret_value()
            if self.settings.snmp.org_v3_priv_password:
                target["priv_key"] = self.settings.snmp.org_v3_priv_password.get_secret_value()

            # Log warning if passwords not configured
            if not target.get("auth_key") or not target.get("priv_key"):
                with LogContext(org_id=org["id"], org_name=org["name"]):
                    logger.warning(
                        "SNMPv3 passwords not configured. Set environment variables: "
                        "MERAKI_EXPORTER_SNMP__ORG_V3_AUTH_PASSWORD and "
                        "MERAKI_EXPORTER_SNMP__ORG_V3_PRIV_PASSWORD"
                    )

            # Set v2c as fallback if available
            if org_snmp.get("v2cEnabled"):
                v2_community = org_snmp.get("v2CommunityString", "")
                target["v2c_fallback"] = {"version": "v2c", "community": v2_community or "public"}
        elif org_snmp.get("v2cEnabled"):
            # Use SNMPv2c
            target["version"] = "v2c"
            target["community"] = org_snmp.get("v2CommunityString", "public")

        # Get device information from API to enrich SNMP data
        devices = await self._get_org_devices(org["id"])

        # Get all networks for the organization once
        networks_cache = {}
        try:
            networks = await self.client.get_networks(org["id"])
            for network in networks:
                networks_cache[network["id"]] = network
        except Exception as e:
            with LogContext(org_id=org["id"], error=str(e)):
                logger.warning("Failed to fetch networks for device enrichment")

        # Create a device map for MAC -> device info lookup
        device_map = {}

        for device in devices:
            mac = device.get("mac", "")
            if mac:
                # Normalize MAC address (remove colons, lowercase)
                normalized_mac = mac.lower().replace(":", "")

                # Get network info from cache
                network_id = device.get("networkId")
                network_info = networks_cache.get(network_id, {"id": network_id, "name": "Unknown"})

                # Store device with network info
                device_map[normalized_mac] = {"device": device, "network": network_info}

        target["device_map"] = device_map

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
                # For network devices, the passphrase is used as both auth and priv key
                passphrase = user.get("passphrase", "")
                if passphrase:
                    target["auth_key"] = passphrase
                    target["priv_key"] = passphrase
                # Default protocols for network devices (not specified in API)
                target["auth_protocol"] = "SHA"
                target["priv_protocol"] = "AES128"
        else:
            # SNMPv2c (access == "community")
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

    async def _test_org_snmp_connectivity(
        self, org: dict[str, Any], org_snmp: dict[str, Any]
    ) -> None:
        """Test organization SNMP connectivity on startup."""
        org_id = org["id"]
        org_name = org["name"]

        # Build test target
        target = {
            "host": org_snmp.get("hostname", "snmp.meraki.com"),
            "port": org_snmp.get("port", 16100),
            "org_id": org_id,
            "org_name": org_name,
        }

        # Try v3 first if enabled
        if org_snmp.get("v3Enabled") and org_id not in self._failed_org_v3:
            target["version"] = "v3"
            target["username"] = org_snmp.get("v3User", "")
            target["auth_protocol"] = org_snmp.get("v3AuthMode", "SHA")
            target["priv_protocol"] = org_snmp.get("v3PrivMode", "AES128")

            has_auth_key = False
            has_priv_key = False

            if self.settings.snmp.org_v3_auth_password:
                target["auth_key"] = self.settings.snmp.org_v3_auth_password.get_secret_value()
                has_auth_key = True
            if self.settings.snmp.org_v3_priv_password:
                target["priv_key"] = self.settings.snmp.org_v3_priv_password.get_secret_value()
                has_priv_key = True

            # Warn if v3 is enabled but credentials are missing
            if not has_auth_key or not has_priv_key:
                with LogContext(
                    org_id=org_id,
                    org_name=org_name,
                    has_auth_key=has_auth_key,
                    has_priv_key=has_priv_key,
                    v3_user=target["username"],
                ):
                    logger.warning(
                        "Organization SNMPv3 is enabled but authentication credentials are missing. "
                        "Set environment variables MERAKI_EXPORTER_SNMP__ORG_V3_AUTH_PASSWORD and "
                        "MERAKI_EXPORTER_SNMP__ORG_V3_PRIV_PASSWORD"
                    )

            # Test v3
            from .cloud_controller import CloudControllerSNMPCollector

            test_collector = CloudControllerSNMPCollector(self, self.settings)
            result = await test_collector.snmp_get(target, "1.3.6.1.2.1.1.1.0")  # sysDescr

            if result:
                self._org_snmp_versions[org_id] = "v3"
                with LogContext(org_id=org_id, org_name=org_name):
                    logger.info("Organization SNMP connectivity test passed (v3)")
                return
            else:
                self._failed_org_v3.add(org_id)
                if org_snmp.get("v2cEnabled"):
                    with LogContext(org_id=org_id, org_name=org_name):
                        logger.info("Organization SNMPv3 failed, will use v2c fallback")

        # Try v2c if enabled
        if org_snmp.get("v2cEnabled"):
            target = {
                "host": org_snmp.get("hostname", "snmp.meraki.com"),
                "port": org_snmp.get("port", 16100),
                "org_id": org_id,
                "org_name": org_name,
                "version": "v2c",
                "community": org_snmp.get("v2CommunityString", "public"),
            }

            from .cloud_controller import CloudControllerSNMPCollector

            test_collector = CloudControllerSNMPCollector(self, self.settings)
            result = await test_collector.snmp_get(target, "1.3.6.1.2.1.1.1.0")  # sysDescr

            if result:
                self._org_snmp_versions[org_id] = "v2c"
                with LogContext(org_id=org_id, org_name=org_name):
                    logger.info("Organization SNMP connectivity test passed (v2c)")
            else:
                with LogContext(org_id=org_id, org_name=org_name):
                    logger.warning("Organization SNMP connectivity test failed for both v3 and v2c")

    async def _test_device_snmp_connectivity(self, org: dict[str, Any]) -> None:
        """Test device SNMP connectivity on startup."""
        if self._device_connectivity_tested:
            return

        org_id = org["id"]
        networks = await self.client.get_networks(org_id)

        tested_count = 0
        successful = False

        for network in networks:
            if tested_count >= 3:
                break

            network_snmp = await self._get_network_snmp_settings(network["id"])
            if not network_snmp or network_snmp.get("access") == "none":
                continue

            devices = await self.client.get_network_devices(network["id"])
            test_devices = [d for d in devices if d.get("model", "").startswith(("MR", "MS"))]

            if not test_devices:
                continue

            device = test_devices[0]
            tested_count += 1

            # Build test target
            target = self._build_device_target(
                device,
                network,
                org,
                network_snmp,
                DeviceType.MR if device["model"].startswith("MR") else DeviceType.MS,
            )

            if target:
                # Test connectivity
                from .device_snmp import MRDeviceSNMPCollector, MSDeviceSNMPCollector

                collector_class = (
                    MRDeviceSNMPCollector
                    if device["model"].startswith("MR")
                    else MSDeviceSNMPCollector
                )
                test_collector = collector_class(self, self.settings)
                result = await test_collector.snmp_get(target, "1.3.6.1.2.1.1.1.0")  # sysDescr

                if result:
                    successful = True
                    with LogContext(
                        device_name=device.get("name", "unknown"),
                        device_model=device["model"],
                        network_name=network["name"],
                    ):
                        logger.info("Device SNMP connectivity test passed")
                    break
                else:
                    with LogContext(
                        device_name=device.get("name", "unknown"),
                        device_model=device["model"],
                        network_name=network["name"],
                    ):
                        logger.warning("Device SNMP connectivity test failed")

        self._device_connectivity_tested = True

        if not successful and tested_count > 0:
            logger.warning(
                f"Device SNMP connectivity tests failed for all {tested_count} devices tested. "
                "Check network SNMP settings and device accessibility."
            )


@register_collector()
class SNMPFastCoordinator(BaseSNMPCoordinator):
    """SNMP coordinator for fast-updating metrics (60s default).

    Use this for:
    - Real-time interface counters
    - Critical status metrics
    - Metrics that change frequently
    """

    update_tier = UpdateTier.FAST

    def __init__(self, api: DashboardAPI, settings: Settings) -> None:
        """Initialize SNMP fast coordinator with startup trigger."""
        super().__init__(api, settings)
        # Trigger initial collection after a short delay
        if self.enabled:
            asyncio.create_task(self._trigger_initial_collection())

    def _init_tier_collectors(self) -> None:
        """Initialize FAST tier collectors - all SNMP metrics default to FAST."""
        # Import here to avoid circular imports
        from .cloud_controller import CloudControllerSNMPCollector
        from .device_snmp import MRDeviceSNMPCollector, MSDeviceSNMPCollector

        # All SNMP collectors default to FAST tier for real-time monitoring
        self.collectors = [
            CloudControllerSNMPCollector(self, self.settings),
            MRDeviceSNMPCollector(self, self.settings),
            MSDeviceSNMPCollector(self, self.settings),
        ]

        with LogContext(
            coordinator=self.__class__.__name__,
            tier="fast",
            collector_count=len(self.collectors),
        ):
            logger.info("Initialized FAST tier collectors")

    async def _trigger_initial_collection(self) -> None:
        """Trigger initial collection after startup."""
        await asyncio.sleep(5)  # Wait for other components to initialize
        with LogContext(tier="fast", component="SNMP"):
            logger.info("Triggering initial FAST tier SNMP collection")
        await self._collect_impl()

    async def _collect_impl(self) -> None:
        """Collect fast SNMP metrics."""
        with LogContext(
            coordinator=self.__class__.__name__,
            tier="fast",
            enabled=self.enabled,
        ):
            logger.debug("FAST tier SNMP collection called")

        if not self.enabled:
            return

        # Run base implementation to collect from all registered collectors
        await super()._collect_impl()


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
        # All SNMP collectors have moved to FAST tier by default
        # Only add collectors here that specifically need slower updates
        self.collectors = []


@register_collector()
class SNMPSlowCoordinator(BaseSNMPCoordinator):
    """SNMP coordinator for slow-updating metrics (900s default).

    Use this for:
    - System information (sysDescr, etc.)
    - Hardware inventory
    - Configuration-related metrics
    """

    update_tier = UpdateTier.SLOW

    def __init__(self, api: DashboardAPI, settings: Settings) -> None:
        """Initialize SNMP slow coordinator with startup trigger."""
        super().__init__(api, settings)
        # Trigger initial collection after a short delay
        if self.enabled:
            asyncio.create_task(self._trigger_initial_collection())

    def _init_tier_collectors(self) -> None:
        """Initialize only slow-updating collectors."""
        # For now, no collectors are assigned to SLOW tier
        # Add collectors here as metrics are identified for slow updates
        self.collectors = []

    async def _trigger_initial_collection(self) -> None:
        """Trigger initial collection after startup."""
        await asyncio.sleep(10)  # Wait longer for other components
        with LogContext(tier="slow", component="SNMP"):
            logger.info("Triggering initial SLOW tier SNMP collection")
        await self._collect_impl()

    async def _collect_impl(self) -> None:
        """Collect slow SNMP metrics."""
        if not self.enabled:
            return

        # For now, no slow metrics implemented
        # Will be expanded as slow metrics are identified
        with LogContext(tier="slow", component="SNMP"):
            logger.debug("SLOW tier SNMP collection (no collectors configured yet)")
        pass
