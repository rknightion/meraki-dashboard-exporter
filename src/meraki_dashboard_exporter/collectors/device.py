"""Device-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import (
    DEFAULT_DEVICE_STATUS,
    DeviceMetricName,
    DeviceStatus,
    DeviceType,
    UpdateTier,
)
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.logging import get_logger
from ..core.metrics import LabelName
from ..core.registry import register_collector
from .devices import MGCollector, MRCollector, MSCollector, MTCollector, MVCollector, MXCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class DeviceCollector(MetricCollector):
    """Collector for device-level metrics."""

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
            DeviceType.MG: self.mg_collector,
            DeviceType.MR: self.mr_collector,
            DeviceType.MS: self.ms_collector,
            DeviceType.MT: self.mt_collector,
            DeviceType.MV: self.mv_collector,
            DeviceType.MX: self.mx_collector,
        }

        # Cache for retaining last known packet metric values
        self._packet_metrics_cache: dict[str, float] = {}

        # Initialize sub-collector metrics (only for collectors without their own __init__)
        self.ms_collector._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize device metrics."""
        # Common device metrics
        self._device_up = self._create_gauge(
            DeviceMetricName.DEVICE_UP,
            "Device online status (1 = online, 0 = offline)",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.NETWORK_ID,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._device_status_info = self._create_gauge(
            DeviceMetricName.DEVICE_STATUS_INFO,
            "Device status information",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.NETWORK_ID,
                LabelName.DEVICE_TYPE,
                LabelName.STATUS,
            ],
        )

        # Memory metrics - available via system memory usage history API
        self._device_memory_used_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_USED_BYTES,
            "Device memory used in bytes",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.NETWORK_ID,
                LabelName.DEVICE_TYPE,
                LabelName.STAT,
            ],
        )

        self._device_memory_free_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_FREE_BYTES,
            "Device memory free in bytes",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.NETWORK_ID,
                LabelName.DEVICE_TYPE,
                LabelName.STAT,
            ],
        )

        self._device_memory_total_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_TOTAL_BYTES,
            "Device memory total provisioned in bytes",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.NETWORK_ID,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._device_memory_usage_percent = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_USAGE_PERCENT,
            "Device memory usage percentage (maximum from most recent interval)",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.NETWORK_ID,
                LabelName.DEVICE_TYPE,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect device metrics."""
        try:
            # Get organizations with error handling
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found for device collection")
                return

            # Collect devices for each organization
            org_ids = [org["id"] for org in organizations]
            for org_id in org_ids:
                await self._collect_org_devices(org_id)

        except Exception:
            logger.exception("Failed to collect device metrics")

    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations for device collection.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        """
        if self.settings.org_id:
            return [{"id": self.settings.org_id}]
        else:
            logger.debug("Fetching all organizations for device collection")
            self._track_api_call("getOrganizations")
            orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
            orgs = validate_response_format(orgs, expected_type=list, operation="getOrganizations")
            logger.debug("Successfully fetched organizations", count=len(orgs))
            return orgs

    @with_error_handling(
        operation="Collect organization devices",
        continue_on_error=True,
    )
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

            # Fetch devices and availabilities separately to better handle timeouts
            devices = None

            # Store device lookup map for use in other collectors
            self._device_lookup: dict[str, dict[str, Any]] = {}

            # Fetch devices with error handling
            devices = await self._fetch_devices(org_id)
            if not devices:
                logger.warning("No devices found", org_id=org_id)
                return

            # Fetch availabilities with error handling
            availabilities = await self._fetch_device_availabilities(org_id) or []

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
                availability_count=len(availabilities),
            )

            # Create availability lookup by serial
            availability_map = {
                a["serial"]: a.get("status", DEFAULT_DEVICE_STATUS) for a in availabilities
            }

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

                # Add availability status to device
                device["availability_status"] = availability_map.get(
                    device["serial"], DEFAULT_DEVICE_STATUS
                )

                # Collect common metrics
                self._collect_common_metrics(device)

                # Group devices by type for batch processing
                if device_type not in devices_by_type:
                    devices_by_type[device_type] = []
                devices_by_type[device_type].append(device)

            # Store references for legacy code
            ms_devices = devices_by_type.get(DeviceType.MS, [])
            mr_devices = devices_by_type.get(DeviceType.MR, [])

            # Process MS devices
            if ms_devices:
                logger.debug(
                    "Processing MS devices",
                    count=len(ms_devices),
                )
                # Process devices in smaller batches to avoid overwhelming the API
                await process_in_batches_with_errors(
                    ms_devices,
                    self._collect_ms_device_with_timeout,
                    batch_size=5,
                    delay_between_batches=self.settings.api.batch_delay,
                    item_description="MS device",
                    error_context_func=lambda device: {"serial": device["serial"]},
                )

            # Process MR devices
            if mr_devices:
                logger.debug(
                    "Processing MR devices",
                    count=len(mr_devices),
                    mr_serials=[d["serial"] for d in mr_devices],
                )
                # Process devices in smaller batches to avoid overwhelming the API
                await process_in_batches_with_errors(
                    mr_devices,
                    self._collect_mr_device_with_timeout,
                    batch_size=5,
                    delay_between_batches=self.settings.api.batch_delay,
                    item_description="MR device",
                    error_context_func=lambda device: {"serial": device["serial"]},
                )

            # Process other device types (MX, MG, MV)
            for device_type, type_devices in devices_by_type.items():
                # Skip MS and MR as they're handled above (for now)
                if device_type in {DeviceType.MS, DeviceType.MR}:
                    continue

                if type_devices:
                    logger.debug(
                        f"Processing {device_type} devices",
                        count=len(type_devices),
                    )
                    # Process devices in smaller batches
                    await process_in_batches_with_errors(
                        type_devices,
                        lambda d, dt=device_type: self._collect_device_with_timeout(d, dt),
                        batch_size=5,
                        delay_between_batches=self.settings.api.batch_delay,
                        item_description=f"{device_type} device",
                        error_context_func=lambda device: {"serial": device["serial"]},
                    )

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
            if any(d for d in devices if d.get("model", "").startswith(DeviceType.MR)):
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

    async def _collect_device_with_timeout(
        self, device: dict[str, Any], device_type: DeviceType
    ) -> None:
        """Collect device metrics with timeout.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        device_type : DeviceType
            Device type enum value.

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

    async def _collect_mr_specific_metrics(
        self, org_id: str, devices: list[dict[str, Any]]
    ) -> None:
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
        availability_status = device.get("availability_status", DEFAULT_DEVICE_STATUS)

        # Device up/down status
        is_online = 1 if availability_status == DeviceStatus.ONLINE else 0
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
                "status": availability_status,
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

    @with_error_handling(
        operation="Fetch devices",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_devices(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch devices for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of devices or None on error.

        """
        logger.debug("Fetching devices list", org_id=org_id)
        self._track_api_call("getOrganizationDevices")

        devices = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevices,
            org_id,
            total_pages="all",
        )
        devices = validate_response_format(
            devices, expected_type=list, operation="getOrganizationDevices"
        )
        logger.debug(
            "Successfully fetched devices",
            org_id=org_id,
            count=len(devices),
        )
        return devices

    @with_error_handling(
        operation="Fetch device availabilities",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_device_availabilities(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch device availabilities for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of device availabilities or None on error.

        """
        logger.debug("Fetching device availabilities", org_id=org_id)
        self._track_api_call("getOrganizationDevicesAvailabilities")

        availabilities = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevicesAvailabilities,
            org_id,
            total_pages="all",
        )
        availabilities = validate_response_format(
            availabilities, expected_type=list, operation="getOrganizationDevicesAvailabilities"
        )

        logger.debug(
            "Successfully fetched availabilities",
            org_id=org_id,
            count=len(availabilities) if availabilities else 0,
        )
        return availabilities
