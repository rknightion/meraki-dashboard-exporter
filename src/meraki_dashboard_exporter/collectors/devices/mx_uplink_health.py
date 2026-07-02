"""MX per-uplink WAN loss/latency health collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
from ...core.domain_models import DeviceUplinkLossLatency, UplinkLossLatencyTimeSeriesPoint
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MXUplinkHealthCollector(SubCollectorMixin):
    """Collector for MX per-uplink WAN loss/latency health metrics.

    Collects the latest loss/latency sample per (device, uplink) at the
    organization level using the getOrganizationDevicesUplinksLossAndLatency
    endpoint.

    Update tier: MEDIUM (300s). This is an org-wide single call, and the
    underlying WAN-quality data is sampled roughly every minute server-side,
    so a 5-minute collection freshness is acceptable.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MX uplink health collector.

        Parameters
        ----------
        parent : Any
            Parent collector instance (MXCollector or DeviceCollector) that
            exposes ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize uplink loss/latency Prometheus gauge metrics."""
        labelnames = [
            LabelName.ORG_ID,
            LabelName.NETWORK_ID,
            LabelName.SERIAL,
            LabelName.MODEL,
            LabelName.DEVICE_TYPE,
            LabelName.INTERFACE,
        ]
        self._mx_uplink_loss_percent = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_LOSS_PERCENT,
            "MX per-uplink WAN loss percent (latest sample)",
            labelnames=labelnames,
        )
        self._mx_uplink_latency_seconds = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_LATENCY_SECONDS,
            "MX per-uplink WAN latency in seconds (latest sample)",
            labelnames=labelnames,
        )

    @log_api_call("getOrganizationDevicesUplinksLossAndLatency")
    @with_error_handling(
        operation="Collect MX uplink loss and latency",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_uplink_loss_latency(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect per-uplink loss/latency metrics for all MX appliances in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        resp = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevicesUplinksLossAndLatency,
            org_id,
            timespan=300,
        )

        rows = validate_response_format(
            resp,
            expected_type=list,
            operation="getOrganizationDevicesUplinksLossAndLatency",
        )

        if not rows:
            return

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        emitted = 0

        # NOTE: This endpoint returns one row per (device, uplink, destination-ip);
        # multiple destination IPs can produce multiple rows for the same uplink.
        # We label only by interface (not destination ip, which is unbounded), so
        # if multiple IP rows share an uplink, last-write-wins is acceptable here.
        for row in rows:
            entry = DeviceUplinkLossLatency.model_validate(row)
            network_id = entry.networkId or ""

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            serial = entry.serial or ""
            device_info = device_lookup.get(serial, {})
            network_id = network_id or device_info.get("network_id", "")

            device_data = {
                "serial": serial,
                "name": device_info.get("name", serial),
                "model": device_info.get("model", ""),
                "networkId": network_id,
                "networkName": device_info.get("network_name", network_id),
            }

            interface = entry.uplink or ""
            time_series = entry.timeSeries

            loss_value = self._latest_non_null(time_series, "lossPercent")
            latency_value = self._latest_non_null(time_series, "latencyMs")

            if loss_value is None and latency_value is None:
                continue

            labels = create_device_labels(
                device_data,
                org_id=org_id,
                org_name=org_name,
                interface=interface,
            )

            if loss_value is not None:
                self.parent._set_metric(
                    self._mx_uplink_loss_percent,
                    labels,
                    float(loss_value),
                    MXMetricName.MX_UPLINK_LOSS_PERCENT.value,
                )
                emitted += 1

            if latency_value is not None:
                self.parent._set_metric(
                    self._mx_uplink_latency_seconds,
                    labels,
                    float(latency_value) / 1000,
                    MXMetricName.MX_UPLINK_LATENCY_SECONDS.value,
                )
                emitted += 1

        logger.debug(
            "Collected MX uplink loss/latency",
            org_id=org_id,
            row_count=len(rows),
            skipped_count=skipped,
            emitted_count=emitted,
        )

    @staticmethod
    def _latest_non_null(
        time_series: list[UplinkLossLatencyTimeSeriesPoint], field: str
    ) -> float | None:
        """Return the value of the latest non-null sample for ``field`` in a time series.

        Parameters
        ----------
        time_series : list[UplinkLossLatencyTimeSeriesPoint]
            List of validated time series points, each potentially having ``field`` set.
        field : str
            Attribute name to look up (e.g. ``"lossPercent"`` or ``"latencyMs"``).

        Returns
        -------
        float | None
            The latest non-null value, or None if no sample has a non-null value.

        """
        for point in reversed(time_series):
            value = getattr(point, field, None)
            if value is not None:
                return float(value)
        return None
