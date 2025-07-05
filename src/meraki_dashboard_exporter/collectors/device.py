"""Device-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import DeviceStatus, DeviceType, MetricName, UpdateTier
from ..core.logging import get_logger
from .devices import MRCollector, MSCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


class DeviceCollector(MetricCollector):
    """Collector for device-level metrics."""

    # Device metrics update at medium frequency
    update_tier: UpdateTier = UpdateTier.MEDIUM

    def _set_metric_value(self, metric_name: str, labels: dict[str, str], value: float) -> None:
        """Safely set a metric value with validation.
        
        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float
            Value to set.
            
        """
        metric = getattr(self, metric_name, None)
        if metric is None:
            logger.debug(
                "Metric not available",
                metric_name=metric_name,
            )
            return

        try:
            metric.labels(**labels).set(value)
        except Exception:
            logger.exception(
                "Failed to set metric value",
                metric_name=metric_name,
                labels=labels,
                value=value,
            )

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize device collector with sub-collectors."""
        super().__init__(api, settings, registry)

        # Initialize device-specific collectors
        self.ms_collector = MSCollector(self)
        self.mr_collector = MRCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize device metrics."""
        # Common device metrics
        self._device_up = self._create_gauge(
            MetricName.DEVICE_UP,
            "Device online status (1 = online, 0 = offline)",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )


        # Memory metrics - available via system memory usage history API
        self._device_memory_used_bytes = self._create_gauge(
            "meraki_device_memory_used_bytes",
            "Device memory used in bytes",
            labelnames=["serial", "name", "model", "network_id", "device_type", "stat"],
        )

        self._device_memory_free_bytes = self._create_gauge(
            "meraki_device_memory_free_bytes",
            "Device memory free in bytes",
            labelnames=["serial", "name", "model", "network_id", "device_type", "stat"],
        )

        self._device_memory_total_bytes = self._create_gauge(
            "meraki_device_memory_total_bytes",
            "Device memory total provisioned in bytes",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        self._device_memory_usage_percent = self._create_gauge(
            MetricName.DEVICE_MEMORY_USAGE_PERCENT,
            "Device memory usage percentage (maximum from most recent interval)",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        # Switch-specific metrics
        self._switch_port_status = self._create_gauge(
            MetricName.MS_PORT_STATUS,
            "Switch port status (1 = connected, 0 = disconnected)",
            labelnames=["serial", "name", "port_id", "port_name"],
        )

        self._switch_port_traffic = self._create_gauge(
            MetricName.MS_PORT_TRAFFIC_BYTES,
            "Switch port traffic in bytes",
            labelnames=["serial", "name", "port_id", "port_name", "direction"],
        )

        self._switch_port_errors = self._create_gauge(
            MetricName.MS_PORT_ERRORS_TOTAL,
            "Switch port error count",
            labelnames=["serial", "name", "port_id", "port_name", "error_type"],
        )

        self._switch_power = self._create_gauge(
            MetricName.MS_POWER_USAGE_WATTS,
            "Switch power usage in watts",
            labelnames=["serial", "name", "model"],
        )

        # POE metrics
        self._switch_poe_port_power = self._create_gauge(
            MetricName.MS_POE_PORT_POWER_WATTS,
            "Per-port POE power consumption in watt-hours (Wh)",
            labelnames=["serial", "name", "port_id", "port_name"],
        )

        self._switch_poe_total_power = self._create_gauge(
            MetricName.MS_POE_TOTAL_POWER_WATTS,
            "Total POE power consumption for switch in watt-hours (Wh)",
            labelnames=["serial", "name", "model", "network_id"],
        )

        self._switch_poe_budget = self._create_gauge(
            MetricName.MS_POE_BUDGET_WATTS,
            "Total POE power budget for switch in watts",
            labelnames=["serial", "name", "model", "network_id"],
        )

        self._switch_poe_network_total = self._create_gauge(
            MetricName.MS_POE_NETWORK_TOTAL_WATTS,
            "Total POE power consumption for all switches in network in watt-hours (Wh)",
            labelnames=["network_id", "network_name"],
        )

        # Wireless AP metrics
        self._ap_clients = self._create_gauge(
            MetricName.MR_CLIENTS_CONNECTED,
            "Number of clients connected to access point",
            labelnames=["serial", "name", "model", "network_id"],
        )


        self._ap_traffic = self._create_gauge(
            MetricName.MR_TRAFFIC_BYTES,
            "Access point traffic in bytes",
            labelnames=["serial", "name", "direction"],
        )

    async def _collect_impl(self) -> None:
        """Collect device metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                org_ids = [self.settings.org_id]
            else:
                orgs = await asyncio.to_thread(
                    self.api.organizations.getOrganizations
                )
                org_ids = [org["id"] for org in orgs]

            # Collect devices for each organization
            for org_id in org_ids:
                await self._collect_org_devices(org_id)

        except Exception:
            logger.exception("Failed to collect device metrics")

    async def _collect_org_devices(self, org_id: str) -> None:
        """Collect device metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            # Get all devices and their statuses with timeout
            logger.info(
                "Starting device collection",
                org_id=org_id,
            )

            # Check if API is accessible
            logger.debug("Checking API access", org_id=org_id)

            # Fetch devices and statuses separately to better handle timeouts
            devices = None
            statuses = None

            try:
                logger.info("Fetching devices list", org_id=org_id)
                self._track_api_call("getOrganizationDevices")

                devices = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevices,
                    org_id,
                    total_pages="all",
                )
                logger.info(
                    "Successfully fetched devices",
                    org_id=org_id,
                    count=len(devices) if devices else 0,
                )
            except TimeoutError:
                logger.error(
                    "Timeout fetching devices",
                    org_id=org_id,
                )
                return
            except Exception as e:
                logger.error(
                    "Failed to fetch devices",
                    org_id=org_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return

            try:
                logger.info("Fetching device statuses", org_id=org_id)
                self._track_api_call("getOrganizationDevicesStatuses")

                statuses = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevicesStatuses,
                    org_id,
                    total_pages="all",
                )
                logger.info(
                    "Successfully fetched statuses",
                    org_id=org_id,
                    count=len(statuses) if statuses else 0,
                )
            except TimeoutError:
                logger.error(
                    "Timeout fetching statuses",
                    org_id=org_id,
                )
                # Continue with devices but no status info
                statuses = []
            except Exception as e:
                logger.error(
                    "Failed to fetch statuses",
                    org_id=org_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Continue with devices but no status info
                statuses = []

            if not devices:
                logger.warning(
                    "No devices found for organization",
                    org_id=org_id,
                )
                return

            logger.info(
                "Processing devices",
                org_id=org_id,
                device_count=len(devices),
                status_count=len(statuses),
            )

            # Create status lookup
            status_map = {s["serial"]: s for s in statuses}

            # Track network POE usage (removed for now - not implemented)

            # Collect metrics for each device type
            tasks = []
            ms_devices = []
            mr_devices = []

            for device in devices:
                device_type = self._get_device_type(device)
                if device_type not in self.settings.device_types:
                    continue

                # Add status info to device
                device["status_info"] = status_map.get(device["serial"], {})

                # Collect common metrics
                self._collect_common_metrics(device)

                # Collect type-specific metrics (excluding sensors - they're handled separately)
                if device_type == DeviceType.MS:
                    ms_devices.append(device)
                elif device_type == DeviceType.MR:
                    mr_devices.append(device)

            # Process MS devices
            if ms_devices:
                logger.info(
                    "Processing MS devices",
                    count=len(ms_devices),
                )
                # Process devices in smaller batches to avoid overwhelming the API
                batch_size = 5
                for i in range(0, len(ms_devices), batch_size):
                    batch = ms_devices[i:i + batch_size]
                    logger.debug(
                        "Processing MS device batch",
                        batch_start=i,
                        batch_size=len(batch),
                    )

                    # Process devices in batch concurrently but with individual timeouts
                    tasks = []
                    for device in batch:
                        task = self._collect_ms_device_with_timeout(device)
                        tasks.append(task)

                    # Wait for batch to complete
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Log any failures
                    for device, result in zip(batch, results, strict=False):
                        if isinstance(result, Exception):
                            logger.error(
                                "Failed to collect MS device",
                                serial=device["serial"],
                                error=str(result),
                                error_type=type(result).__name__,
                            )

                    # Small delay between batches
                    await asyncio.sleep(0.5)

            # Process MR devices
            if mr_devices:
                logger.info(
                    "Processing MR devices",
                    count=len(mr_devices),
                )
                # Process devices in smaller batches to avoid overwhelming the API
                batch_size = 5
                for i in range(0, len(mr_devices), batch_size):
                    batch = mr_devices[i:i + batch_size]
                    logger.debug(
                        "Processing MR device batch",
                        batch_start=i,
                        batch_size=len(batch),
                    )

                    # Process devices in batch concurrently but with individual timeouts
                    tasks = []
                    for device in batch:
                        task = self._collect_mr_device_with_timeout(device)
                        tasks.append(task)

                    # Wait for batch to complete
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Log any failures
                    for device, result in zip(batch, results, strict=False):
                        if isinstance(result, Exception):
                            logger.error(
                                "Failed to collect MR device",
                                serial=device["serial"],
                                error=str(result),
                                error_type=type(result).__name__,
                            )

                    # Small delay between batches
                    await asyncio.sleep(0.5)

            # Aggregate network-wide POE metrics after all switches are collected
            logger.info("Aggregating network POE metrics")
            try:
                await asyncio.wait_for(
                    self._aggregate_network_poe(org_id, devices),
                    timeout=60.0
                )
            except TimeoutError:
                logger.error("Timeout aggregating POE metrics")

            # Collect memory metrics for all devices
            logger.info("Collecting device memory metrics")
            try:
                await asyncio.wait_for(
                    self._collect_memory_metrics(org_id),
                    timeout=60.0
                )
            except TimeoutError:
                logger.error("Timeout collecting memory metrics")

            # Collect wireless client counts
            if any(d for d in devices if d.get("model", "").startswith("MR")):
                logger.info("Collecting wireless client counts")
                try:
                    await asyncio.wait_for(
                        self._collect_wireless_clients(org_id),
                        timeout=30.0
                    )
                except TimeoutError:
                    logger.error("Timeout collecting wireless client counts")

        except Exception as e:
            logger.exception(
                "Failed to collect devices for organization",
                org_id=org_id,
                error_type=type(e).__name__,
                error=str(e),
            )

    async def _collect_ms_device_with_timeout(self, device: dict[str, Any]) -> None:
        """Collect MS device metrics with timeout.
        
        Parameters
        ----------
        device : dict[str, Any]
            Device data.
            
        """
        try:
            await asyncio.wait_for(
                self.ms_collector.collect(device),
                timeout=15.0  # 15 second timeout per device
            )
        except TimeoutError as e:
            raise TimeoutError(
                f"Timeout collecting MS device {device['serial']}"
            ) from e

    async def _collect_mr_device_with_timeout(self, device: dict[str, Any]) -> None:
        """Collect MR device metrics with timeout.
        
        Parameters
        ----------
        device : dict[str, Any]
            Device data.
            
        """
        try:
            await asyncio.wait_for(
                self.mr_collector.collect(device),
                timeout=15.0  # 15 second timeout per device
            )
        except TimeoutError as e:
            raise TimeoutError(
                f"Timeout collecting MR device {device['serial']}"
            ) from e

    def _get_device_type(self, device: dict[str, Any]) -> str:
        """Get device type from device model.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        Returns
        -------
        str
            Device type.

        """
        model = device.get("model", "")
        return model[:2] if len(model) >= 2 else "Unknown"

    def _collect_common_metrics(self, device: dict[str, Any]) -> None:
        """Collect common device metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        serial = device["serial"]
        name = device.get("name", serial)
        model = device.get("model", "Unknown")
        network_id = device.get("networkId", "")
        device_type = self._get_device_type(device)
        status_info = device.get("status_info", {})

        # Device up/down status
        status = status_info.get("status", DeviceStatus.OFFLINE)
        is_online = 1 if status == DeviceStatus.ONLINE else 0
        self._set_metric_value(
            "_device_up",
            {
                "serial": serial,
                "name": name,
                "model": model,
                "network_id": network_id,
                "device_type": device_type,
            },
            is_online,
        )

        # Uptime
        if "uptimeInSeconds" in device:
            self._set_metric_value(
                "_device_uptime",
                {
                    "serial": serial,
                    "name": name,
                    "model": model,
                    "network_id": network_id,
                    "device_type": device_type,
                },
                device["uptimeInSeconds"],
            )

    async def _aggregate_network_poe(self, org_id: str, devices: list[dict[str, Any]]) -> None:
        """Aggregate POE metrics at the network level.
        
        Parameters
        ----------
        org_id : str
            Organization ID.
        devices : list[dict[str, Any]]
            All devices in the organization.
            
        """
        try:
            # Get network names
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            network_map = {n["id"]: n["name"] for n in networks}

            # Group switches by network
            network_switches: dict[str, list[str]] = {}
            for device in devices:
                if self._get_device_type(device) == DeviceType.MS:
                    network_id = device.get("networkId", "")
                    if network_id:
                        if network_id not in network_switches:
                            network_switches[network_id] = []
                        network_switches[network_id].append(device["serial"])

            # Calculate total POE per network
            for network_id, switch_serials in network_switches.items():
                total_poe = 0
                for serial in switch_serials:
                    # Get the current value from the metric
                    try:
                        # Find the switch in devices list
                        switch = next(d for d in devices if d["serial"] == serial)
                        # Skip making additional API calls for now
                        # We'll aggregate from already collected metrics instead
                        _ = switch  # Keep switch for future POE aggregation

                    except StopIteration:
                        continue
                    except Exception:
                        logger.debug(
                            "Failed to get POE data for switch",
                            serial=serial,
                        )
                        continue

                # Set network-wide POE metric
                network_name = network_map.get(network_id, network_id)
                self._set_metric_value(
                    "_switch_poe_network_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_poe,
                )

        except Exception:
            logger.exception(
                "Failed to aggregate network POE metrics",
                org_id=org_id,
            )

    async def _collect_memory_metrics(self, org_id: str) -> None:
        """Collect memory metrics for all devices in an organization.
        
        Parameters
        ----------
        org_id : str
            Organization ID.
            
        """
        try:
            # Use a short timespan (600 seconds = 10 minutes) with 300 second interval
            # This gives us the most recent memory data
            logger.info("Fetching device memory usage history", org_id=org_id)
            self._track_api_call("getOrganizationDevicesSystemMemoryUsageHistoryByInterval")

            memory_response = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval,
                org_id,
                timespan=600,
                interval=300,
            )

            # Handle different API response formats
            if isinstance(memory_response, dict) and "items" in memory_response:
                memory_data = memory_response["items"]
            elif isinstance(memory_response, list):
                memory_data = memory_response
            else:
                logger.warning(
                    "Unexpected memory data format",
                    org_id=org_id,
                    response_type=type(memory_response).__name__,
                )
                memory_data = []

            logger.info(
                "Successfully fetched memory data",
                org_id=org_id,
                device_count=len(memory_data) if memory_data else 0,
            )

            # Process each device's memory data
            for device_data in memory_data:
                serial = device_data.get("serial", "")
                name = device_data.get("name", serial)
                model = device_data.get("model", "Unknown")
                network_id = device_data.get("network", {}).get("id", "")
                device_type = model[:2] if len(model) >= 2 else "Unknown"

                # Total provisioned memory
                provisioned_kb = device_data.get("provisioned")
                if provisioned_kb and provisioned_kb > 0:
                    self._set_metric_value(
                        "_device_memory_total_bytes",
                        {
                            "serial": serial,
                            "name": name,
                            "model": model,
                            "network_id": network_id,
                            "device_type": device_type,
                        },
                        provisioned_kb * 1024,  # Convert KB to bytes
                    )

                # Get the most recent interval data
                intervals = device_data.get("intervals", [])
                if intervals:
                    # Use the first interval (most recent)
                    latest_interval = intervals[0]
                    memory_stats = latest_interval.get("memory", {})

                    # Used memory stats
                    used_stats = memory_stats.get("used", {})
                    if used_stats:
                        # Minimum used
                        if "minimum" in used_stats:
                            self._set_metric_value(
                                "_device_memory_used_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "min",
                                },
                                used_stats["minimum"] * 1024,  # Convert KB to bytes
                            )

                        # Maximum used
                        if "maximum" in used_stats:
                            self._set_metric_value(
                                "_device_memory_used_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "max",
                                },
                                used_stats["maximum"] * 1024,  # Convert KB to bytes
                            )

                        # Median used
                        if "median" in used_stats:
                            self._set_metric_value(
                                "_device_memory_used_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "median",
                                },
                                used_stats["median"] * 1024,  # Convert KB to bytes
                            )

                        # Memory usage percentage (use maximum percentage)
                        percentages = used_stats.get("percentages", {})
                        if "maximum" in percentages:
                            self._set_metric_value(
                                "_device_memory_usage_percent",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                },
                                percentages["maximum"],
                            )

                    # Free memory stats
                    free_stats = memory_stats.get("free", {})
                    if free_stats:
                        # Minimum free
                        if "minimum" in free_stats:
                            self._set_metric_value(
                                "_device_memory_free_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "min",
                                },
                                free_stats["minimum"] * 1024,  # Convert KB to bytes
                            )

                        # Maximum free
                        if "maximum" in free_stats:
                            self._set_metric_value(
                                "_device_memory_free_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "max",
                                },
                                free_stats["maximum"] * 1024,  # Convert KB to bytes
                            )

                        # Median free
                        if "median" in free_stats:
                            self._set_metric_value(
                                "_device_memory_free_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "median",
                                },
                                free_stats["median"] * 1024,  # Convert KB to bytes
                            )

        except Exception:
            logger.exception(
                "Failed to collect memory metrics",
                org_id=org_id,
            )

    async def _collect_wireless_clients(self, org_id: str) -> None:
        """Collect wireless client counts for MR devices.
        
        Parameters
        ----------
        org_id : str
            Organization ID.
            
        """
        try:
            logger.info("Fetching wireless client counts", org_id=org_id)
            self._track_api_call("getOrganizationWirelessClientsOverviewByDevice")

            client_overview = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessClientsOverviewByDevice,
                org_id,
                total_pages="all",
            )

            # Handle different API response formats
            if isinstance(client_overview, dict) and "items" in client_overview:
                client_data = client_overview["items"]
            elif isinstance(client_overview, list):
                client_data = client_overview
            else:
                logger.warning(
                    "Unexpected client overview format",
                    org_id=org_id,
                    response_type=type(client_overview).__name__,
                )
                client_data = []

            logger.info(
                "Successfully fetched wireless client counts",
                org_id=org_id,
                device_count=len(client_data) if client_data else 0,
            )

            # Process each device's client data
            for device_data in client_data:
                serial = device_data.get("serial", "")
                network_id = device_data.get("network", {}).get("id", "")
                
                # Get online client count
                counts = device_data.get("counts", {})
                by_status = counts.get("byStatus", {})
                online_clients = by_status.get("online", 0)
                
                # We need to look up the device name and model from our devices cache
                # For now, just use the serial as the name
                self._ap_clients.labels(
                    serial=serial,
                    name=serial,  # Will be updated in future with device lookup
                    model="MR",  # Will be updated in future with device lookup
                    network_id=network_id,
                ).set(online_clients)

        except Exception:
            logger.exception(
                "Failed to collect wireless client counts",
                org_id=org_id,
            )
