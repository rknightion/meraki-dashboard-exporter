"""MG cellular gateway collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MGMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    from ..device import DeviceCollector

logger = get_logger(__name__)


def _parse_float(value: Any) -> float | None:
    """Parse a signal-strength value (may be a string, empty, or non-numeric) to a float.

    Parameters
    ----------
    value : Any
        Raw value from the API (typically a string like "-90", "", or None).

    Returns
    -------
    float | None
        The parsed float, or None if the value is missing/empty/non-numeric.

    """
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


class MGCollector(BaseDeviceCollector):
    """Collector for MG cellular gateway metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MG collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)

        self._mg_uplink_status_info = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_STATUS_INFO,
            "MG cellular gateway uplink status info (1 = present)",
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
                LabelName.PROVIDER,
                LabelName.CONNECTION_TYPE,
                LabelName.SIGNAL_TYPE,
                LabelName.ROAMING_STATUS,
                LabelName.APN,
                LabelName.IP,
            ],
        )

        signal_labelnames = [
            LabelName.ORG_ID,
            LabelName.ORG_NAME,
            LabelName.NETWORK_ID,
            LabelName.NETWORK_NAME,
            LabelName.SERIAL,
            LabelName.NAME,
            LabelName.MODEL,
            LabelName.DEVICE_TYPE,
            LabelName.INTERFACE,
        ]

        self._mg_uplink_signal_rsrp = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_SIGNAL_RSRP_DBM,
            "MG cellular gateway uplink RSRP signal strength in dBm",
            labelnames=signal_labelnames,
        )

        self._mg_uplink_signal_rsrq = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_SIGNAL_RSRQ_DB,
            "MG cellular gateway uplink RSRQ signal quality in dB",
            labelnames=signal_labelnames,
        )

        self._mg_uplink_roaming = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_ROAMING,
            "MG cellular gateway uplink roaming status (1 = roaming, 0 = home)",
            labelnames=signal_labelnames,
        )

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MG-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Cellular uplink status/signal metrics are collected org-wide via
        collect_uplink_statuses(), not per-device, so this remains a no-op.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        # Uplink statuses are collected separately via collect_uplink_statuses()

    @log_api_call("getOrganizationCellularGatewayUplinkStatuses")
    @with_error_handling(
        operation="Collect MG uplink statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_uplink_statuses(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect cellular uplink statuses for all MG gateways in an organization.

        Update tier: MEDIUM (300s) — cellular uplink status/signal does not change
        second-to-second, and a single org-wide call covers all MG devices.

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
            self.api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses,
            org_id,
            total_pages="all",
        )

        uplink_statuses = validate_response_format(
            uplink_statuses,
            expected_type=list,
            operation="getOrganizationCellularGatewayUplinkStatuses",
        )

        if not uplink_statuses:
            return

        # Clear previous label series to avoid stale status/roaming values
        # (status, provider, etc. are labels, so transitions leave old series behind)
        self._mg_uplink_status_info._metrics.clear()
        self._mg_uplink_roaming._metrics.clear()

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        uplink_count = 0

        for row in uplink_statuses:
            serial = row.get("serial", "")
            device_info = device_lookup.get(serial, {})
            network_id = row.get("networkId", device_info.get("network_id", ""))

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            device_data = {
                "serial": serial,
                "name": device_info.get("name", serial),
                "model": row.get("model", device_info.get("model", "")),
                "networkId": network_id,
                "networkName": device_info.get("network_name", network_id),
            }

            for uplink in row.get("uplinks", []):
                uplink_count += 1
                interface = uplink.get("interface", "")
                status = uplink.get("status", "not connected")
                roaming = uplink.get("roaming") or {}

                info_labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                    status=status,
                    provider=uplink.get("provider", ""),
                    connection_type=uplink.get("connectionType", ""),
                    signal_type=uplink.get("signalType", ""),
                    roaming_status=roaming.get("status", ""),
                    apn=uplink.get("apn", ""),
                    ip=uplink.get("ip", ""),
                )
                self.parent._set_metric(
                    self._mg_uplink_status_info,
                    info_labels,
                    1,
                    MGMetricName.MG_UPLINK_STATUS_INFO.value,
                )

                signal_labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                )

                signal = uplink.get("signalStat") or {}
                rsrp = _parse_float(signal.get("rsrp"))
                if rsrp is not None:
                    self.parent._set_metric(
                        self._mg_uplink_signal_rsrp,
                        signal_labels,
                        rsrp,
                        MGMetricName.MG_UPLINK_SIGNAL_RSRP_DBM.value,
                    )

                rsrq = _parse_float(signal.get("rsrq"))
                if rsrq is not None:
                    self.parent._set_metric(
                        self._mg_uplink_signal_rsrq,
                        signal_labels,
                        rsrq,
                        MGMetricName.MG_UPLINK_SIGNAL_RSRQ_DB.value,
                    )

                if "roaming" in uplink:
                    roaming_value = 1.0 if roaming.get("status") == "roaming" else 0.0
                    self.parent._set_metric(
                        self._mg_uplink_roaming,
                        signal_labels,
                        roaming_value,
                        MGMetricName.MG_UPLINK_ROAMING.value,
                    )

        logger.debug(
            "Collected MG uplink statuses",
            org_id=org_id,
            gateway_count=len(uplink_statuses),
            uplink_count=uplink_count,
            skipped_count=skipped,
        )
