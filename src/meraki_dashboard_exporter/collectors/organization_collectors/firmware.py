"""Firmware upgrade collector for organization firmware metrics."""

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
    from ..organization import OrganizationCollector

logger = get_logger(__name__)

# Statuses considered "pending"/in-flight for the pending-total gauge. The Meraki API
# returns capitalized status values (e.g. "Completed", "Cancelled"; scheduled/in-flight
# events use capitalized forms too), so membership is checked against the lower-cased
# status rather than the raw (label) value.
_PENDING_STATUSES = frozenset({"scheduled", "pending", "started"})


class FirmwareCollector(BaseOrganizationCollector):
    """Collector for organization firmware upgrade metrics."""

    def __init__(self, parent: OrganizationCollector) -> None:
        """Initialize the firmware collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        super().__init__(parent)
        # Bounded label combos emitted on a previous cycle, per org - used to zero out
        # combos that are absent this cycle instead of leaving a stale non-zero value.
        self._seen_upgrade_keys: dict[str, set[tuple[str, str]]] = {}
        self._seen_pending_product_types: dict[str, set[str]] = {}

    @log_api_call("getOrganizationFirmwareUpgrades")
    async def _fetch_firmware_upgrades(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch organization firmware upgrades.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of firmware upgrade events.

        """
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationFirmwareUpgrades,
            org_id,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationFirmwareUpgrades",
            ),
        )

    @with_error_handling(
        operation="Collect firmware upgrade metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect firmware upgrade metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                upgrades = await self._fetch_firmware_upgrades(org_id)
                allowed_network_ids = (
                    await self.inventory.get_allowed_network_ids(org_id)
                    if self.inventory is not None
                    else None
                )

            if not upgrades:
                logger.debug("No firmware upgrade events available", org_id=org_id)

            # Always process (even with an empty list) so bounded label combos that
            # disappear this cycle get explicitly zeroed rather than left stale.
            self._process_firmware_upgrades(org_id, org_name, upgrades, allowed_network_ids)

        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "No firmware upgrade information available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
            else:
                raise  # Let decorator handle non-404 errors

    def _process_firmware_upgrades(
        self,
        org_id: str,
        org_name: str,
        upgrades: list[dict[str, Any]],
        allowed_network_ids: set[str] | None,
    ) -> None:
        """Process firmware upgrade events into aggregated metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        upgrades : list[dict[str, Any]]
            List of firmware upgrade events.
        allowed_network_ids : set[str] | None
            Network IDs permitted by the configured NetworkFilter, or None when
            filtering is disabled (accept every row).

        """
        # Aggregate counts by (product_type, status) - bound cardinality, never per-network/device.
        upgrade_counts: dict[tuple[str, str], int] = {}
        pending_counts: dict[str, int] = {}
        skipped = 0

        for event in upgrades:
            network_id = event.get("network", {}).get("id")
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            product_type = event.get("productTypes", "unknown")
            status = event.get("status", "unknown")

            key = (product_type, status)
            upgrade_counts[key] = upgrade_counts.get(key, 0) + 1

            # The API returns capitalized status values (e.g. "Completed"); compare
            # case-insensitively so the pending gauge actually fires.
            status_normalized = status.lower() if isinstance(status, str) else status
            if status_normalized in _PENDING_STATUSES:
                pending_counts[product_type] = pending_counts.get(product_type, 0) + 1

        org_data = {"id": org_id, "name": org_name}

        # Zero out combos that were emitted on a previous cycle but are absent this
        # cycle, so a status that stops recurring (e.g. all upgrades finish) reports 0
        # rather than freezing at its last non-zero value.
        seen_upgrade_keys = self._seen_upgrade_keys.setdefault(org_id, set())
        for stale_product_type, stale_status in seen_upgrade_keys - upgrade_counts.keys():
            labels = create_org_labels(
                org_data,
                product_type=stale_product_type,
                status=stale_status,
            )
            self._set_metric_value("_org_firmware_upgrades_total", labels, 0)

        for (product_type, status), count in upgrade_counts.items():
            labels = create_org_labels(
                org_data,
                product_type=product_type,
                status=status,
            )
            self._set_metric_value(
                "_org_firmware_upgrades_total",
                labels,
                count,
            )
        seen_upgrade_keys.clear()
        seen_upgrade_keys.update(upgrade_counts.keys())

        seen_pending_product_types = self._seen_pending_product_types.setdefault(org_id, set())
        for stale_product_type in seen_pending_product_types - pending_counts.keys():
            labels = create_org_labels(
                org_data,
                product_type=stale_product_type,
            )
            self._set_metric_value("_org_firmware_upgrades_pending_total", labels, 0)

        for product_type, count in pending_counts.items():
            labels = create_org_labels(
                org_data,
                product_type=product_type,
            )
            self._set_metric_value(
                "_org_firmware_upgrades_pending_total",
                labels,
                count,
            )
        seen_pending_product_types.clear()
        seen_pending_product_types.update(pending_counts.keys())

        logger.info(
            "Collected firmware upgrade metrics",
            org_id=org_id,
            org_name=org_name,
            total_events=len(upgrades),
            pending_product_types=len(pending_counts),
            skipped_filtered_network=skipped,
        )
