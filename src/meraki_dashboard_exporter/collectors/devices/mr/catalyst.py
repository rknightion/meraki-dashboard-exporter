"""MR (Catalyst CW*) wireless-controller association metrics collector (#326)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ....core.constants import MRMetricName
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName
from ....core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)


class _ControllerRef(BaseModel):
    """The wireless controller an AP is associated with."""

    model_config = ConfigDict(extra="allow")

    serial: str | None = None


class _NetworkRef(BaseModel):
    """Network reference on a wireless-controller row."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None


class _WirelessControllerRow(BaseModel):
    """One Catalyst AP → wireless-controller association row.

    Lenient (``extra="allow"``) — this is a spec-only family until a homelab
    with CW* hardware verifies the shape. The ``tags``/``details`` arrays are
    deliberately NOT modelled here because they are never emitted.
    """

    model_config = ConfigDict(extra="allow")

    serial: str | None = None
    model: str | None = None
    network: _NetworkRef | None = None
    controller: _ControllerRef | None = None
    joinedAt: str | None = None
    mode: str | None = None
    countryCode: str | None = None


class MRCatalystCollector:
    """Collector for Catalyst (CW*) AP wireless-controller association info.

    Single org-wide bulk call
    (``getOrganizationWirelessDevicesWirelessControllersByDevice``), one row per
    Catalyst AP — cardinality bounded by the physical Catalyst AP count. Emits an
    info/join series (controller serial, mode, country code) plus the join
    timestamp. Empty for non-Catalyst orgs, so the scheduler auto-disables the
    group (``catalyst_ap_count == 0``). Gated on ``MR_WIRELESS_CONTROLLER``.
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR Catalyst wireless-controller collector.

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
        """Initialize wireless-controller association metrics."""
        self._mr_wireless_controller_info = self.parent._create_gauge(
            MRMetricName.MR_WIRELESS_CONTROLLER_INFO,
            "Catalyst access point to wireless-controller association info (1 = associated)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.CONTROLLER_SERIAL,
                LabelName.MODE,
                LabelName.COUNTRY_CODE,
            ],
        )
        self._mr_wireless_controller_joined_timestamp_seconds = self.parent._create_gauge(
            MRMetricName.MR_WIRELESS_CONTROLLER_JOINED_TIMESTAMP_SECONDS,
            "Unix timestamp when the Catalyst access point joined its wireless controller",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
            ],
        )

    @staticmethod
    def _parse_joined_at(joined_at: str | None) -> float | None:
        """Parse an ISO-8601 ``joinedAt`` string into unix seconds.

        Parameters
        ----------
        joined_at : str | None
            ISO-8601 timestamp (optionally with a trailing ``Z``).

        Returns
        -------
        float | None
            Unix seconds, or None when absent/unparseable.

        """
        if not joined_at:
            return None
        try:
            normalized = joined_at.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError, TypeError:
            return None

    @log_api_call("getOrganizationWirelessDevicesWirelessControllersByDevice")
    @with_error_handling(
        operation="Collect MR wireless controller associations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_wireless_controllers(self, org_id: str, org_name: str) -> None:
        """Collect the wireless-controller association for every Catalyst AP.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # Scheduler gate: skip the org-wide fetch when not due (#617/#623).
        if not self.parent._should_run_group(EndpointGroupName.MR_WIRELESS_CONTROLLER):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MR_WIRELESS_CONTROLLER)

        with LogContext(org_id=org_id):
            raw_rows = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesWirelessControllersByDevice,
                org_id,
                total_pages="all",
                perPage=1000,
            )
        rows_data = validate_response_format(
            raw_rows,
            expected_type=list,
            operation="getOrganizationWirelessDevicesWirelessControllersByDevice",
        )

        # Fetch succeeded — record the run so the gate can stretch (#617).
        self.parent._mark_group_ran(EndpointGroupName.MR_WIRELESS_CONTROLLER)

        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0

        for raw_row in rows_data:
            row = _WirelessControllerRow.model_validate(raw_row)

            serial = row.serial
            if not serial:
                continue

            network_id = row.network.id if row.network else None
            if (
                allowed_network_ids is not None
                and network_id is not None
                and network_id not in allowed_network_ids
            ):
                skipped += 1
                continue

            controller_serial = row.controller.serial if row.controller else None

            info_labels = {
                LabelName.ORG_ID.value: org_id,
                LabelName.NETWORK_ID.value: network_id or "",
                LabelName.SERIAL.value: serial,
                LabelName.MODEL.value: row.model or "",
                LabelName.CONTROLLER_SERIAL.value: controller_serial or "",
                LabelName.MODE.value: row.mode or "",
                LabelName.COUNTRY_CODE.value: row.countryCode or "",
            }
            self.parent._set_metric(
                self._mr_wireless_controller_info,
                info_labels,
                1.0,
                ttl_seconds=ttl,
            )

            joined_ts = self._parse_joined_at(row.joinedAt)
            if joined_ts is not None:
                self.parent._set_metric(
                    self._mr_wireless_controller_joined_timestamp_seconds,
                    {
                        LabelName.ORG_ID.value: org_id,
                        LabelName.NETWORK_ID.value: network_id or "",
                        LabelName.SERIAL.value: serial,
                    },
                    joined_ts,
                    ttl_seconds=ttl,
                )

        if skipped:
            logger.debug(
                "MR wireless controllers: skipped rows outside network filter",
                org_id=org_id,
                skipped_count=skipped,
            )
