"""MG cellular gateway collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MGMetricName
from ...core.domain_models import CellularGatewayUplinkStatus
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ...core.scheduler import EndpointGroupName
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
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
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
            LabelName.NETWORK_ID,
            LabelName.SERIAL,
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
        # #617 gate: the mg_uplink_status group is declared on DeviceCollector;
        # skip the org-wide fetch when it is not due this heartbeat.
        if not self.parent._should_run_group(EndpointGroupName.MG_UPLINK_STATUS):
            return

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

        # Successful fetch: advance the group's last-ran clock.
        self.parent._mark_group_ran(EndpointGroupName.MG_UPLINK_STATUS)

        if not uplink_statuses:
            return

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MG_UPLINK_STATUS)

        # NB: do NOT clear the gauge's label series here. This runs once per org
        # (concurrently across orgs, sharing one gauge instance), so a global
        # _metrics.clear() would wipe every other org's series mid-cycle. Stale
        # label series (status/provider transitions) are removed by the metric
        # expiration manager via parent._set_metric tracking instead.

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        uplink_count = 0

        for row in uplink_statuses:
            gateway = CellularGatewayUplinkStatus.model_validate(row)
            serial = gateway.serial
            device_info = device_lookup.get(serial, {})
            network_id = (
                gateway.networkId
                if gateway.networkId is not None
                else device_info.get("network_id", "")
            )

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            gateway_model = (
                gateway.model if gateway.model is not None else device_info.get("model", "")
            )
            device_data = {
                "serial": serial,
                "name": device_info.get("name", serial),
                "model": gateway_model,
                "networkId": network_id,
                "networkName": device_info.get("network_name", network_id),
            }

            for uplink in gateway.uplinks:
                uplink_count += 1
                interface = uplink.interface
                status = uplink.status
                roaming = uplink.roaming

                info_labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                    status=status,
                    provider=uplink.provider or "",
                    connection_type=uplink.connectionType or "",
                    signal_type=uplink.signalType or "",
                    roaming_status=(roaming.status or "") if roaming is not None else "",
                    apn=uplink.apn or "",
                    ip=uplink.ip or "",
                )
                self.parent._set_metric(
                    self._mg_uplink_status_info,
                    info_labels,
                    1,
                    MGMetricName.MG_UPLINK_STATUS_INFO.value,
                    ttl_seconds=ttl_seconds,
                )

                signal_labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                )

                signal = uplink.signalStat
                rsrp = _parse_float(signal.rsrp) if signal is not None else None
                if rsrp is not None:
                    self.parent._set_metric(
                        self._mg_uplink_signal_rsrp,
                        signal_labels,
                        rsrp,
                        MGMetricName.MG_UPLINK_SIGNAL_RSRP_DBM.value,
                        ttl_seconds=ttl_seconds,
                    )

                rsrq = _parse_float(signal.rsrq) if signal is not None else None
                if rsrq is not None:
                    self.parent._set_metric(
                        self._mg_uplink_signal_rsrq,
                        signal_labels,
                        rsrq,
                        MGMetricName.MG_UPLINK_SIGNAL_RSRQ_DB.value,
                        ttl_seconds=ttl_seconds,
                    )

                if "roaming" in uplink.model_fields_set:
                    roaming_value = (
                        1.0 if (roaming is not None and roaming.status == "roaming") else 0.0
                    )
                    self.parent._set_metric(
                        self._mg_uplink_roaming,
                        signal_labels,
                        roaming_value,
                        MGMetricName.MG_UPLINK_ROAMING.value,
                        ttl_seconds=ttl_seconds,
                    )

        logger.debug(
            "Collected MG uplink statuses",
            org_id=org_id,
            gateway_count=len(uplink_statuses),
            uplink_count=uplink_count,
            skipped_count=skipped,
        )
