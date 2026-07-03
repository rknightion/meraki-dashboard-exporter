"""Device-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

from ..core.async_utils import ManagedTaskGroup
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import (
    DEFAULT_DEVICE_STATUS,
    DeviceMetricName,
    DeviceStatus,
    DeviceType,
    UpdateTier,
)
from ..core.error_handling import (
    CollectorError,
    ErrorCategory,
    NothingCollectedError,
    validate_response_format,
    with_error_handling,
)
from ..core.label_helpers import create_device_labels
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.otel_tracing import trace_method
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName, pages
from .devices import (
    MGCollector,
    MRCollector,
    MSCollector,
    MSStackCollector,
    MTCollector,
    MVCollector,
    MXCollector,
)
from .devices.ms_power import MSPowerCollector
from .devices.mx_ha import MXHACollector
from .devices.mx_uplink_health import MXUplinkHealthCollector
from .devices.mx_uplink_usage import MXUplinkUsageCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..core.org_health import OrgHealthTracker
    from ..services.inventory import OrganizationInventory

from ..core.org_health import SOURCE_DEVICE

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class DeviceCollector(MetricCollector):
    """Collector for device-level metrics."""

    # #617 §2 — every MEDIUM endpoint group owned by DeviceCollector (including
    # those whose fetch sites live in the per-device-type sub-collectors, which
    # gate against these declarations via ``self.parent._should_run_group``).
    # cost_fn returns the estimated API calls (incl. pagination) for ONE run.
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.DEVICE_AVAILABILITY,
            priority=1,
            floor_seconds=120,
            cost_fn=lambda s: pages(s.device_count, 500),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.DEVICE_MEMORY,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.device_count, 20),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_WIRELESS_CLIENTS,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.ap_count, 1000),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_CONNECTION_STATS,
            priority=3,
            floor_seconds=1800,
            cost_fn=lambda s: float(s.wireless_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_ETHERNET_STATUS,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.ap_count, 1000),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_PACKET_LOSS,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: 2 * pages(s.ap_count, 1000),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_CPU_LOAD,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.ap_count, 20),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_SSID_STATUS,
            priority=2,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.ap_count, 500),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MR_SSID_USAGE,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_PORT_STATUS,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.switch_count, 20),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_PORT_USAGE,
            priority=3,
            floor_seconds=600,
            cost_fn=lambda s: pages(s.switch_count, 50) + pages(s.switch_count, 20),
            tier=UpdateTier.MEDIUM,
            setting_pin="ms_port_usage_interval",
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_PACKET_STATS,
            priority=3,
            floor_seconds=600,
            cost_fn=lambda s: float(s.switch_count),
            tier=UpdateTier.MEDIUM,
            setting_pin="ms_packet_stats_interval",
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_PORT_OVERVIEW,
            priority=4,
            floor_seconds=3600,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_POWER,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.switch_count, 1000),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_STACKS,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: float(s.switch_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_STP,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: float(s.switch_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_UPLINK_STATUS,
            priority=1,
            floor_seconds=300,
            cost_fn=lambda s: pages(s.appliance_count, 1000),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_UPLINK_HEALTH,
            priority=1,
            floor_seconds=300,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_UPLINK_USAGE,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_PERFORMANCE,
            priority=3,
            floor_seconds=900,
            cost_fn=lambda s: float(s.physical_mx_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_HA,
            priority=2,
            floor_seconds=300,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_VPN,
            priority=2,
            floor_seconds=300,
            cost_fn=lambda s: 2.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_SECURITY_EVENTS,
            priority=2,
            floor_seconds=300,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_FIREWALL_CONFIG,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: 2 * s.appliance_network_count,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MV_ANALYTICS,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: 3 * s.camera_count,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MG_UPLINK_STATUS,
            priority=1,
            floor_seconds=300,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
    )

    @property
    def api(self) -> DashboardAPI:
        """The current API client."""
        return self._api

    @api.setter
    def api(self, api: DashboardAPI) -> None:
        """Update the API client and propagate to subcollectors when ready."""
        self._api = api
        if getattr(self, "_subcollectors_ready", False):
            self._sync_subcollector_api()

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

        # Record this key as active in the current collection cycle
        self._active_cache_keys.add(cache_key)

        # Use regular metric setting
        self._set_metric_value(metric_name, labels, value)

    def _evict_stale_cache_entries(self, active_keys: set[str]) -> None:
        """Remove packet metric cache entries that were not updated this cycle.

        Parameters
        ----------
        active_keys : set[str]
            Cache keys that were written during the current collection cycle.
            Any key in ``_packet_metrics_cache`` that is absent from this set
            belongs to a device (or label combination) no longer present and
            should be evicted to prevent unbounded memory growth.

        """
        stale_keys = set(self._packet_metrics_cache) - active_keys
        for key in stale_keys:
            del self._packet_metrics_cache[key]
        if stale_keys:
            logger.debug(
                "Evicted stale packet metric cache entries",
                evicted_count=len(stale_keys),
                remaining_count=len(self._packet_metrics_cache),
            )

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
        inventory: OrganizationInventory | None = None,
        expiration_manager: MetricExpirationManager | None = None,
        rate_limiter: Any | None = None,
        scheduler: Any | None = None,
        org_health_tracker: OrgHealthTracker | None = None,
    ) -> None:
        """Initialize device collector with sub-collectors."""
        self._subcollectors_ready = False
        super().__init__(
            api,
            settings,
            registry,
            inventory,
            expiration_manager,
            rate_limiter,
            scheduler=scheduler,
        )

        # Shared per-org health tracker (F-169 / #547): when present, per-org
        # collection is skipped for organizations currently in backoff, AND this
        # collector reports its own per-org verdict into the tracker under the
        # SOURCE_DEVICE failure domain so device-endpoint failures engage backoff
        # even when the organization collector is healthy or disabled.
        self.org_health_tracker = org_health_tracker

        # Initialize device-specific collectors
        self.mg_collector = MGCollector(self)
        self.mr_collector = MRCollector(self)
        self.ms_collector = MSCollector(self)
        self.ms_stack_collector = MSStackCollector(self)
        self.mt_collector = MTCollector.as_subcollector(self)
        self.mv_collector = MVCollector(self)
        self.mx_collector = MXCollector(self)
        # Org-wide standalone sub-collectors (not per-device-type dispatched)
        self.mx_uplink_health_collector = MXUplinkHealthCollector(self)
        self.mx_uplink_usage_collector = MXUplinkUsageCollector(self)
        self.mx_ha_collector = MXHACollector(self)
        self.ms_power_collector = MSPowerCollector(self)

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
        # Tracks which cache keys were touched during the current collection cycle
        self._active_cache_keys: set[str] = set()

        # Ensure all subcollectors share the current API instance
        self._subcollectors_ready = True
        self._sync_subcollector_api()

    def _sync_subcollector_api(self) -> None:
        """Ensure subcollectors use the current API client."""
        for collector in self._device_collectors.values():
            collector.update_api(self.api)
        self.ms_stack_collector.update_api(self.api)
        self.mx_uplink_health_collector.update_api(self.api)
        self.mx_uplink_usage_collector.update_api(self.api)
        self.mx_ha_collector.update_api(self.api)
        self.ms_power_collector.update_api(self.api)

    def _initialize_metrics(self) -> None:
        """Initialize device metrics."""
        # Common device metrics
        self._device_up = self._create_gauge(
            DeviceMetricName.DEVICE_UP,
            "Device online status (1 = online, 0 = offline)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._device_status_info = self._create_gauge(
            DeviceMetricName.DEVICE_STATUS_INFO,
            "Device status information",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
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
            "Device memory used in bytes (derived from the API's binary KiB value x1024), "
            "5-min window",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.STAT,
            ],
        )

        self._device_memory_free_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_FREE_BYTES,
            "Device memory free in bytes (derived from the API's binary KiB value x1024), "
            "5-min window",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.STAT,
            ],
        )

        self._device_memory_total_bytes = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_TOTAL_BYTES,
            "Device memory total provisioned in bytes (derived from the API's binary KiB value x1024)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._device_memory_usage_percent = self._create_gauge(
            DeviceMetricName.DEVICE_MEMORY_USAGE_PERCENT,
            "Device memory usage percentage (maximum from most recent interval)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect device metrics with parallel organization processing.

        Organizations are processed in parallel with bounded concurrency
        to significantly improve performance for multi-org deployments.
        """
        start_time = asyncio.get_event_loop().time()
        metrics_collected = 0
        organizations_processed = 0
        api_calls_made = 0

        # Reset active-key tracker for this collection cycle
        self._active_cache_keys = set()

        # Get organizations with error handling
        organizations = await self._fetch_organizations()
        if not organizations:
            logger.warning("No organizations found for device collection")
            return
        api_calls_made += 1

        logger.info(
            "Starting parallel organization processing",
            org_count=len(organizations),
            concurrency_limit=self.settings.api.concurrency_limit,
        )

        # Process organizations in parallel with bounded concurrency. Backoff
        # gating happens here (before task creation) rather than inside the
        # worker so an all-in-backoff cycle can be distinguished from a
        # genuine success (#509 frozen coordinator rule).
        skipped_backoff = 0
        async with ManagedTaskGroup(
            name="device_collector_orgs",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for org in organizations:
                org_id = org["id"]
                if (
                    self.org_health_tracker is not None
                    and not self.org_health_tracker.should_collect(org_id)
                ):
                    skipped_backoff += 1
                    logger.debug(
                        "Skipping device collection for organization in backoff",
                        org_id=org_id,
                        org_name=org.get("name", org_id),
                    )
                    continue
                await group.create_task(
                    self._collect_org_devices(org_id, org.get("name", org_id)),
                    name=f"org_{org_id}",
                )
                organizations_processed += 1

        attempted = len(organizations) - skipped_backoff
        if (
            organizations
            and group.succeeded_count == 0
            and (group.failed_count > 0 or attempted == 0)
        ):
            raise NothingCollectedError(
                self.__class__.__name__,
                attempted=attempted,
                failed=group.failed_count,
                skipped_backoff=skipped_backoff,
            )

        # Approximate API calls (actual count may vary)
        api_calls_made += organizations_processed * 10

        # Evict packet metric cache entries for devices no longer seen this cycle
        self._evict_stale_cache_entries(self._active_cache_keys)
        # Evict MS collector timestamp caches for serials no longer seen this cycle
        self.ms_collector._evict_stale_serials(self.ms_collector._active_serials)
        # Reset MS active serials for next cycle
        self.ms_collector._active_serials = set()

        # Log collection summary
        log_metric_collection_summary(
            "DeviceCollector",
            metrics_collected=metrics_collected,
            duration_seconds=asyncio.get_event_loop().time() - start_time,
            organizations_processed=organizations_processed,
            api_calls_made=api_calls_made,
        )

    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]]:
        """Fetch organizations for device collection using inventory cache.

        Returns
        -------
        list[dict[str, Any]]
            List of organizations.

        Raises
        ------
        RuntimeError
            If inventory service is not configured.

        """
        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for DeviceCollector. "
                "This is a programming error - collectors must be initialized with inventory service."
            )

        return await self.inventory.get_organizations()

    @trace_method("process.organization")
    @log_batch_operation("collect devices", batch_size=None)
    @with_error_handling(
        operation="Collect organization devices",
        continue_on_error=False,
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
        # #547: report this org's device-domain verdict into the shared tracker.
        # The verdict mirrors the coordinator's raise/return accounting exactly --
        # the worker "fails" (raises CollectorError) only when the device fetch
        # fails; every normal or swallowed-error return is a device-domain success.
        # Recorded in a finally so exactly one verdict is written per org per
        # cycle, on every control-flow path, before the raise propagates.
        device_failed = False
        try:
            with LogContext(org_id=org_id):
                # Local device lookup map - must not be an instance attribute
                # to avoid race conditions during concurrent org processing
                device_lookup: dict[str, dict[str, Any]] = {}

                # Fetch devices with error handling
                devices = await self._fetch_devices(org_id)
                if devices is None:
                    raise CollectorError(
                        "Device fetch failed for organization",
                        ErrorCategory.API_CLIENT_ERROR,
                        {"org_id": org_id},
                    )
                if not devices:
                    logger.info("No devices found", org_id=org_id)
                    return

                # #617: gate the org-wide availabilities fetch by the
                # device_availability endpoint group. When the scheduler says the
                # group isn't due this cycle we skip the refetch entirely and let
                # the device_up/status_info series ride on their (stretched) TTL
                # rather than re-emitting them with stale/default statuses.
                availability_due = self._should_run_group(EndpointGroupName.DEVICE_AVAILABILITY)
                if availability_due:
                    availabilities = await self._fetch_device_availabilities(org_id) or []
                    self._mark_group_ran(EndpointGroupName.DEVICE_AVAILABILITY)
                else:
                    availabilities = []

                logger.debug(
                    "Processing devices",
                    device_count=len(devices),
                    availability_count=len(availabilities),
                    availability_due=availability_due,
                )

            # Resolved TTL for the device_availability group's series (device_up,
            # status_info); None when no scheduler ⇒ tier-derived TTL applies.
            availability_ttl = self._group_ttl_seconds(EndpointGroupName.DEVICE_AVAILABILITY)

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
                device_lookup[serial] = {
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
                self._collect_common_metrics(
                    device,
                    org_id,
                    org_name,
                    availability_due=availability_due,
                    availability_ttl=availability_ttl,
                )

                # Group devices by type for batch processing
                if device_type not in devices_by_type:
                    devices_by_type[device_type] = []
                devices_by_type[device_type].append(device)

            # Store references for device processing
            ms_devices = devices_by_type.get(DeviceType.MS, [])

            # Process MS devices
            if ms_devices:
                spread_window = self._get_smoothing_window()
                min_delay = self.settings.api.smoothing_min_batch_delay
                max_delay = self.settings.api.smoothing_max_batch_delay
                used_fallback = False

                if self.settings.api.ms_port_status_use_org_endpoint:
                    status_result = await self.ms_collector.collect_port_statuses_by_switch(
                        org_id,
                        org_name,
                        ms_devices,
                    )
                    if not status_result:
                        used_fallback = True
                        logger.warning(
                            "Org-level switch port status collection failed; falling back to per-device status",
                            org_id=org_id,
                        )
                        await process_in_batches_with_errors(
                            ms_devices,
                            self._collect_ms_device_with_timeout,
                            batch_size=self.settings.api.device_batch_size,
                            delay_between_batches=self.settings.api.batch_delay,
                            spread_over_seconds=spread_window,
                            initial_delay=self._get_smoothing_offset(f"{org_id}:ms_devices"),
                            min_batch_delay=min_delay,
                            max_batch_delay=max_delay,
                            item_description="MS device",
                            error_context_func=lambda device: {"serial": device["serial"]},
                            on_error=lambda: self._track_error(ErrorCategory.UNKNOWN),
                        )

                    if not used_fallback:
                        usage_devices = [
                            device
                            for device in ms_devices
                            if self.ms_collector._should_collect_port_usage(
                                device.get("serial", "")
                            )
                        ]

                        if usage_devices:
                            # Prefer the org-wide usage/PoE endpoints (2 calls per
                            # org) over the per-switch loop (~1 call per switch) -
                            # F-168. Falls back to the per-device batched loop only
                            # when the SDK lacks the org-wide endpoints.
                            usage_result = await self.ms_collector.collect_port_usage_by_switch(
                                org_id,
                                org_name,
                                usage_devices,
                            )
                            if not usage_result:
                                await process_in_batches_with_errors(
                                    usage_devices,
                                    self.ms_collector.collect_device_port_usage_metrics,
                                    batch_size=self.settings.api.device_batch_size,
                                    delay_between_batches=self.settings.api.batch_delay,
                                    spread_over_seconds=spread_window,
                                    initial_delay=self._get_smoothing_offset(f"{org_id}:ms_usage"),
                                    min_batch_delay=min_delay,
                                    max_batch_delay=max_delay,
                                    item_description="MS port usage",
                                    error_context_func=lambda device: {"serial": device["serial"]},
                                    on_error=lambda: self._track_error(ErrorCategory.UNKNOWN),
                                )
                else:
                    # Process devices in batches (configurable via device_batch_size)
                    used_fallback = True
                    await process_in_batches_with_errors(
                        ms_devices,
                        self._collect_ms_device_with_timeout,
                        batch_size=self.settings.api.device_batch_size,
                        delay_between_batches=self.settings.api.batch_delay,
                        spread_over_seconds=spread_window,
                        initial_delay=self._get_smoothing_offset(f"{org_id}:ms_devices"),
                        min_batch_delay=min_delay,
                        max_batch_delay=max_delay,
                        item_description="MS device",
                        error_context_func=lambda device: {"serial": device["serial"]},
                        on_error=lambda: self._track_error(ErrorCategory.UNKNOWN),
                    )

                # Collect packet statistics with smoothing and interval gating
                if not used_fallback:
                    await process_in_batches_with_errors(
                        ms_devices,
                        self.ms_collector._collect_packet_statistics,
                        batch_size=self.settings.api.device_batch_size,
                        delay_between_batches=self.settings.api.batch_delay,
                        spread_over_seconds=spread_window,
                        initial_delay=self._get_smoothing_offset(f"{org_id}:ms_packets"),
                        min_batch_delay=min_delay,
                        max_batch_delay=max_delay,
                        item_description="MS packet stats",
                        error_context_func=lambda device: {"serial": device["serial"]},
                        on_error=lambda: self._track_error(ErrorCategory.UNKNOWN),
                    )

            # Note: MR per-device collection has been replaced with org/network-level
            # collection for efficiency. Client counts use org-wide endpoint and
            # connection stats use network-level endpoint. See _collect_mr_specific_metrics().

            # Process other device types (MX, MG, MV)
            for device_type, type_devices in devices_by_type.items():
                # Skip MS and MR as they're handled above (for now)
                if device_type in {DeviceType.MS, DeviceType.MR}:
                    continue

                if type_devices:
                    # Process devices in batches (configurable via device_batch_size)
                    # Create a coroutine factory to avoid loop variable issues
                    def make_collect_coroutine(dt: DeviceType) -> Any:
                        async def collect_device(d: dict[str, Any]) -> None:
                            await self._collect_device_with_timeout(d, dt)

                        return collect_device

                    await process_in_batches_with_errors(
                        type_devices,
                        make_collect_coroutine(device_type),
                        batch_size=self.settings.api.device_batch_size,
                        delay_between_batches=self.settings.api.batch_delay,
                        item_description=f"{device_type} device",
                        error_context_func=lambda device: {"serial": device["serial"]},
                        on_error=lambda: self._track_error(ErrorCategory.UNKNOWN),
                    )

            # Aggregate network-wide POE metrics after all switches are collected
            try:
                await self._aggregate_network_poe(org_id, org_name, devices)
            except Exception:
                logger.exception("Failed to aggregate POE metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect switch port overview metrics
            try:
                await self.ms_collector.collect_port_overview(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect switch port overview")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect memory metrics for all devices
            try:
                # Use base collector's memory collection
                await self.ms_collector.collect_memory_metrics(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect memory metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect MR-specific metrics
            if any(d for d in devices if d.get("model", "").startswith(DeviceType.MR)):
                # Use MR collector for all MR-specific metrics
                await self._collect_mr_specific_metrics(org_id, org_name, devices, device_lookup)

            # Collect MS-specific metrics. Gate on productType == "switch" in addition
            # to the "MS"-prefixed model check so Meraki-managed Catalyst switches
            # (productType "switch", model not prefixed "MS", e.g. "C9300-48P") are
            # not silently skipped for the org-wide MS block (STP priorities,
            # ms_stack, port overview, PSU/power-supply collector) - see F-030.
            if any(
                d
                for d in devices
                if d.get("model", "").startswith(DeviceType.MS) or d.get("productType") == "switch"
            ):
                # Use MS collector for all MS-specific metrics
                await self._collect_ms_specific_metrics(org_id, org_name, devices, device_lookup)

            # Collect MX-specific metrics
            if any(
                d
                for d in devices
                if d.get("model", "").startswith(DeviceType.MX)
                or d.get("productType") == "appliance"
            ):
                await self._collect_mx_specific_metrics(org_id, org_name, device_lookup)

            # Collect MG-specific metrics
            if any(d for d in devices if d.get("model", "").startswith(DeviceType.MG)):
                await self._collect_mg_specific_metrics(org_id, org_name, device_lookup)

        except CollectorError:
            device_failed = True
            raise
        except Exception as e:
            logger.exception(
                "Failed to collect devices for organization",
                org_id=org_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            self._track_error(ErrorCategory.UNKNOWN)
        finally:
            self._record_org_health_verdict(org_id, org_name, success=not device_failed)

    def _record_org_health_verdict(self, org_id: str, org_name: str, *, success: bool) -> None:
        """Report this org's device-domain verdict into the shared tracker (#547).

        No-op when no tracker is wired. Runs synchronously (no await) so
        concurrent per-org workers never interleave a read-modify-write on the
        tracker's per-source counters.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        success : bool
            True to record a device-domain success for this org, False a failure.

        """
        if self.org_health_tracker is None:
            return
        if success:
            self.org_health_tracker.record_success(org_id, org_name, source=SOURCE_DEVICE)
        else:
            self.org_health_tracker.record_failure(org_id, org_name, source=SOURCE_DEVICE)

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

    @trace_method("collect.mr_metrics")
    async def _collect_mr_specific_metrics(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
        device_lookup: dict[str, dict[str, Any]],
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
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        try:
            # Get networks for connection stats collection
            networks: list[dict[str, Any]] = []
            if self.inventory:
                networks = await self.inventory.get_networks(org_id)

            # Collect wireless client counts (org-wide - replaces per-device getDeviceWirelessStatus)
            try:
                await self.mr_collector.collect_wireless_clients(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect wireless client counts")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect connection stats (network-level - replaces per-device getDeviceWirelessConnectionStats)
            if networks:
                try:
                    await self.mr_collector.collect_connection_stats(
                        org_id, org_name, networks, device_lookup
                    )
                except Exception:
                    logger.exception("Failed to collect MR connection stats")
                    self._track_error(ErrorCategory.UNKNOWN)

            # Collect MR ethernet status
            try:
                await self.mr_collector.collect_ethernet_status(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect MR ethernet status")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect MR packet loss metrics
            try:
                await self.mr_collector.collect_packet_loss(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect MR packet loss metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect MR CPU load metrics
            try:
                await self.mr_collector.collect_cpu_load(org_id, org_name, devices)
            except Exception:
                logger.exception("Failed to collect MR CPU load metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect MR SSID status metrics
            try:
                await self.mr_collector.collect_ssid_status(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect MR SSID status metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect MR SSID usage metrics
            try:
                await self.mr_collector.collect_ssid_usage(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect MR SSID usage metrics")
                self._track_error(ErrorCategory.UNKNOWN)

        except Exception:
            logger.exception(
                "Failed to collect MR-specific metrics",
                org_id=org_id,
            )
            self._track_error(ErrorCategory.UNKNOWN)

    @trace_method("collect.ms_metrics")
    async def _collect_ms_specific_metrics(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
        device_lookup: dict[str, dict[str, Any]],
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
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        try:
            # Collect STP metrics
            try:
                await self.ms_collector.collect_stp_priorities(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect STP priorities")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect switch stack metrics
            try:
                networks: list[dict[str, Any]] = []
                if self.inventory:
                    networks = await self.inventory.get_networks(org_id)
                await self.ms_stack_collector.collect_for_org(org_id, org_name, networks)
            except Exception:
                logger.exception("Failed to collect switch stack metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect power-supply module status (org-wide, single call)
            try:
                await self.ms_power_collector.collect_power_modules(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect MS power module statuses")
                self._track_error(ErrorCategory.UNKNOWN)
        except Exception:
            logger.exception(
                "Failed to collect MS-specific metrics",
                org_id=org_id,
            )
            self._track_error(ErrorCategory.UNKNOWN)

    @trace_method("collect.mx_metrics")
    async def _collect_mx_specific_metrics(
        self,
        org_id: str,
        org_name: str,
        device_lookup: dict[str, dict[str, Any]],
    ) -> None:
        """Collect MX-specific organization-wide metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        try:
            # Collect uplink statuses
            try:
                await self.mx_collector.collect_uplink_statuses(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect MX uplink statuses")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect per-uplink WAN loss & latency (org-wide, single call)
            try:
                await self.mx_uplink_health_collector.collect_uplink_loss_latency(
                    org_id, org_name, device_lookup
                )
            except Exception:
                logger.exception("Failed to collect MX uplink loss and latency")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect per-uplink WAN bandwidth usage (org-wide, single call)
            try:
                await self.mx_uplink_usage_collector.collect_uplink_usage(
                    org_id, org_name, device_lookup
                )
            except Exception:
                logger.exception("Failed to collect MX uplink usage")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect HA / warm-spare redundancy status (org-wide, paginated)
            try:
                await self.mx_ha_collector.collect_redundancy(org_id, org_name, device_lookup)
            except Exception:
                logger.exception("Failed to collect MX HA redundancy")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect VPN health metrics (point-in-time statuses)
            try:
                await self.mx_collector.vpn_collector.collect(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect MX VPN metrics")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect VPN history stats (usage volume + per-peer-pair latency)
            try:
                await self.mx_collector.vpn_collector.collect_vpn_stats(org_id, org_name)
            except Exception:
                logger.exception("Failed to collect MX VPN stats")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect security events (org-wide, single call per org)
            try:
                await self.mx_collector.firewall_collector.collect_org_security_events(
                    org_id, org_name
                )
            except Exception:
                logger.exception("Failed to collect MX security events")
                self._track_error(ErrorCategory.UNKNOWN)

            # Collect firewall rules (SLOW tier: per-network API calls)
            try:
                networks: list[dict[str, Any]] = []
                if self.inventory:
                    networks = await self.inventory.get_networks(org_id)
                # Identify unique appliance network IDs from device_lookup
                appliance_network_ids = {
                    info["network_id"]
                    for info in device_lookup.values()
                    if info.get("device_type") in {"MX", "Z3", "Z4"} and info.get("network_id")
                }
                network_map = {n["id"]: n.get("name", n["id"]) for n in networks}
                async with ManagedTaskGroup(
                    name="mx_firewall_networks",
                    max_concurrency=self.settings.api.concurrency_limit,
                ) as group:
                    for network_id in appliance_network_ids:
                        network_name = network_map.get(network_id, network_id)
                        await group.create_task(
                            self.mx_collector.firewall_collector.collect_for_network(
                                org_id, org_name, network_id, network_name
                            ),
                            name=f"fw_{network_id}",
                        )
            except Exception:
                logger.exception("Failed to collect MX firewall metrics")
                self._track_error(ErrorCategory.UNKNOWN)

        except Exception:
            logger.exception(
                "Failed to collect MX-specific metrics",
                org_id=org_id,
            )
            self._track_error(ErrorCategory.UNKNOWN)

    @trace_method("collect.mg_metrics")
    async def _collect_mg_specific_metrics(
        self,
        org_id: str,
        org_name: str,
        device_lookup: dict[str, dict[str, Any]],
    ) -> None:
        """Collect MG-specific organization-wide metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        try:
            await self.mg_collector.collect_uplink_statuses(org_id, org_name, device_lookup)
        except Exception:
            logger.exception(
                "Failed to collect MG-specific metrics",
                org_id=org_id,
            )
            self._track_error(ErrorCategory.UNKNOWN)

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
        device_type_str = model[:2] if len(model) >= 2 else "Unknown"

        # If device type based on the model isn't supported, use the product type instead
        if device_type_str not in DeviceType.__members__.values():
            # Try mapping it using the product type instead
            product_type = device.get("productType", "")
            match product_type:
                case "switch":
                    logger.debug("Overriding the device type", device_type_str=DeviceType.MS)
                    device_type_str = DeviceType.MS
                case "appliance":
                    logger.debug("Overriding the device type", device_type_str=DeviceType.MX)
                    device_type_str = DeviceType.MX
                case "wireless":
                    logger.debug("Overriding the device type", device_type_str=DeviceType.MR)
                    device_type_str = DeviceType.MR

        return device_type_str

    def _collect_common_metrics(
        self,
        device: dict[str, Any],
        org_id: str,
        org_name: str,
        *,
        availability_due: bool = True,
        availability_ttl: float | None = None,
    ) -> None:
        """Collect common device metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        availability_due : bool
            When False the device_availability endpoint group was gated out this
            cycle (#617); the availability-derived series (``meraki_device_up``,
            ``meraki_device_status_info``) are left to ride on their TTL rather
            than being re-emitted with stale/default statuses.
        availability_ttl : float | None
            Resolved per-series TTL for the device_availability group, forwarded
            to the availability-derived ``_set_metric`` calls (#617 §1f). ``None``
            ⇒ the tier-derived TTL applies.

        """
        availability_status = device.get("availability_status", DEFAULT_DEVICE_STATUS)

        # Create standard device labels (ID-only; see label_helpers.py, #534)
        labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        # meraki_device_status_info keeps `name` as its designated device-name
        # carrier (docs/stability.md) even though create_device_labels() no
        # longer emits it, so it's supplied here as an explicit extra label.
        device_name = device.get("name", device.get("serial", ""))

        # Availability-derived series are emitted only when the device_availability
        # group ran this cycle; otherwise they survive on their TTL (#617).
        if availability_due:
            # Device up/down status
            is_online = 1 if availability_status == DeviceStatus.ONLINE else 0
            self._set_metric_value(
                "_device_up",
                labels,
                is_online,
                ttl_seconds=availability_ttl,
            )

            # Remove stale status label series for this device
            # (status is a label, so transitions leave old series at 1)
            for stale_status in DeviceStatus:
                if stale_status.value != availability_status:
                    stale_labels = create_device_labels(
                        device,
                        org_id=org_id,
                        org_name=org_name,
                        name=device_name,
                        status=stale_status.value,
                    )
                    try:
                        self._device_status_info.remove(*[
                            stale_labels[ln.value]
                            for ln in [
                                LabelName.ORG_ID,
                                LabelName.NETWORK_ID,
                                LabelName.SERIAL,
                                LabelName.NAME,
                                LabelName.MODEL,
                                LabelName.DEVICE_TYPE,
                                LabelName.STATUS,
                            ]
                        ])
                    except KeyError:
                        pass  # Label combination doesn't exist

            # Device status info metric
            status_labels = create_device_labels(
                device,
                org_id=org_id,
                org_name=org_name,
                name=device_name,
                status=availability_status,
            )
            self._set_metric_value(
                "_device_status_info",
                status_labels,
                1,
                ttl_seconds=availability_ttl,
            )

        # Uptime
        if "uptimeInSeconds" in device:
            self._set_metric_value(
                "_device_uptime",
                labels,
                device["uptimeInSeconds"],
            )

    async def _fetch_networks_for_poe(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch networks for POE aggregation via the shared inventory cache.

        Going through inventory ensures the configured network filter is
        applied and that the per-org network list is fetched at most once
        per cache TTL.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of networks (filtered by the configured NetworkFilter).

        """
        if self.inventory is None:
            raise RuntimeError(
                "Inventory service not configured for DeviceCollector. "
                "POE aggregation requires inventory to apply the network filter."
            )
        with LogContext(org_id=org_id):
            return await self.inventory.get_networks(org_id)

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

                # Set network-wide POE metric (ID-only labels, #534: org_name/
                # network_name dropped, join via meraki_org_info/meraki_network_info)
                network_name = network_map.get(network_id, network_id)
                self._set_metric(
                    self.ms_collector._switch_poe_network_total,
                    {
                        "org_id": org_id,
                        "network_id": network_id,
                    },
                    total_poe,
                )

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
            self._track_error(ErrorCategory.UNKNOWN)

    @with_error_handling(
        operation="Fetch devices",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_devices(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch devices for an organization using inventory cache.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of devices or None on error.

        Raises
        ------
        RuntimeError
            If inventory service is not configured.

        """
        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for DeviceCollector. "
                "This is a programming error - collectors must be initialized with inventory service."
            )

        self._track_api_call("getOrganizationDevices")
        return await self.inventory.get_devices(org_id)

    async def _fetch_device_availabilities(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch device availabilities for an organization.

        Uses inventory cache if available (2-min TTL), otherwise falls back to direct API call.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of device availabilities or None on error.

        """
        if self.inventory:
            logger.debug("Using inventory cache for device availabilities", org_id=org_id)
            return await self.inventory.get_device_availabilities(org_id)

        # Fallback to direct API call
        result = await self._fetch_device_availabilities_direct(org_id)
        return cast(list[dict[str, Any]] | None, result)

    @log_api_call("getOrganizationDevicesAvailabilities")
    @with_error_handling(
        operation="Fetch device availabilities",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_device_availabilities_direct(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch device availabilities directly from API (fallback when inventory unavailable).

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
