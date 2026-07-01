"""MX per-uplink WAN usage collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
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


class MXUplinkUsageCollector(SubCollectorMixin):
    """Collector for MX per-uplink WAN usage (sent/received bytes) metrics.

    Collects the last-5-minute windowed sent/received byte totals per
    (device, uplink) at the organization level using the
    getOrganizationApplianceUplinksUsageByNetwork endpoint.

    Update tier: MEDIUM (300s). This is an org-wide single call per
    organization, and the underlying usage figures are a rolling 5-minute
    window, so a 5-minute collection cadence matches the data's own freshness.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MX uplink usage collector.

        Parameters
        ----------
        parent : Any
            Parent collector instance (DeviceCollector) that exposes
            ``_create_gauge``, ``_set_metric``, ``api``, ``settings``, and
            ``inventory``.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize uplink usage Prometheus gauge metrics."""
        labelnames = [
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
        self._mx_uplink_sent_bytes = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_SENT_BYTES,
            "MX per-uplink WAN bytes sent (last 5 minutes)",
            labelnames=labelnames,
        )
        self._mx_uplink_recv_bytes = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_RECV_BYTES,
            "MX per-uplink WAN bytes received (last 5 minutes)",
            labelnames=labelnames,
        )

    @log_api_call("getOrganizationApplianceUplinksUsageByNetwork")
    @with_error_handling(
        operation="Collect MX uplink usage",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_uplink_usage(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect per-uplink sent/received byte usage for all MX appliances in an organization.

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
            self.api.appliance.getOrganizationApplianceUplinksUsageByNetwork,
            org_id,
            timespan=300,
        )

        rows = validate_response_format(
            resp,
            expected_type=list,
            operation="getOrganizationApplianceUplinksUsageByNetwork",
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

        for row in rows:
            network_id = row.get("networkId", "")

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            for uplink in row.get("byUplink", []):
                serial = uplink.get("serial", "")
                interface = uplink.get("interface", "")
                sent = uplink.get("sent")
                received = uplink.get("received")

                if sent is None and received is None:
                    continue

                device_info = device_lookup.get(serial, {})
                device_data = {
                    "serial": serial,
                    "name": device_info.get("name", serial),
                    "model": device_info.get("model", ""),
                    "networkId": network_id,
                    "networkName": device_info.get("network_name", row.get("name", network_id)),
                }

                labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                )

                if sent is not None:
                    self.parent._set_metric(
                        self._mx_uplink_sent_bytes,
                        labels,
                        float(sent),
                        MXMetricName.MX_UPLINK_SENT_BYTES.value,
                    )
                    emitted += 1

                if received is not None:
                    self.parent._set_metric(
                        self._mx_uplink_recv_bytes,
                        labels,
                        float(received),
                        MXMetricName.MX_UPLINK_RECV_BYTES.value,
                    )
                    emitted += 1

        logger.debug(
            "Collected MX uplink usage",
            org_id=org_id,
            row_count=len(rows),
            skipped_count=skipped,
            emitted_count=emitted,
        )
