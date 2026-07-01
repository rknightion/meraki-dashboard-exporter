"""MX high-availability (warm spare) redundancy collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName, create_labels
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MXHACollector(SubCollectorMixin):
    """Collector for MX high-availability (warm spare) redundancy metrics.

    Collects per-network HA enablement/mode and per-device HA role
    (designation priority) at the organization level using the
    getOrganizationApplianceDevicesRedundancyByNetwork endpoint.

    Update tier: MEDIUM (300s). This is an org-wide single call per
    organization, and HA configuration/role changes infrequently, so a
    5-minute cadence is appropriate.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MX HA collector.

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
        """Initialize HA Prometheus gauge metrics."""
        self._mx_ha_enabled = self.parent._create_gauge(
            MXMetricName.MX_HA_ENABLED,
            "Whether MX warm spare high availability is enabled for a network (1 = enabled)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )
        self._mx_ha_mode = self.parent._create_gauge(
            MXMetricName.MX_HA_MODE,
            "MX warm spare high availability mode info (1 = present)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.MODE,
            ],
        )
        self._mx_ha_role = self.parent._create_gauge(
            MXMetricName.MX_HA_ROLE,
            "MX warm spare designation priority for a device",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
            ],
        )

    @log_api_call("getOrganizationApplianceDevicesRedundancyByNetwork")
    @with_error_handling(
        operation="Collect MX HA redundancy",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_redundancy(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect HA redundancy status/mode/role for all MX networks in an organization.

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
            self.api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork,
            org_id,
            total_pages="all",
        )

        rows = validate_response_format(
            resp,
            expected_type=list,
            operation="getOrganizationApplianceDevicesRedundancyByNetwork",
        )

        if not rows:
            return

        # mode/serial are labels that can churn (mode changes, warm spare
        # pairs are re-designated) so clear prior series before re-setting.
        self._mx_ha_mode._metrics.clear()
        self._mx_ha_role._metrics.clear()

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

            network_name = row.get("name", network_id)
            network_labels = create_network_labels(
                {"id": network_id, "name": network_name},
                org_id=org_id,
                org_name=org_name,
            )

            self.parent._set_metric(
                self._mx_ha_enabled,
                network_labels,
                1.0 if row.get("enabled") else 0.0,
                MXMetricName.MX_HA_ENABLED.value,
            )
            emitted += 1

            mode = row.get("mode", "")
            mode_labels = create_labels(
                org_id=org_id,
                org_name=org_name,
                network_id=network_id,
                network_name=network_name,
                mode=mode,
            )
            self.parent._set_metric(
                self._mx_ha_mode,
                mode_labels,
                1,
                MXMetricName.MX_HA_MODE.value,
            )
            emitted += 1

            for designation in row.get("designations", []):
                serial = designation.get("serial", "")
                priority = designation.get("priority")
                if priority is None:
                    continue

                role_labels = create_labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    serial=serial,
                )
                self.parent._set_metric(
                    self._mx_ha_role,
                    role_labels,
                    float(priority),
                    MXMetricName.MX_HA_ROLE.value,
                )
                emitted += 1

        logger.debug(
            "Collected MX HA redundancy",
            org_id=org_id,
            row_count=len(rows),
            skipped_count=skipped,
            emitted_count=emitted,
        )
