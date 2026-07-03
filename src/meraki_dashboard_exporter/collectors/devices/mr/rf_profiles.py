"""MR RF profile assignment drift metrics collector (#291)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ....core.constants import MRMetricName
from ....core.domain_models import WirelessRfProfileAssignment
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName
from ....core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)


class MRRfProfilesCollector:
    """Collector for per-AP RF profile assignment (config-drift) metrics.

    Single org-wide bulk call
    (``getOrganizationWirelessRfProfilesAssignmentsByDevice``), one row per AP
    -- low cardinality, appropriate for the MEDIUM tier's SLOW-floor group
    declared for this endpoint (#617).
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR RF profiles collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance that owns the metrics.

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize RF profile assignment info metric."""
        self._rf_profile_info = self.parent._create_gauge(
            MRMetricName.MR_RF_PROFILE_INFO,
            "AP RF profile assignment (join metric: serial -> rf_profile_id/name; value 1)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.RF_PROFILE_ID,
                LabelName.RF_PROFILE_NAME,
                LabelName.IS_DEFAULT,
            ],
        )

    @log_api_call("getOrganizationWirelessRfProfilesAssignmentsByDevice")
    @with_error_handling(
        operation="Collect MR RF profile assignments",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_rf_profile_assignments(self, org_id: str, org_name: str) -> None:
        """Collect the current RF profile assignment for every AP in the org.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # Scheduler gate: skip the org-wide fetch when not due (#617).
        if not self.parent._should_run_group(EndpointGroupName.MR_RF_PROFILES):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MR_RF_PROFILES)

        with LogContext(org_id=org_id):
            raw_assignments = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice,
                org_id,
                total_pages="all",
                perPage=1000,
            )
            assignments_data = validate_response_format(
                raw_assignments,
                expected_type=list,
                operation="getOrganizationWirelessRfProfilesAssignmentsByDevice",
            )

        # Fetch succeeded — record the run so the gate can stretch (#617).
        self.parent._mark_group_ran(EndpointGroupName.MR_RF_PROFILES)

        # Resolve allowed network IDs for filter enforcement on this org-wide response.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0

        for raw_row in assignments_data:
            assignment = WirelessRfProfileAssignment.model_validate(raw_row)

            network_id = assignment.network.id if assignment.network else None
            if (
                allowed_network_ids is not None
                and network_id is not None
                and network_id not in allowed_network_ids
            ):
                skipped += 1
                continue

            serial = assignment.serial
            if not serial:
                continue

            rf_profile = assignment.rfProfile
            if rf_profile is None:
                # No assignment data to join on for this AP this cycle.
                continue

            rf_profile_id = str(rf_profile.id) if rf_profile.id is not None else ""
            rf_profile_name = rf_profile.name or ""
            is_default = bool(rf_profile.isIndoorDefault or rf_profile.isOutdoorDefault)

            labels = {
                LabelName.ORG_ID.value: org_id,
                LabelName.NETWORK_ID.value: network_id or "",
                LabelName.SERIAL.value: serial,
                LabelName.RF_PROFILE_ID.value: rf_profile_id,
                LabelName.RF_PROFILE_NAME.value: rf_profile_name,
                LabelName.IS_DEFAULT.value: "true" if is_default else "false",
            }

            self.parent._set_metric(
                self._rf_profile_info,
                labels,
                1.0,
                ttl_seconds=ttl,
            )

        if skipped:
            logger.debug(
                "MR RF profile assignments: skipped rows outside network filter",
                org_id=org_id,
                skipped_count=skipped,
            )
