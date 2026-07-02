"""MX security appliance collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MXMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
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

                self.parent._set_metric(self._mx_uplink_info, labels, 1)

        logger.debug(
            "Collected MX uplink statuses",
            org_id=org_id,
            appliance_count=len(uplink_statuses),
            skipped_count=skipped,
        )
