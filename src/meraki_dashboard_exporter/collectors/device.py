"""Device-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import (
    DEFAULT_DEVICE_STATUS,
    DeviceMetricName,
    DeviceStatus,
    DeviceType,
    MSMetricName,
    UpdateTier,
)
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.label_helpers import create_device_labels
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation
from ..core.logging_helpers import LogContext, log_metric_collection_summary
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

        # Initialize port overview metrics here since they're org-level
        self._ms_ports_active_total = self._create_gauge(
            MSMetricName.MS_PORTS_ACTIVE_TOTAL,
            "Total number of active switch ports",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
            ],
        )

        self._ms_ports_inactive_total = self._create_gauge(
            MSMetricName.MS_PORTS_INACTIVE_TOTAL,
            "Total number of inactive switch ports",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
            ],
        )

        self._ms_ports_by_media_total = self._create_gauge(
            MSMetricName.MS_PORTS_BY_MEDIA_TOTAL,
            "Total number of switch ports by media type",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.MEDIA,
                LabelName.STATUS,  # active or inactive
            ],
        )

        self._ms_ports_by_link_speed_total = self._create_gauge(
            MSMetricName.MS_PORTS_BY_LINK_SPEED_TOTAL,
            "Total number of active switch ports by link speed",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.MEDIA,
                LabelName.LINK_SPEED,  # speed in Mbps
            ],
        )

    def _initialize_metrics(self) -> None:
        """Initialize device metrics."""
        # Common device metrics
        self._device_up = self._create_gauge(
            DeviceMetricName.DEVICE_UP,
            "Device online status (1 = online, 0 = offline)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._device_status_info = self._create_gauge(
            DeviceMetricName.DEVICE_STATUS_INFO,
            "Device status information",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.STATUS,
            ],
        )

        # Memory metrics - available via system memory usage history API
        self._device_memory_used_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_USED_BYTES,
            "Device memory used in bytes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.STAT,
            ],
        )

        self._device_memory_free_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_FREE_BYTES,
            "Device memory free in bytes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.STAT,
            ],
        )

        self._device_memory_total_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_TOTAL_BYTES,
            "Device memory total provisioned in bytes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._device_memory_usage_percent = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_USAGE_PERCENT,
            "Device memory usage percentage (maximum from most recent interval)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect device metrics."""
        start_time = asyncio.get_event_loop().time()
        metrics_collected = 0
        organizations_processed = 0
        api_calls_made = 0

        try:
            # Get organizations with error handling
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found for device collection")
                return
            api_calls_made += 1

            # Collect devices for each organization
            for org in organizations:
                await self._collect_org_devices(org["id"], org.get("name", org["id"]))
                organizations_processed += 1
                # Each org makes multiple API calls
                api_calls_made += 10  # Approximate

            # Log collection summary
            log_metric_collection_summary(
                "DeviceCollector",
                metrics_collected=metrics_collected,
                duration_seconds=asyncio.get_event_loop().time() - start_time,
                organizations_processed=organizations_processed,
                api_calls_made=api_calls_made,
            )

        except Exception:
            logger.exception("Failed to collect device metrics")

    @log_api_call("getOrganizations")
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
        if self.settings.meraki.org_id:
            return [{"id": self.settings.meraki.org_id}]
        else:
            with LogContext(operation="fetch_organizations"):
                orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
                orgs = validate_response_format(
                    orgs, expected_type=list, operation="getOrganizations"
                )
                return cast(list[dict[str, Any]], orgs)

    @log_batch_operation("collect devices", batch_size=None)
    @with_error_handling(
        operation="Collect organization devices",
        continue_on_error=True,
    )
    async def _collect_org_devices(self, org_id: str, org_name: str) -> None:
        """Collect device metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id):
                # Store device lookup map for use in other collectors
                self._device_lookup: dict[str, dict[str, Any]] = {}

                # Fetch devices with error handling
                devices = await self._fetch_devices(org_id)
                if not devices:
                    logger.warning("No devices found", org_id=org_id)
                    return

                # Fetch availabilities with error handling
                availabilities = await self._fetch_device_availabilities(org_id) or []

                logger.debug(
                    "Processing devices",
                    device_count=len(devices),
                    availability_count=len(availabilities),
                )

            # Create availability lookup by serial
            availability_map = {
                a["serial"]: a.get("status", DEFAULT_DEVICE_STATUS) for a in availabilities
            }

            # Fetch network information for adding network names to devices
            networks = await self._fetch_networks_for_poe(org_id)
            network_map = {n["id"]: n["name"] for n in networks}

            # Group devices by type for batch processing
            devices_by_type: dict[DeviceType, list[dict[str, Any]]] = {}

            for device in devices:
                device_type_str = self._get_device_type(device)

                # Add to device lookup map
                serial = device["serial"]
                network_id = device.get("networkId", "")
                self._device_lookup[serial] = {
                    "name": device.get("name", serial),
                    "model": device.get("model", "Unknown"),
                    "network_id": network_id,
                    "network_name": network_map.get(network_id, network_id),
                    "device_type": device_type_str,
                }

                # Skip unsupported device types
                if device_type_str not in DeviceType.__members__.values():
                    logger.debug(
                        "Skipping device with unsupported type",
                        serial=device["serial"],
                        model=device.get("model", "Unknown"),
                        device_type=device_type_str,
                    )
                    continue

                # Convert to enum
                device_type = DeviceType(device_type_str)

                # Add availability status to device
                device["availability_status"] = availability_map.get(
                    device["serial"], DEFAULT_DEVICE_STATUS
                )

                # Add network name to device data
                network_id = device.get("networkId", "")
                device["networkName"] = network_map.get(network_id, network_id)

                # Add organization info to device data
                device["orgId"] = org_id
                device["orgName"] = org_name

                # Collect common metrics
                self._collect_common_metrics(device, org_id, org_name)

                # Group devices by type for batch processing
                if device_type not in devices_by_type:
                    devices_by_type[device_type] = []
                devices_by_type[device_type].append(device)

            # Store references for legacy code
            ms_devices = devices_by_type.get(DeviceType.MS, [])
            mr_devices = devices_by_type.get(DeviceType.MR, [])

            # Process MS devices
            if ms_devices:
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
                    # Process devices in smaller batches
                    # Create a coroutine factory to avoid loop variable issues
                    def make_collect_coroutine(dt: DeviceType) -> Any:
                        async def collect_device(d: dict[str, Any]) -> None:
                            await self._collect_device_with_timeout(d, dt)

                        return collect_device

                    await process_in_batches_with_errors(
                        type_devices,
                        make_collect_coroutine(device_type),
                        batch_size=5,
                        delay_between_batches=self.settings.api.batch_delay,
                        item_description=f"{device_type} device",
                        error_context_func=lambda device: {"serial": device["serial"]},
                    )

            # Aggregate network-wide POE metrics after all switches are collected
            try:
                await self._aggregate_network_poe(org_id, org_name, devices)
            except Exception:
                logger.exception("Failed to aggregate POE metrics")

            # Collect switch port overview metrics
            try:
                await self._collect_switch_port_overview(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect switch port overview")

            # Collect memory metrics for all devices
            try:
                # Use base collector's memory collection
                await self.ms_collector.collect_memory_metrics(
                    org_id, org_name, self._device_lookup
                )
            except Exception:
                logger.exception("Failed to collect memory metrics")

            # Collect MR-specific metrics
            if any(d for d in devices if d.get("model", "").startswith(DeviceType.MR)):
                # Use MR collector for all MR-specific metrics
                await self._collect_mr_specific_metrics(org_id, org_name, devices)

            # Collect MS-specific metrics
            if any(d for d in devices if d.get("model", "").startswith(DeviceType.MS)):
                # Use MS collector for all MS-specific metrics
                await self._collect_ms_specific_metrics(org_id, org_name, devices)

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
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> None:
        """Collect MR-specific organization-wide metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            All devices in the organization.

        """
        try:
            # Collect wireless client counts
            try:
                await self.mr_collector.collect_wireless_clients(
                    org_id, org_name, self._device_lookup
                )
            except Exception:
                logger.exception("Failed to collect wireless client counts")

            # Collect MR ethernet status
            try:
                await self.mr_collector.collect_ethernet_status(
                    org_id, org_name, self._device_lookup
                )
            except Exception:
                logger.exception("Failed to collect MR ethernet status")

            # Collect MR packet loss metrics
            try:
                await self.mr_collector.collect_packet_loss(org_id, org_name, self._device_lookup)
            except Exception:
                logger.exception("Failed to collect MR packet loss metrics")

            # Collect MR CPU load metrics
            try:
                await self.mr_collector.collect_cpu_load(org_id, org_name, devices)
            except Exception:
                logger.exception("Failed to collect MR CPU load metrics")

            # Collect MR SSID status metrics
            try:
                await self.mr_collector.collect_ssid_status(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect MR SSID status metrics")

            # Collect MR SSID usage metrics
            try:
                await self.mr_collector.collect_ssid_usage(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect MR SSID usage metrics")

        except Exception:
            logger.exception(
                "Failed to collect MR-specific metrics",
                org_id=org_id,
            )

    async def _collect_ms_specific_metrics(
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> None:
        """Collect MS-specific organization-wide metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            All devices in the organization.

        """
        try:
            # Collect STP metrics
            try:
                await self.ms_collector.collect_stp_priorities(
                    org_id, org_name, self._device_lookup
                )
            except Exception:
                logger.exception("Failed to collect STP priorities")
        except Exception:
            logger.exception(
                "Failed to collect MS-specific metrics",
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

    def _collect_common_metrics(self, device: dict[str, Any], org_id: str, org_name: str) -> None:
        """Collect common device metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        availability_status = device.get("availability_status", DEFAULT_DEVICE_STATUS)

        # Create standard device labels
        labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        # Device up/down status
        is_online = 1 if availability_status == DeviceStatus.ONLINE else 0
        self._set_metric_value(
            "_device_up",
            labels,
            is_online,
        )

        # Device status info metric
        status_labels = create_device_labels(
            device, org_id=org_id, org_name=org_name, status=availability_status
        )
        self._set_metric_value(
            "_device_status_info",
            status_labels,
            1,
        )

        # Uptime
        if "uptimeInSeconds" in device:
            self._set_metric_value(
                "_device_uptime",
                labels,
                device["uptimeInSeconds"],
            )

    @log_api_call("getOrganizationNetworks")
    async def _fetch_networks_for_poe(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch networks for POE aggregation.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of networks.

        """
        with LogContext(org_id=org_id):
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            return cast(list[dict[str, Any]], networks)

    async def _aggregate_network_poe(
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> None:
        """Aggregate POE metrics at the network level.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            All devices in the organization.

        """
        try:
            # Get network names
            networks = await self._fetch_networks_for_poe(org_id)
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
                total_poe = 0.0
                for serial in switch_serials:
                    # Get the current value from the metric
                    try:
                        # Find the switch in devices list to verify it exists
                        _ = next(d for d in devices if d["serial"] == serial)

                        # Get the POE value from the already collected metric
                        # The metric is indexed by serial, name, model, and network_id
                        for metric_sample in self.ms_collector._switch_poe_total_power._samples():
                            labels = metric_sample[1]
                            if (
                                labels.get("serial") == serial
                                and labels.get("network_id") == network_id
                            ):
                                total_poe += metric_sample[2]  # Add the value
                                break

                    except StopIteration:
                        logger.debug("Switch not found in devices list", serial=serial)
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
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                ).set(total_poe)

                logger.debug(
                    "Set network POE total",
                    network_id=network_id,
                    network_name=network_name,
                    total_poe=total_poe,
                    switch_count=len(switch_serials),
                )

        except Exception:
            logger.exception(
                "Failed to aggregate network POE metrics",
                org_id=org_id,
            )

    @log_api_call("getOrganizationSwitchPortsOverview")
    @with_error_handling(
        operation="Collect switch port overview",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_switch_port_overview(self, org_id: str, org_name: str) -> None:
        """Collect switch port overview metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # Call the API with required timespan
        overview = await asyncio.to_thread(
            self.api.switch.getOrganizationSwitchPortsOverview,
            org_id,
            timespan=43200,  # 12 hours as required
        )

        # Parse the counts structure
        counts = overview.get("counts", {})

        # Set total active/inactive counts
        active_count = counts.get("byStatus", {}).get("active", {}).get("total", 0)
        inactive_count = counts.get("byStatus", {}).get("inactive", {}).get("total", 0)

        self._ms_ports_active_total.labels(
            org_id=org_id,
            org_name=org_name,
        ).set(active_count)

        self._ms_ports_inactive_total.labels(
            org_id=org_id,
            org_name=org_name,
        ).set(inactive_count)

        logger.debug(
            "Set port overview totals",
            org_id=org_id,
            active_count=active_count,
            inactive_count=inactive_count,
        )

        # Process active ports by media and link speed
        active_data = counts.get("byStatus", {}).get("active", {})
        by_media_speed = active_data.get("byMediaAndLinkSpeed", {})

        for media_type, media_data in by_media_speed.items():
            # Set total for this media type (active)
            media_total = media_data.get("total", 0)
            self._ms_ports_by_media_total.labels(
                org_id=org_id,
                org_name=org_name,
                media=media_type,
                status="active",
            ).set(media_total)

            # Set breakdown by link speed
            for speed, count in media_data.items():
                if speed != "total" and isinstance(count, (int, float)):
                    self._ms_ports_by_link_speed_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                        media=media_type,
                        link_speed=str(speed),  # Speed in Mbps
                    ).set(count)

                    logger.debug(
                        "Set port link speed count",
                        org_id=org_id,
                        media=media_type,
                        speed=speed,
                        count=count,
                    )

        # Process inactive ports by media
        inactive_data = counts.get("byStatus", {}).get("inactive", {})
        by_media = inactive_data.get("byMedia", {})

        for media_type, media_data in by_media.items():
            media_total = media_data.get("total", 0)
            self._ms_ports_by_media_total.labels(
                org_id=org_id,
                org_name=org_name,
                media=media_type,
                status="inactive",
            ).set(media_total)

        logger.debug(
            "Completed switch port overview collection",
            org_id=org_id,
        )

    @log_api_call("getOrganizationDevices")
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
        with LogContext(org_id=org_id):
            devices = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
            )
            devices = validate_response_format(
                devices, expected_type=list, operation="getOrganizationDevices"
            )
            return cast(list[dict[str, Any]], devices)

    @log_api_call("getOrganizationDevicesAvailabilities")
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
        with LogContext(org_id=org_id):
            availabilities = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesAvailabilities,
                org_id,
                total_pages="all",
            )
            availabilities = validate_response_format(
                availabilities, expected_type=list, operation="getOrganizationDevicesAvailabilities"
            )
            return cast(list[dict[str, Any]], availabilities)
