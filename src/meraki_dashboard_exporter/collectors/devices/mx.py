"""MX security appliance collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ...core.constants import MXMetricName
from ...core.domain_models import ApplianceDhcpSubnet
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ...core.scheduler import EndpointGroupName
from .base import BaseDeviceCollector
from .mx_firewall import MXFirewallCollector
from .mx_vpn import MXVpnCollector

if TYPE_CHECKING:
    from ..device import DeviceCollector

logger = get_logger(__name__)


class MXCollector(BaseDeviceCollector):
    """Collector for MX security appliance metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MX collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)
        self.vpn_collector = MXVpnCollector(self)
        self.firewall_collector = MXFirewallCollector(self)

        # Per-serial throttle for the NEW mx_performance gate (#552/#617). The
        # per-device getDeviceAppliancePerformance call fans out across every
        # physical MX inside one MEDIUM-tier cycle, so a group-global run gate
        # (single last_ran) would collect only the first appliance and skip the
        # rest for the whole cycle. Instead each serial keeps its own timestamp
        # and reads the interval from the mx_performance endpoint group
        # (floor 900s), mirroring the per-serial MS gates.
        self._last_performance_collection: dict[str, float] = {}

        # Per-serial throttle for the NEW mx_dhcp_subnets gate (#286/#617), mirroring
        # _last_performance_collection above for the same reason (a per-physical-MX
        # fan-out within one MEDIUM-tier cycle needs per-serial state, not a single
        # group-global run gate).
        self._last_dhcp_subnets_collection: dict[str, float] = {}

        self._mx_uplink_info = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_INFO,
            "MX appliance uplink status info (1 = present)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.INTERFACE,
                LabelName.STATUS,
            ],
        )

        self._mx_performance_score = self.parent._create_gauge(
            MXMetricName.MX_PERFORMANCE_SCORE,
            "MX appliance performance score (0-100)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # Phase 4 (#286): per-MX-device DHCP subnet utilization.
        dhcp_subnet_labelnames = [
            LabelName.ORG_ID,
            LabelName.NETWORK_ID,
            LabelName.SERIAL,
            LabelName.MODEL,
            LabelName.DEVICE_TYPE,
            LabelName.SUBNET,
            LabelName.VLAN,
        ]
        self._dhcp_subnet_used_ips = self.parent._create_gauge(
            MXMetricName.MX_DHCP_SUBNET_USED_IPS,
            "Number of IPs in use within a DHCP-served subnet on this MX",
            labelnames=dhcp_subnet_labelnames,
        )
        self._dhcp_subnet_free_ips = self.parent._create_gauge(
            MXMetricName.MX_DHCP_SUBNET_FREE_IPS,
            "Number of free IPs within a DHCP-served subnet on this MX",
            labelnames=dhcp_subnet_labelnames,
        )

    def _create_gauge(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate gauge creation to the parent DeviceCollector.

        Sub-collectors (e.g. MXVpnCollector) call ``self.parent._create_gauge``,
        where ``self.parent`` is this MXCollector.  MXCollector itself does not
        own a registry, so we forward the call to our own parent (DeviceCollector).
        """
        return self.parent._create_gauge(*args, **kwargs)

    def _set_metric(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate metric setting to the parent DeviceCollector."""
        return self.parent._set_metric(*args, **kwargs)

    # -- scheduler gate delegation (#617) ----------------------------------
    # MXVpnCollector / MXFirewallCollector take *this* MXCollector as their
    # ``parent``, but the scheduler gate helpers live on the top-level
    # DeviceCollector.  Forward them the same way _create_gauge/_set_metric are
    # forwarded so sub-collectors can call ``self.parent._should_run_group`` etc.

    def _should_run_group(self, group: EndpointGroupName) -> bool:
        """Delegate the run gate to the parent DeviceCollector."""
        return bool(self.parent._should_run_group(group))

    def _mark_group_ran(self, group: EndpointGroupName) -> None:
        """Delegate the run-marker to the parent DeviceCollector."""
        self.parent._mark_group_ran(group)

    def _group_interval(self, group: EndpointGroupName) -> float:
        """Delegate the solved-interval lookup to the parent DeviceCollector."""
        return float(self.parent._group_interval(group))

    def _group_ttl_seconds(self, group: EndpointGroupName) -> float | None:
        """Delegate the per-series TTL lookup to the parent DeviceCollector."""
        ttl = self.parent._group_ttl_seconds(group)
        return None if ttl is None else float(ttl)

    def _should_collect_performance(self, serial: str) -> bool:
        """Return whether enough time has elapsed to (re)collect this MX's perf score.

        Per-serial throttle for the mx_performance endpoint group (#552/#617),
        reading the interval from the scheduler-solved group interval (floor
        900s) rather than a raw setting. A non-positive interval disables gating.
        """
        interval = self._group_interval(EndpointGroupName.MX_PERFORMANCE)
        if interval <= 0:
            return True
        last = self._last_performance_collection.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_performance_collected(self, serial: str) -> None:
        """Record that the perf score was just collected for this serial."""
        self._last_performance_collection[serial] = time.time()

    def _should_collect_dhcp_subnets(self, serial: str) -> bool:
        """Return whether enough time has elapsed to (re)collect this MX's DHCP subnets.

        Per-serial throttle for the mx_dhcp_subnets endpoint group (#286/#617),
        mirroring ``_should_collect_performance`` above.
        """
        interval = self._group_interval(EndpointGroupName.MX_DHCP_SUBNETS)
        if interval <= 0:
            return True
        last = self._last_dhcp_subnets_collection.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_dhcp_subnets_collected(self, serial: str) -> None:
        """Record that DHCP subnets were just collected for this serial."""
        self._last_dhcp_subnets_collection[serial] = time.time()

    @property
    def inventory(self) -> Any:
        """Expose the parent DeviceCollector's inventory cache to sub-collectors."""
        return self.parent.inventory

    def update_api(self, api: Any) -> None:
        """Update the API client and propagate to sub-collectors.

        Parameters
        ----------
        api : Any
            New DashboardAPI instance.

        """
        super().update_api(api)
        self.vpn_collector.update_api(api)
        self.firewall_collector.update_api(api)

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MX-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Runs at the parent DeviceCollector's MEDIUM (300s) per-device cadence.
        The roadmap issue for this metric suggested a SLOW tier, but there is
        no separate SLOW per-device pipeline for MX appliances -- collect() is
        only ever invoked from the existing bounded MEDIUM-tier per-device
        fan-out, so MEDIUM is what this metric actually gets. That cadence is
        acceptable for a performance score.

        Uplink statuses are collected separately via collect_uplink_statuses().

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        if self._is_physical_mx_hardware(device):
            await self._collect_performance_score(device)
            await self._collect_dhcp_subnets(device)

    @staticmethod
    def _is_physical_mx_hardware(device: dict[str, Any]) -> bool:
        """Return True only for physical MX hardware (not Z-series or vMX).

        ``getDeviceAppliancePerformance`` (the org's per-device performance score)
        is documented by Meraki as unavailable on Z-series teleworker gateways
        (Z3/Z3C/Z4) and on virtual MX (vMX) -- calling it for those anyway burns
        API budget and logs an error every collection cycle. Real MX hardware
        models are named e.g. "MX68"/"MX250"; Z-series models are named "Z3"/
        "Z4"/etc; vMX models are named "vMX100"/"vMX-S"/"vMX-M"/"vMX-L" (which do
        NOT start with "MX", so the same prefix check excludes them too).

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        Returns
        -------
        bool
            True if the device's model indicates physical MX hardware.

        """
        model = str(device.get("model", ""))
        return model.upper().startswith("MX")

    @log_api_call("getDeviceAppliancePerformance")
    @with_error_handling(
        operation="Collect MX performance score",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_performance_score(self, device: dict[str, Any]) -> None:
        """Collect the appliance performance score for a single MX device.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        serial = device.get("serial", "")

        # mx_performance gate (#552/#617): throttle the per-physical-MX perf call
        # to the mx_performance group's interval (floor 900s). Keyed per serial so
        # every appliance is collected once per interval within the MEDIUM-tier
        # fan-out rather than only the first one.
        if not self._should_collect_performance(serial):
            return

        # Pass an explicit timespan so the score reflects a fixed, deterministic
        # window rather than drifting with whatever the API's undocumented
        # default happens to be. 1800s (30 minutes) is the minimum accepted
        # value (and also the SDK's documented default) -- it's the freshest
        # window available and matches this collector's per-cycle granularity,
        # so re-running collect() doesn't average over an ever-shifting range.
        resp = await asyncio.to_thread(
            self.api.appliance.getDeviceAppliancePerformance,
            serial,
            timespan=1800,
        )

        resp = validate_response_format(
            resp,
            expected_type=dict,
            operation="getDeviceAppliancePerformance",
        )

        # Mark after a successful fetch (before emit) so a failed call retries on
        # the next cycle rather than being throttled out.
        self._mark_performance_collected(serial)

        perf = resp.get("perfScore")
        if perf is not None:
            labels = create_device_labels(
                device,
                org_id=device.get("orgId", ""),
                org_name=device.get("orgName", device.get("orgId", "")),
            )
            self.parent._set_metric(
                self._mx_performance_score,
                labels,
                float(perf),
                MXMetricName.MX_PERFORMANCE_SCORE.value,
                ttl_seconds=self._group_ttl_seconds(EndpointGroupName.MX_PERFORMANCE),
            )

    @log_api_call("getDeviceApplianceDhcpSubnets")
    @with_error_handling(
        operation="Collect MX DHCP subnet utilization",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_dhcp_subnets(self, device: dict[str, Any]) -> None:
        """Collect per-subnet DHCP IP utilization for a single MX device (#286).

        ``getDeviceApplianceDhcpSubnets`` returns an empty list when the
        device serves no DHCP-enabled VLANs -- that is a normal, expected
        response and results in no metrics for this device, not an error.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        serial = device.get("serial", "")

        # mx_dhcp_subnets gate (#286/#617): throttle the per-physical-MX DHCP
        # subnets call to the mx_dhcp_subnets group's interval (floor 900s).
        if not self._should_collect_dhcp_subnets(serial):
            return

        resp = await asyncio.to_thread(
            self.api.appliance.getDeviceApplianceDhcpSubnets,
            serial,
        )

        resp = validate_response_format(
            resp,
            expected_type=list,
            operation="getDeviceApplianceDhcpSubnets",
        )

        # Mark after a successful fetch (before emit) so a failed call retries on
        # the next cycle rather than being throttled out.
        self._mark_dhcp_subnets_collected(serial)

        subnets = [ApplianceDhcpSubnet.model_validate(s) for s in resp]
        ttl_seconds = self._group_ttl_seconds(EndpointGroupName.MX_DHCP_SUBNETS)

        for subnet in subnets:
            labels = create_device_labels(
                device,
                org_id=device.get("orgId", ""),
                org_name=device.get("orgName", device.get("orgId", "")),
                subnet=subnet.subnet or "",
                vlan=str(subnet.vlanId) if subnet.vlanId is not None else "",
            )
            if subnet.usedCount is not None:
                self.parent._set_metric(
                    self._dhcp_subnet_used_ips,
                    labels,
                    float(subnet.usedCount),
                    ttl_seconds=ttl_seconds,
                )
            if subnet.freeCount is not None:
                self.parent._set_metric(
                    self._dhcp_subnet_free_ips,
                    labels,
                    float(subnet.freeCount),
                    ttl_seconds=ttl_seconds,
                )

    @log_api_call("getOrganizationApplianceUplinkStatuses")
    @with_error_handling(
        operation="Collect MX uplink statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_uplink_statuses(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect uplink statuses for all MX appliances in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        # mx_uplink_status gate (#617): single org-wide call per cycle.
        if not self.parent._should_run_group(EndpointGroupName.MX_UPLINK_STATUS):
            return

        uplink_statuses = await asyncio.to_thread(
            self.api.appliance.getOrganizationApplianceUplinkStatuses,
            org_id,
            total_pages="all",
        )

        uplink_statuses = validate_response_format(
            uplink_statuses,
            expected_type=list,
            operation="getOrganizationApplianceUplinkStatuses",
        )

        if not uplink_statuses:
            return

        # NB: do NOT clear the gauge's label series here. This runs once per org
        # (concurrently across orgs, sharing one gauge instance), so a global
        # _metrics.clear() would wipe every other org's series mid-cycle. Stale
        # label series (status transitions) are removed by the metric expiration
        # manager via parent._set_metric tracking instead.

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0

        for appliance in uplink_statuses:
            serial = appliance.get("serial", "")
            device_info = device_lookup.get(serial, {})
            network_id = appliance.get("networkId", device_info.get("network_id", ""))

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            device_data = {
                "serial": serial,
                "name": device_info.get("name", serial),
                "model": appliance.get("model", device_info.get("model", "")),
                "networkId": network_id,
                "networkName": device_info.get("network_name", network_id),
            }

            uplinks = appliance.get("uplinks", [])
            for uplink in uplinks:
                interface = uplink.get("interface", "")
                status = uplink.get("status", "not connected")

                labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                    status=status,
                )

                self.parent._set_metric(
                    self._mx_uplink_info,
                    labels,
                    1,
                    ttl_seconds=self.parent._group_ttl_seconds(EndpointGroupName.MX_UPLINK_STATUS),
                )

        # Mark after a successful org-wide fetch (failures retry next cycle).
        self.parent._mark_group_ran(EndpointGroupName.MX_UPLINK_STATUS)

        logger.debug(
            "Collected MX uplink statuses",
            org_id=org_id,
            appliance_count=len(uplink_statuses),
            skipped_count=skipped,
        )
