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

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MX-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        self.collect_common_metrics(device)

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
