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
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.INTERFACE,
                LabelName.STATUS,
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

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        # MX per-device metrics can be added here
        # Uplink statuses are collected separately via collect_uplink_statuses()

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

        # Clear previous label series to avoid stale status values
        # (status is a label, so status transitions leave old series at 1)
        self._mx_uplink_info._metrics.clear()

        for appliance in uplink_statuses:
            serial = appliance.get("serial", "")
            device_info = device_lookup.get(serial, {})
            network_id = appliance.get("networkId", device_info.get("network_id", ""))

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
        )
