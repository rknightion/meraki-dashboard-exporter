"""MS switch power-supply (PSU) module status collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MSMetricName
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


class MSPowerCollector(SubCollectorMixin):
    """Collector for MS rackmount switch power-supply (PSU) module status.

    Collects per-slot power-supply module status at the organization level
    using the getOrganizationDevicesPowerModulesStatusesByDevice endpoint,
    filtered to switch product types.

    Update tier: called once per org from the DeviceCollector MEDIUM (300s)
    loop; hardware PSU status is slow-changing so MEDIUM is ample. It is a
    single org-wide call, so it is cheap relative to the rate-limit budget.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MS power module collector.

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
        """Initialize PSU-related Prometheus gauge metrics."""
        self._ms_power_supply_status = self.parent._create_gauge(
            MSMetricName.MS_POWER_SUPPLY_STATUS,
            "MS/rackmount power-supply module status (1 = reported this cycle)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.SLOT,
                LabelName.PSU_SERIAL,
                LabelName.PSU_MODEL,
                LabelName.STATUS,
            ],
        )

    @log_api_call("getOrganizationDevicesPowerModulesStatusesByDevice")
    @with_error_handling(
        operation="Collect MS power module statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_power_modules(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect PSU module statuses for all MS switches in an organization.

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
            self.api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice,
            org_id,
            productTypes=["switch"],
            total_pages="all",
        )

        rows = validate_response_format(
            resp,
            expected_type=list,
            operation="getOrganizationDevicesPowerModulesStatusesByDevice",
        )

        if not rows:
            return

        # NB: do NOT clear the gauge's label series here. collect_power_modules runs
        # once per org (concurrently across orgs, sharing one gauge instance), so a
        # global _metrics.clear() would wipe every other org's series mid-cycle. Stale
        # label series (status transitions) are removed by the metric expiration
        # manager via parent._set_metric tracking instead.

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        emitted = 0

        for row in rows:
            serial = row.get("serial", "")
            device_info = device_lookup.get(serial, {})
            network = row.get("network") or {}
            network_id = network.get("id", device_info.get("network_id", ""))

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            name = row.get("name", device_info.get("name", serial))
            model = row.get("model", device_info.get("model", ""))

            device_data = {
                "serial": serial,
                "name": name,
                "model": model,
                "networkId": network_id,
                "networkName": device_info.get("network_name", network_id),
            }

            for slot in row.get("slots") or []:
                slot_number = str(slot.get("number", ""))
                psu_serial = slot.get("serial") or ""
                psu_model = slot.get("model") or ""
                status = slot.get("status", "")

                labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    slot=slot_number,
                    psu_serial=psu_serial,
                    psu_model=psu_model,
                    status=status,
                )

                self.parent._set_metric(
                    self._ms_power_supply_status,
                    labels,
                    1,
                    MSMetricName.MS_POWER_SUPPLY_STATUS.value,
                )
                emitted += 1

        logger.debug(
            "Collected MS power module statuses",
            org_id=org_id,
            device_count=len(rows),
            emitted_count=emitted,
            skipped_count=skipped,
        )
