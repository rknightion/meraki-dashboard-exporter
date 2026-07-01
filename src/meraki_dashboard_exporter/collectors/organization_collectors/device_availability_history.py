"""Device availability change history collector for organization metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# timespan matches the MEDIUM (300s) collection cadence so each poll counts only
# availability changes that occurred since the previous run (a windowed flap count).
_TIMESPAN_SECONDS = 300


class DeviceAvailabilityHistoryCollector(BaseOrganizationCollector):
    """Collector for organization device availability change history metrics."""

    @log_api_call("getOrganizationDevicesAvailabilitiesChangeHistory")
    async def _fetch_availability_change_history(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch organization device availability change history.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of device availability change events.

        """
        self._track_api_call("getOrganizationDevicesAvailabilitiesChangeHistory")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory,
            org_id,
            timespan=_TIMESPAN_SECONDS,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationDevicesAvailabilitiesChangeHistory",
            ),
        )

    @with_error_handling(
        operation="Collect device availability change history metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect device availability change history metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                events = await self._fetch_availability_change_history(org_id)

            if not events:
                logger.debug("No device availability change events available", org_id=org_id)
                return

            self._process_availability_changes(org_id, org_name, events)

        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "No device availability change history available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
            else:
                raise  # Let decorator handle non-404 errors

    def _process_availability_changes(
        self, org_id: str, org_name: str, events: list[dict[str, Any]]
    ) -> None:
        """Process device availability change events into aggregated metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        events : list[dict[str, Any]]
            List of device availability change events.

        """
        # Aggregate counts by (product_type, new_status) - bound cardinality, never per-device.
        change_counts: dict[tuple[str, str], int] = {}

        for event in events:
            product_type = event.get("device", {}).get("productType", "unknown")
            new_status = next(
                (
                    d["value"]
                    for d in event.get("details", {}).get("new", [])
                    if d.get("name") == "status"
                ),
                "unknown",
            )

            key = (product_type, new_status)
            change_counts[key] = change_counts.get(key, 0) + 1

        org_data = {"id": org_id, "name": org_name}

        for (product_type, new_status), count in change_counts.items():
            labels = create_org_labels(
                org_data,
                product_type=product_type,
                status=new_status,
            )
            self._set_metric_value(
                "_org_devices_availability_changes_total",
                labels,
                count,
            )

        logger.info(
            "Collected device availability change history metrics",
            org_id=org_id,
            org_name=org_name,
            total_events=len(events),
            unique_combinations=len(change_counts),
        )
