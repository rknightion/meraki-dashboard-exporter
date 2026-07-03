"""Device availability change history collector for organization metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.scheduler import EndpointGroupName
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    from ..organization import OrganizationCollector

logger = get_logger(__name__)


class DeviceAvailabilityHistoryCollector(BaseOrganizationCollector):
    """Collector for organization device availability change history metrics."""

    def __init__(self, parent: OrganizationCollector) -> None:
        """Initialize the device availability history collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        super().__init__(parent)
        # Bounded label combos emitted on a previous cycle, per org - used to zero out
        # combos that are absent this cycle instead of leaving a stale non-zero value.
        self._seen_change_keys: dict[str, set[tuple[str, str]]] = {}

    @log_api_call("getOrganizationDevicesAvailabilitiesChangeHistory")
    async def _fetch_availability_change_history(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch organization device availability change history.

        The fetch window is tied to the configured MEDIUM update interval
        (``settings.update_intervals.medium``, operator-configurable 300-1800s)
        rather than a hardcoded value, so it always matches the actual
        collection cadence: each poll counts only availability changes that
        occurred since (approximately) the previous run.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of device availability change events.

        """
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory,
            org_id,
            timespan=self.settings.update_intervals.medium,
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
    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect device availability change history metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success or when the endpoint is unavailable for this
            org (404). On a real (non-404) failure the error is re-raised so
            the ``with_error_handling`` decorator can retry rate limits and
            then swallow it (returning ``None``); the parent coordinator treats
            any non-``True`` result as a failure so it is counted by
            ``OrgHealthTracker`` (F-172).

        """
        if not self.parent._should_run_group(EndpointGroupName.ORG_AVAILABILITY_HISTORY):
            return True

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                events = await self._fetch_availability_change_history(org_id)
                allowed_network_ids = (
                    await self.inventory.get_allowed_network_ids(org_id)
                    if self.inventory is not None
                    else None
                )

            # Fetch succeeded — record the group ran so gating stretches.
            self.parent._mark_group_ran(EndpointGroupName.ORG_AVAILABILITY_HISTORY)

            if not events:
                logger.debug("No device availability change events available", org_id=org_id)

            # Always process (even with an empty list) so bounded label combos that
            # disappear this cycle get explicitly zeroed rather than left stale.
            self._process_availability_changes(org_id, org_name, events, allowed_network_ids)
            return True

        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "No device availability change history available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle non-404 errors (retry + swallow)

    def _process_availability_changes(
        self,
        org_id: str,
        org_name: str,
        events: list[dict[str, Any]],
        allowed_network_ids: set[str] | None,
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
        allowed_network_ids : set[str] | None
            Network IDs permitted by the configured NetworkFilter, or None when
            filtering is disabled (accept every row).

        """
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_AVAILABILITY_HISTORY)

        # Aggregate counts by (product_type, new_status) - bound cardinality, never per-device.
        change_counts: dict[tuple[str, str], int] = {}
        skipped = 0

        for event in events:
            network_id = event.get("network", {}).get("id")
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

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

        # Zero out combos that were emitted on a previous cycle but are absent this
        # cycle (a quiet window with no flaps), so the windowed count reports 0
        # rather than freezing at its last non-zero value forever.
        seen_change_keys = self._seen_change_keys.setdefault(org_id, set())
        for stale_product_type, stale_status in seen_change_keys - change_counts.keys():
            labels = create_org_labels(
                org_data,
                product_type=stale_product_type,
                status=stale_status,
            )
            self._set_metric_value(
                "_org_devices_availability_changes_total", labels, 0, ttl_seconds=ttl
            )

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
                ttl_seconds=ttl,
            )
        seen_change_keys.clear()
        seen_change_keys.update(change_counts.keys())

        logger.info(
            "Collected device availability change history metrics",
            org_id=org_id,
            org_name=org_name,
            total_events=len(events),
            unique_combinations=len(change_counts),
            skipped_filtered_network=skipped,
        )
