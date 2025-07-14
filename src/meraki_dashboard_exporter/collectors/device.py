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
        self.ms_collector = MSCollector(self)
        self.mr_collector = MRCollector(self)

        # Cache for retaining last known packet metric values
        self._packet_metrics_cache: dict[str, float] = {}

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

        self._ap_connection_stats = self._create_gauge(
            MetricName.MR_CONNECTION_STATS,
            "Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=["serial", "name", "model", "network_id", "stat_type"],
        )

        # MR ethernet status metrics
        self._mr_power_mode = self._create_gauge(
            "meraki_mr_power_mode",
            "Access point power mode (1 = full, 0 = other)",
            labelnames=["serial", "name", "network_id", "mode"],
        )

        self._mr_power_ac_connected = self._create_gauge(
            "meraki_mr_power_ac_connected",
            "Access point AC power connection status (1 = connected, 0 = not connected)",
            labelnames=["serial", "name", "network_id"],
        )

        self._mr_power_poe_connected = self._create_gauge(
            "meraki_mr_power_poe_connected",
            "Access point PoE power connection status (1 = connected, 0 = not connected)",
            labelnames=["serial", "name", "network_id"],
        )

        self._mr_port_poe_standard = self._create_gauge(
            "meraki_mr_port_poe_standard",
            "Access point port PoE standard (1 = 802.3at, 2 = 802.3af, 3 = 802.3bt, 0 = other/none)",
            labelnames=["serial", "name", "network_id", "port_name", "standard"],
        )

        self._mr_port_link_negotiation_duplex = self._create_gauge(
            "meraki_mr_port_link_negotiation_duplex",
            "Access point port link negotiation duplex (1 = full, 0 = half)",
            labelnames=["serial", "name", "network_id", "port_name"],
        )

        self._mr_port_link_negotiation_speed = self._create_gauge(
            "meraki_mr_port_link_negotiation_speed_mbps",
            "Access point port link negotiation speed in Mbps",
            labelnames=["serial", "name", "network_id", "port_name"],
        )

        self._mr_aggregation_enabled = self._create_gauge(
            "meraki_mr_aggregation_enabled",
            "Access point port aggregation enabled status (1 = enabled, 0 = disabled)",
            labelnames=["serial", "name", "network_id"],
        )

        self._mr_aggregation_speed = self._create_gauge(
            "meraki_mr_aggregation_speed_mbps",
            "Access point total aggregated port speed in Mbps",
            labelnames=["serial", "name", "network_id"],
        )

        # MR packet loss metrics (per device, 5-minute window)
        self._mr_packets_downstream_total = self._create_gauge(
            "meraki_mr_packets_downstream_total",
            "Total downstream packets transmitted by access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packets_downstream_lost = self._create_gauge(
            "meraki_mr_packets_downstream_lost",
            "Downstream packets lost by access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packet_loss_downstream_percent = self._create_gauge(
            "meraki_mr_packet_loss_downstream_percent",
            "Downstream packet loss percentage for access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packets_upstream_total = self._create_gauge(
            "meraki_mr_packets_upstream_total",
            "Total upstream packets received by access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packets_upstream_lost = self._create_gauge(
            "meraki_mr_packets_upstream_lost",
            "Upstream packets lost by access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packet_loss_upstream_percent = self._create_gauge(
            "meraki_mr_packet_loss_upstream_percent",
            "Upstream packet loss percentage for access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        # Combined packet metrics (calculated)
        self._mr_packets_total = self._create_gauge(
            "meraki_mr_packets_total",
            "Total packets (upstream + downstream) for access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packets_lost_total = self._create_gauge(
            "meraki_mr_packets_lost_total",
            "Total packets lost (upstream + downstream) for access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        self._mr_packet_loss_total_percent = self._create_gauge(
            "meraki_mr_packet_loss_total_percent",
            "Total packet loss percentage (upstream + downstream) for access point (5-minute window)",
            labelnames=["serial", "name", "network_id", "network_name"],
        )

        # Network-wide MR packet loss metrics (5-minute window)
        self._mr_network_packets_downstream_total = self._create_gauge(
            "meraki_mr_network_packets_downstream_total",
            "Total downstream packets for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packets_downstream_lost = self._create_gauge(
            "meraki_mr_network_packets_downstream_lost",
            "Downstream packets lost for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packet_loss_downstream_percent = self._create_gauge(
            "meraki_mr_network_packet_loss_downstream_percent",
            "Downstream packet loss percentage for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packets_upstream_total = self._create_gauge(
            "meraki_mr_network_packets_upstream_total",
            "Total upstream packets for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packets_upstream_lost = self._create_gauge(
            "meraki_mr_network_packets_upstream_lost",
            "Upstream packets lost for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packet_loss_upstream_percent = self._create_gauge(
            "meraki_mr_network_packet_loss_upstream_percent",
            "Upstream packet loss percentage for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        # Combined network-wide packet metrics (calculated)
        self._mr_network_packets_total = self._create_gauge(
            "meraki_mr_network_packets_total",
            "Total packets (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packets_lost_total = self._create_gauge(
            "meraki_mr_network_packets_lost_total",
            "Total packets lost (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        self._mr_network_packet_loss_total_percent = self._create_gauge(
            "meraki_mr_network_packet_loss_total_percent",
            "Total packet loss percentage (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=["network_id", "network_name"],
        )

        # MR CPU metrics
        self._mr_cpu_load_5min = self._create_gauge(
            "meraki_mr_cpu_load_5min",
            "Access point CPU load average over 5 minutes (normalized to 0-100 per core)",
            labelnames=["serial", "name", "model", "network_id", "network_name"],
        )

        # MR SSID/Radio status metrics
        self._mr_radio_broadcasting = self._create_gauge(
            "meraki_mr_radio_broadcasting",
            "Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting)",
            labelnames=["serial", "name", "network_id", "network_name", "band", "radio_index"],
        )

        self._mr_radio_channel = self._create_gauge(
            "meraki_mr_radio_channel",
            "Access point radio channel number",
            labelnames=["serial", "name", "network_id", "network_name", "band", "radio_index"],
        )

        self._mr_radio_channel_width = self._create_gauge(
            "meraki_mr_radio_channel_width_mhz",
            "Access point radio channel width in MHz",
            labelnames=["serial", "name", "network_id", "network_name", "band", "radio_index"],
        )

        self._mr_radio_power = self._create_gauge(
            "meraki_mr_radio_power_dbm",
            "Access point radio transmit power in dBm",
            labelnames=["serial", "name", "network_id", "network_name", "band", "radio_index"],
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

            logger.debug(
                "Processing devices",
                org_id=org_id,
                device_count=len(devices),
                status_count=len(statuses),
            )

            # Create status lookup
            status_map = {s["serial"]: s for s in statuses}

            # Track network POE usage (removed for now - not implemented)

            # Collect metrics for each device type
            tasks: list[Any] = []
            ms_devices = []
            mr_devices = []

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

            # Aggregate network-wide POE metrics after all switches are collected
            logger.debug("Aggregating network POE metrics")
            try:
                await asyncio.wait_for(self._aggregate_network_poe(org_id, devices), timeout=60.0)
            except TimeoutError:
                logger.error("Timeout aggregating POE metrics")

            # Collect memory metrics for all devices
            logger.debug("Collecting device memory metrics")
            try:
                await asyncio.wait_for(self._collect_memory_metrics(org_id), timeout=60.0)
            except TimeoutError:
                logger.error("Timeout collecting memory metrics")

            # Collect wireless client counts
            if any(d for d in devices if d.get("model", "").startswith("MR")):
                logger.debug("Collecting wireless client counts")
                try:
                    await asyncio.wait_for(self._collect_wireless_clients(org_id), timeout=30.0)
                except TimeoutError:
                    logger.error("Timeout collecting wireless client counts")

                # Collect MR ethernet status
                logger.debug("Collecting MR ethernet status")
                try:
                    await asyncio.wait_for(self._collect_mr_ethernet_status(org_id), timeout=30.0)
                except TimeoutError:
                    logger.error("Timeout collecting MR ethernet status")

                # Collect MR packet loss metrics
                logger.debug("Collecting MR packet loss metrics")
                try:
                    await asyncio.wait_for(self._collect_mr_packet_loss(org_id), timeout=30.0)
                except TimeoutError:
                    logger.error("Timeout collecting MR packet loss metrics")

                # Collect MR CPU load metrics
                logger.debug("Collecting MR CPU load metrics")
                try:
                    await asyncio.wait_for(self._collect_mr_cpu_load(org_id, devices), timeout=30.0)
                except TimeoutError:
                    logger.error("Timeout collecting MR CPU load metrics")

                # Collect MR SSID status metrics
                logger.debug("Collecting MR SSID status metrics")
                try:
                    await asyncio.wait_for(self._collect_mr_ssid_status(org_id), timeout=30.0)
                except TimeoutError:
                    logger.error("Timeout collecting MR SSID status metrics")

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
                timeout=30.0,  # 15 second timeout per device
            )
        except TimeoutError as e:
            raise TimeoutError(f"Timeout collecting MS device {device['serial']}") from e

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
                timeout=30.0,  # 15 second timeout per device
            )
        except TimeoutError as e:
            raise TimeoutError(f"Timeout collecting MR device {device['serial']}") from e

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
            # Use a short timespan (300 seconds = 5 minutes) with 300 second interval
            # This gives us the most recent memory data block
            logger.debug("Fetching device memory usage history", org_id=org_id)
            self._track_api_call("getOrganizationDevicesSystemMemoryUsageHistoryByInterval")

            memory_response = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval,
                org_id,
                timespan=300,
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

            logger.debug(
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
            logger.debug("Fetching wireless client counts", org_id=org_id)
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

            logger.debug(
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

                # Look up device info from our cache
                device_info = self._device_lookup.get(serial, {})
                device_name = device_info.get("name", serial)
                device_model = device_info.get("model", "MR")

                self._ap_clients.labels(
                    serial=serial,
                    name=device_name,
                    model=device_model,
                    network_id=network_id,
                ).set(online_clients)

        except Exception:
            logger.exception(
                "Failed to collect wireless client counts",
                org_id=org_id,
            )

    async def _collect_mr_ethernet_status(self, org_id: str) -> None:
        """Collect ethernet status for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            logger.debug("Fetching MR ethernet status", org_id=org_id)
            self._track_api_call("getOrganizationWirelessDevicesEthernetStatuses")

            ethernet_statuses = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesEthernetStatuses,
                org_id,
            )

            # Handle different API response formats
            if isinstance(ethernet_statuses, dict) and "items" in ethernet_statuses:
                ethernet_data = ethernet_statuses["items"]
            elif isinstance(ethernet_statuses, list):
                ethernet_data = ethernet_statuses
            else:
                logger.warning(
                    "Unexpected ethernet status format",
                    org_id=org_id,
                    response_type=type(ethernet_statuses).__name__,
                )
                ethernet_data = []

            logger.debug(
                "Successfully fetched MR ethernet status",
                org_id=org_id,
                device_count=len(ethernet_data) if ethernet_data else 0,
            )

            # Process each device's ethernet status
            for device_data in ethernet_data:
                serial = device_data.get("serial", "")
                name = device_data.get("name", serial)
                network_id = device_data.get("network", {}).get("id", "")

                # Power status
                power_info = device_data.get("power", {})
                power_mode = power_info.get("mode", "")

                # Set power mode metric (1 for full, 0 for other)
                self._set_metric_value(
                    "_mr_power_mode",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "mode": power_mode,
                    },
                    1 if power_mode == "full" else 0,
                )

                # AC power connection
                ac_info = power_info.get("ac", {})
                ac_connected = ac_info.get("isConnected", False)
                self._set_metric_value(
                    "_mr_power_ac_connected",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                    },
                    1 if ac_connected else 0,
                )

                # PoE power connection
                poe_info = power_info.get("poe", {})
                poe_connected = poe_info.get("isConnected", False)
                self._set_metric_value(
                    "_mr_power_poe_connected",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                    },
                    1 if poe_connected else 0,
                )

                # Port information
                ports = device_data.get("ports", [])
                for port in ports:
                    port_name = port.get("name", "Unknown")

                    # PoE standard
                    port_poe = port.get("poe", {})
                    poe_standard = port_poe.get("standard", "")

                    # Map PoE standard to numeric value
                    poe_standard_value = 0
                    if poe_standard == "802.3at":
                        poe_standard_value = 1
                    elif poe_standard == "802.3af":
                        poe_standard_value = 2
                    elif poe_standard == "802.3bt":
                        poe_standard_value = 3

                    self._set_metric_value(
                        "_mr_port_poe_standard",
                        {
                            "serial": serial,
                            "name": name,
                            "network_id": network_id,
                            "port_name": port_name,
                            "standard": poe_standard,
                        },
                        poe_standard_value,
                    )

                    # Link negotiation
                    link_neg = port.get("linkNegotiation", {})
                    duplex = link_neg.get("duplex", "")
                    speed = link_neg.get("speed", 0)

                    # Set duplex metric (1 for full, 0 for half)
                    self._set_metric_value(
                        "_mr_port_link_negotiation_duplex",
                        {
                            "serial": serial,
                            "name": name,
                            "network_id": network_id,
                            "port_name": port_name,
                        },
                        1 if duplex == "full" else 0,
                    )

                    # Set speed metric
                    self._set_metric_value(
                        "_mr_port_link_negotiation_speed",
                        {
                            "serial": serial,
                            "name": name,
                            "network_id": network_id,
                            "port_name": port_name,
                        },
                        speed,
                    )

                # Aggregation information
                aggregation = device_data.get("aggregation", {})
                aggregation_enabled = aggregation.get("enabled", False)
                aggregation_speed = aggregation.get("speed", 0)

                self._set_metric_value(
                    "_mr_aggregation_enabled",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                    },
                    1 if aggregation_enabled else 0,
                )

                self._set_metric_value(
                    "_mr_aggregation_speed",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                    },
                    aggregation_speed,
                )

        except Exception:
            logger.exception(
                "Failed to collect MR ethernet status",
                org_id=org_id,
            )

    async def _collect_mr_packet_loss(self, org_id: str) -> None:
        """Collect packet loss metrics for MR devices and networks.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            # Collect per-device packet loss metrics
            logger.debug("Fetching MR device packet loss", org_id=org_id)
            self._track_api_call("getOrganizationWirelessDevicesPacketLossByDevice")

            device_packet_loss = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesPacketLossByDevice,
                org_id,
                timespan=3600,  # 1-hour window for better data availability
            )

            # Handle different API response formats
            if isinstance(device_packet_loss, dict) and "items" in device_packet_loss:
                device_data = device_packet_loss["items"]
            elif isinstance(device_packet_loss, list):
                device_data = device_packet_loss
            else:
                logger.warning(
                    "Unexpected device packet loss format",
                    org_id=org_id,
                    response_type=type(device_packet_loss).__name__,
                )
                device_data = []

            logger.debug(
                "Successfully fetched MR device packet loss",
                org_id=org_id,
                device_count=len(device_data) if device_data else 0,
            )

            # Process each device's packet loss data
            for device_info in device_data:
                device = device_info.get("device", {})
                serial = device.get("serial", "")
                name = device.get("name", serial)
                network = device_info.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", "")

                # Downstream metrics
                downstream = device_info.get("downstream", {})
                downstream_total = downstream.get("total", 0)
                downstream_lost = downstream.get("lost", 0)
                downstream_loss_pct = downstream.get("lossPercentage", 0.0)

                self._set_packet_metric_value(
                    "_mr_packets_downstream_total",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_packets_downstream_lost",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_downstream_percent",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_loss_pct,
                )

                # Upstream metrics
                upstream = device_info.get("upstream", {})
                upstream_total = upstream.get("total", 0)
                upstream_lost = upstream.get("lost", 0)
                upstream_loss_pct = upstream.get("lossPercentage", 0.0)

                self._set_packet_metric_value(
                    "_mr_packets_upstream_total",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_packets_upstream_lost",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_upstream_percent",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_loss_pct,
                )

                # Calculate combined metrics
                total_packets = downstream_total + upstream_total
                total_lost = downstream_lost + upstream_lost
                total_loss_pct = (total_lost / total_packets * 100) if total_packets > 0 else 0.0

                self._set_packet_metric_value(
                    "_mr_packets_total",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_packets,
                )

                self._set_packet_metric_value(
                    "_mr_packets_lost_total",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_total_percent",
                    {
                        "serial": serial,
                        "name": name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_loss_pct,
                )

            # Collect network-wide packet loss metrics
            logger.debug("Fetching MR network packet loss", org_id=org_id)
            self._track_api_call("getOrganizationWirelessDevicesPacketLossByNetwork")

            network_packet_loss = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork,
                org_id,
                timespan=3600,  # 1-hour window for better data availability
            )

            # Handle different API response formats
            if isinstance(network_packet_loss, dict) and "items" in network_packet_loss:
                network_data = network_packet_loss["items"]
            elif isinstance(network_packet_loss, list):
                network_data = network_packet_loss
            else:
                logger.warning(
                    "Unexpected network packet loss format",
                    org_id=org_id,
                    response_type=type(network_packet_loss).__name__,
                )
                network_data = []

            logger.debug(
                "Successfully fetched MR network packet loss",
                org_id=org_id,
                network_count=len(network_data) if network_data else 0,
            )

            # Process each network's packet loss data
            for network_info in network_data:
                network = network_info.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", "")

                # Downstream metrics
                downstream = network_info.get("downstream", {})
                downstream_total = downstream.get("total", 0)
                downstream_lost = downstream.get("lost", 0)
                downstream_loss_pct = downstream.get("lossPercentage", 0.0)

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_lost",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_downstream_percent",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_loss_pct,
                )

                # Upstream metrics
                upstream = network_info.get("upstream", {})
                upstream_total = upstream.get("total", 0)
                upstream_lost = upstream.get("lost", 0)
                upstream_loss_pct = upstream.get("lossPercentage", 0.0)

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_lost",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_upstream_percent",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_loss_pct,
                )

                # Calculate combined network metrics
                total_packets = downstream_total + upstream_total
                total_lost = downstream_lost + upstream_lost
                total_loss_pct = (total_lost / total_packets * 100) if total_packets > 0 else 0.0

                self._set_packet_metric_value(
                    "_mr_network_packets_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_packets,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_lost_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_total_percent",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_loss_pct,
                )

        except Exception:
            logger.exception(
                "Failed to collect MR packet loss metrics",
                org_id=org_id,
            )

    async def _collect_mr_cpu_load(self, org_id: str, devices: list[dict[str, Any]]) -> None:
        """Collect CPU load metrics for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        devices : list[dict[str, Any]]
            List of all devices in the organization.

        """
        try:
            # Extract MR device serials
            mr_serials = [
                device["serial"] for device in devices if device.get("model", "").startswith("MR")
            ]

            if not mr_serials:
                logger.debug("No MR devices found for CPU load collection", org_id=org_id)
                return

            # Create a lookup map for device info
            device_map = {
                device["serial"]: {
                    "name": device.get("name", device["serial"]),
                    "model": device.get("model", "Unknown"),
                    "network_id": device.get("networkId", ""),
                }
                for device in devices
                if device["serial"] in mr_serials
            }

            logger.debug(
                "Fetching MR CPU load history",
                org_id=org_id,
                device_count=len(mr_serials),
                serials=mr_serials,
            )
            self._track_api_call("getOrganizationWirelessDevicesSystemCpuLoadHistory")

            # Note: The API might not return all requested devices in a single response
            # This could be due to timing (device just came online) or API limitations
            cpu_response = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory,
                org_id,
                serials=mr_serials,  # Only request MR devices
                timespan=3600,  # 1-hour window for better data availability
            )

            # Handle different API response formats
            if isinstance(cpu_response, dict) and "items" in cpu_response:
                cpu_data = cpu_response["items"]
            elif isinstance(cpu_response, list):
                cpu_data = cpu_response
            else:
                logger.warning(
                    "Unexpected CPU load response format",
                    org_id=org_id,
                    response_type=type(cpu_response).__name__,
                )
                cpu_data = []

            # Log which serials we got responses for
            returned_serials = [d.get("serial", "") for d in cpu_data] if cpu_data else []
            missing_serials = set(mr_serials) - set(returned_serials)

            logger.debug(
                "Successfully fetched MR CPU load data",
                org_id=org_id,
                device_count=len(cpu_data) if cpu_data else 0,
                returned_serials=returned_serials,
                missing_serials=list(missing_serials) if missing_serials else None,
            )

            # Process each device's CPU data
            for device_info in cpu_data:
                serial = device_info.get("serial", "")

                # Skip if not in our device map (shouldn't happen with serial filter)
                if serial not in device_map:
                    logger.warning(
                        "CPU data for unknown device",
                        serial=serial,
                        expected_serials=mr_serials,
                    )
                    continue

                device_details = device_map[serial]
                network = device_info.get("network", {})
                network_name = network.get("name", "")
                cpu_count = device_info.get("cpuCount")

                # Process CPU load data from series
                series = device_info.get("series", [])
                if series:
                    # Get the most recent entry
                    latest = series[-1]  # Series appears to be chronological
                    cpu_load_5 = latest.get("cpuLoad5")

                    logger.debug(
                        "Processing CPU load data",
                        serial=serial,
                        name=device_details["name"],
                        cpu_count=cpu_count,
                        cpu_load_5=cpu_load_5,
                        series_count=len(series),
                    )

                    if cpu_load_5 is not None and cpu_count:
                        # The cpuLoad5 value needs to be normalized
                        # Based on the values in the example (20000-24000 range for 4-core systems),
                        # it appears to be in basis points (1/10000) per core
                        # So we convert to percentage: (value / 10000) / cpu_count * 100
                        normalized_load = (cpu_load_5 / 10000) / cpu_count * 100

                        self._set_metric_value(
                            "_mr_cpu_load_5min",
                            {
                                "serial": serial,
                                "name": device_details["name"],
                                "model": device_details["model"],
                                "network_id": device_details["network_id"],
                                "network_name": network_name,
                            },
                            normalized_load,
                        )
                    else:
                        logger.warning(
                            "Missing CPU data for calculation",
                            serial=serial,
                            name=device_details["name"],
                            cpu_load_5=cpu_load_5,
                            cpu_count=cpu_count,
                        )
                else:
                    logger.debug(
                        "No CPU load series data available",
                        serial=serial,
                        name=device_details["name"],
                        has_cpu_count=cpu_count is not None,
                    )

        except Exception:
            logger.exception(
                "Failed to collect MR CPU load metrics",
                org_id=org_id,
            )

    async def _collect_mr_ssid_status(self, org_id: str) -> None:
        """Collect SSID and radio status for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            logger.debug("Fetching MR SSID statuses", org_id=org_id)
            self._track_api_call("getOrganizationWirelessSsidsStatusesByDevice")

            ssid_statuses = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessSsidsStatusesByDevice,
                org_id,
                hideDisabled=True,  # Only get active radios
                total_pages="all",
            )

            # Handle different API response formats
            if isinstance(ssid_statuses, dict) and "items" in ssid_statuses:
                ssid_data = ssid_statuses["items"]
            elif isinstance(ssid_statuses, list):
                ssid_data = ssid_statuses
            else:
                logger.warning(
                    "Unexpected SSID status format",
                    org_id=org_id,
                    response_type=type(ssid_statuses).__name__,
                )
                ssid_data = []

            logger.debug(
                "Successfully fetched MR SSID statuses",
                org_id=org_id,
                device_count=len(ssid_data) if ssid_data else 0,
            )

            # Process each device's SSID/radio data
            for device_data in ssid_data:
                serial = device_data.get("serial", "")
                name = device_data.get("name", serial)
                network = device_data.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", "")

                # Track unique radios to avoid duplicates
                processed_radios = set()

                # Process basic service sets
                basic_service_sets = device_data.get("basicServiceSets", [])
                for bss in basic_service_sets:
                    radio = bss.get("radio", {})
                    radio_index = radio.get("index", "")
                    band = radio.get("band", "")

                    # Create unique key for this radio
                    radio_key = f"{serial}:{band}:{radio_index}"

                    # Skip if we've already processed this radio
                    if radio_key in processed_radios:
                        continue
                    processed_radios.add(radio_key)

                    # Radio broadcasting status
                    is_broadcasting = radio.get("isBroadcasting", False)
                    self._set_metric_value(
                        "_mr_radio_broadcasting",
                        {
                            "serial": serial,
                            "name": name,
                            "network_id": network_id,
                            "network_name": network_name,
                            "band": band,
                            "radio_index": radio_index,
                        },
                        1 if is_broadcasting else 0,
                    )

                    # Channel number
                    channel = radio.get("channel")
                    if channel is not None:
                        self._set_metric_value(
                            "_mr_radio_channel",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": radio_index,
                            },
                            channel,
                        )

                    # Channel width
                    channel_width = radio.get("channelWidth")
                    if channel_width is not None:
                        self._set_metric_value(
                            "_mr_radio_channel_width",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": radio_index,
                            },
                            channel_width,
                        )

                    # Transmit power
                    power = radio.get("power")
                    if power is not None:
                        self._set_metric_value(
                            "_mr_radio_power",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": radio_index,
                            },
                            power,
                        )

        except Exception:
            logger.exception(
                "Failed to collect MR SSID status metrics",
                org_id=org_id,
            )
