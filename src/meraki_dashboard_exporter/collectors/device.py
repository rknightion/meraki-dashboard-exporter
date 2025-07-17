"""Device-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import DeviceStatus, DeviceType, MetricName, UpdateTier
from ..core.logging import get_logger
from .devices import MGCollector, MRCollector, MSCollector, MTCollector, MVCollector, MXCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


class DeviceCollector(MetricCollector):
    """Collector for device-level metrics."""

    # Device metrics update at medium frequency
    update_tier: UpdateTier = UpdateTier.MEDIUM

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Safely set a metric value with validation.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        # Skip if value is None - this happens when API returns null values
        if value is None:
            logger.debug(
                "Skipping metric update due to None value",
                metric_name=metric_name,
                labels=labels,
            )
            return

        metric = getattr(self, metric_name, None)
        if metric is None:
            logger.debug(
                "Metric not available",
                metric_name=metric_name,
            )
            return

        try:
            metric.labels(**labels).set(value)
            logger.debug(
                "Successfully set metric value",
                metric_name=metric_name,
                labels=labels,
                value=value,
            )
        except Exception:
            logger.exception(
                "Failed to set metric value",
                metric_name=metric_name,
                labels=labels,
                value=value,
            )

    def _set_packet_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Set packet metric value with retention logic for total packet counters.

        For packet loss metrics, 0 is a valid value. For total packet counters,
        we retain the last known value if the API returns None or 0.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. May be None if API returned null.

        """
        # Create a cache key from metric name and sorted labels
        cache_key = f"{metric_name}:{':'.join(f'{k}={v}' for k, v in sorted(labels.items()))}"

        # Determine if this is a "total" metric that should retain values
        is_total_metric = "total" in metric_name and "percent" not in metric_name

        # For total metrics, use cached value if current value is None or 0
        if is_total_metric and (value is None or value == 0):
            cached_value = self._packet_metrics_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(
                    "Using cached value for packet metric",
                    metric_name=metric_name,
                    labels=labels,
                    cached_value=cached_value,
                    original_value=value,
                )
                value = cached_value
            else:
                # No cached value, skip update to avoid showing 0
                logger.debug(
                    "No cached value available for packet metric",
                    metric_name=metric_name,
                    labels=labels,
                    original_value=value,
                )
                return

        # Update cache if we have a valid value
        if value is not None and (not is_total_metric or value > 0):
            self._packet_metrics_cache[cache_key] = value

        # Use regular metric setting
        self._set_metric_value(metric_name, labels, value)

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize device collector with sub-collectors."""
        super().__init__(api, settings, registry)

        # Initialize device-specific collectors
        self.mg_collector = MGCollector(self)
        self.mr_collector = MRCollector(self)
        self.ms_collector = MSCollector(self)
        self.mt_collector = MTCollector(self)
        self.mv_collector = MVCollector(self)
        self.mx_collector = MXCollector(self)

        # Map device type strings to collectors
        self._device_collectors = {
            "MG": self.mg_collector,
            "MR": self.mr_collector,
            "MS": self.ms_collector,
            "MT": self.mt_collector,
            "MV": self.mv_collector,
            "MX": self.mx_collector,
        }

        # Cache for retaining last known packet metric values
        self._packet_metrics_cache: dict[str, float] = {}
        
        # Initialize sub-collector metrics
        self.mr_collector._initialize_metrics()
        self.ms_collector._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize device metrics."""
        # Common device metrics
        self._device_up = self._create_gauge(
            MetricName.DEVICE_UP,
            "Device online status (1 = online, 0 = offline)",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        self._device_status_info = self._create_gauge(
            "meraki_device_status_info",
            "Device status information",
            labelnames=["serial", "name", "model", "network_id", "device_type", "status"],
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

    async def _collect_impl(self) -> None:
        """Collect device metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                org_ids = [self.settings.org_id]
            else:
                logger.debug("Fetching all organizations for device collection")
                self._track_api_call("getOrganizations")
                orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
                org_ids = [org["id"] for org in orgs]
                logger.debug("Successfully fetched organizations", count=len(org_ids))

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
            logger.debug(
                "Starting device collection",
                org_id=org_id,
            )

            # Check if API is accessible
            logger.debug("Checking API access", org_id=org_id)

            # Fetch devices and statuses separately to better handle timeouts
            devices = None
            statuses = None

            # Store device lookup map for use in other collectors
            self._device_lookup: dict[str, dict[str, Any]] = {}

            try:
                logger.debug("Fetching devices list", org_id=org_id)
                self._track_api_call("getOrganizationDevices")

                devices = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevices,
                    org_id,
                    total_pages="all",
                )
                logger.debug(
                    "Successfully fetched devices",
                    org_id=org_id,
                    count=len(devices) if devices else 0,
                )
            except Exception as e:
                logger.error(
                    "Failed to fetch devices",
                    org_id=org_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return

            try:
                logger.debug("Fetching device statuses", org_id=org_id)
                self._track_api_call("getOrganizationDevicesStatuses")

                statuses = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevicesStatuses,
                    org_id,
                    total_pages="all",
                )
                logger.debug(
                    "Successfully fetched statuses",
                    org_id=org_id,
                    count=len(statuses) if statuses else 0,
                )
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

            logger.debug(
                "Processing devices",
                org_id=org_id,
                device_count=len(devices),
                status_count=len(statuses),
            )

            # Create status lookup
            status_map = {s["serial"]: s for s in statuses}

            # Track network POE usage (removed for now - not implemented)

            # Group devices by type for batch processing
            devices_by_type: dict[str, list[dict[str, Any]]] = {}

            for device in devices:
                device_type = self._get_device_type(device)

                # Add to device lookup map
                serial = device["serial"]
                self._device_lookup[serial] = {
                    "name": device.get("name", serial),
                    "model": device.get("model", "Unknown"),
                    "network_id": device.get("networkId", ""),
                    "device_type": device_type,
                }

                # Add status info to device
                device["status_info"] = status_map.get(device["serial"], {})

                # Collect common metrics
                self._collect_common_metrics(device)

                # Group devices by type for batch processing
                if device_type not in devices_by_type:
                    devices_by_type[device_type] = []
                devices_by_type[device_type].append(device)

            # Store references for legacy code
            ms_devices = devices_by_type.get("MS", [])
            mr_devices = devices_by_type.get("MR", [])

            # Process MS devices
            if ms_devices:
                logger.debug(
                    "Processing MS devices",
                    count=len(ms_devices),
                )
                # Process devices in smaller batches to avoid overwhelming the API
                batch_size = 5
                for i in range(0, len(ms_devices), batch_size):
                    batch = ms_devices[i : i + batch_size]
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
                logger.debug(
                    "Processing MR devices",
                    count=len(mr_devices),
                    mr_serials=[d["serial"] for d in mr_devices],
                )
                # Process devices in smaller batches to avoid overwhelming the API
                batch_size = 5
                for i in range(0, len(mr_devices), batch_size):
                    batch = mr_devices[i : i + batch_size]
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

            # Process other device types (MX, MG, MV)
            for device_type, type_devices in devices_by_type.items():
                # Skip MS and MR as they're handled above (for now)
                if device_type in {"MS", "MR"}:
                    continue

                if type_devices:
                    logger.debug(
                        f"Processing {device_type} devices",
                        count=len(type_devices),
                    )
                    # Process devices in smaller batches
                    batch_size = 5
                    for i in range(0, len(type_devices), batch_size):
                        batch = type_devices[i : i + batch_size]
                        
                        # Process devices in batch concurrently
                        tasks = []
                        for device in batch:
                            task = self._collect_device_with_timeout(device, device_type)
                            tasks.append(task)
                        
                        # Wait for batch to complete
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        # Log any failures
                        for device, result in zip(batch, results, strict=False):
                            if isinstance(result, Exception):
                                logger.error(
                                    f"Failed to collect {device_type} device",
                                    serial=device["serial"],
                                    error=str(result),
                                    error_type=type(result).__name__,
                                )
                        
                        # Small delay between batches
                        await asyncio.sleep(0.5)

            # Aggregate network-wide POE metrics after all switches are collected
            logger.debug("Aggregating network POE metrics")
            try:
                await self._aggregate_network_poe(org_id, devices)
            except Exception:
                logger.exception("Failed to aggregate POE metrics")

            # Collect memory metrics for all devices
            logger.debug("Collecting device memory metrics")
            try:
                # Use base collector's memory collection
                await self.ms_collector.collect_memory_metrics(org_id, self._device_lookup)
            except Exception:
                logger.exception("Failed to collect memory metrics")

            # Collect MR-specific metrics
            if any(d for d in devices if d.get("model", "").startswith("MR")):
                logger.debug("Collecting MR-specific metrics")
                # Use MR collector for all MR-specific metrics
                await self._collect_mr_specific_metrics(org_id, devices)

        except Exception as e:
            logger.exception(
                "Failed to collect devices for organization",
                org_id=org_id,
                error_type=type(e).__name__,
                error=str(e),
            )

    async def _collect_device_with_timeout(self, device: dict[str, Any], device_type: str) -> None:
        """Collect device metrics with timeout.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        device_type : str
            Device type (e.g., DeviceType.MS).

        """
        collector = self._device_collectors.get(device_type)
        if collector:
            await collector.collect(device)
        else:
            logger.debug(
                "No collector available for device type",
                device_type=device_type,
                serial=device["serial"],
            )

    async def _collect_ms_device_with_timeout(self, device: dict[str, Any]) -> None:
        """Collect MS device metrics with timeout.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        await self.ms_collector.collect(device)

    async def _collect_mr_device_with_timeout(self, device: dict[str, Any]) -> None:
        """Collect MR device metrics with timeout.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        await self.mr_collector.collect(device)
    
    async def _collect_mr_specific_metrics(self, org_id: str, devices: list[dict[str, Any]]) -> None:
        """Collect MR-specific organization-wide metrics.
        
        Parameters
        ----------
        org_id : str
            Organization ID.
        devices : list[dict[str, Any]]
            All devices in the organization.
            
        """
        try:
            # Collect wireless client counts
            logger.debug("Collecting wireless client counts")
            try:
                await self.mr_collector.collect_wireless_clients(org_id, self._device_lookup)
            except Exception:
                logger.exception("Failed to collect wireless client counts")

            # Collect MR ethernet status
            logger.debug("Collecting MR ethernet status")
            try:
                await self.mr_collector.collect_ethernet_status(org_id, self._device_lookup)
            except Exception:
                logger.exception("Failed to collect MR ethernet status")

            # Collect MR packet loss metrics
            logger.debug("Collecting MR packet loss metrics")
            try:
                await self.mr_collector.collect_packet_loss(org_id, self._device_lookup)
            except Exception:
                logger.exception("Failed to collect MR packet loss metrics")

            # Collect MR CPU load metrics
            logger.debug("Collecting MR CPU load metrics")
            try:
                await self.mr_collector.collect_cpu_load(org_id, devices)
            except Exception:
                logger.exception("Failed to collect MR CPU load metrics")

            # Collect MR SSID status metrics
            logger.debug("Collecting MR SSID status metrics")
            try:
                await self.mr_collector.collect_ssid_status(org_id)
            except Exception:
                logger.exception("Failed to collect MR SSID status metrics")
                
        except Exception:
            logger.exception(
                "Failed to collect MR-specific metrics",
                org_id=org_id,
            )

    def _get_device_type(self, device: dict[str, Any]) -> str:
        """Get device type from device model.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        Returns
        -------
        str
            Device type string (e.g., "MS", "MR", "MX").

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

        # Device status info metric
        self._set_metric_value(
            "_device_status_info",
            {
                "serial": serial,
                "name": name,
                "model": model,
                "network_id": network_id,
                "device_type": device_type,
                "status": status,
            },
            1,
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
            logger.debug("Fetching networks for POE aggregation", org_id=org_id)
            self._track_api_call("getOrganizationNetworks")
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            logger.debug("Successfully fetched networks", org_id=org_id, count=len(networks))
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
                self.ms_collector._switch_poe_network_total.labels(
                    network_id=network_id,
                    network_name=network_name,
                ).set(total_poe)

        except Exception:
            logger.exception(
                "Failed to aggregate network POE metrics",
                org_id=org_id,
            )
