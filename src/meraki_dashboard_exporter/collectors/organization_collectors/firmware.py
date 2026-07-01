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
    pass

logger = get_logger(__name__)

# Statuses considered "pending"/in-flight for the pending-total gauge.
_PENDING_STATUSES = frozenset({"scheduled", "pending", "started"})


class FirmwareCollector(BaseOrganizationCollector):
    """Collector for organization firmware upgrade metrics."""

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
        self._track_api_call("getOrganizationFirmwareUpgrades")
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

            if not upgrades:
                logger.debug("No firmware upgrade events available", org_id=org_id)
                return

            self._process_firmware_upgrades(org_id, org_name, upgrades)

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
        self, org_id: str, org_name: str, upgrades: list[dict[str, Any]]
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

        """
        # Aggregate counts by (product_type, status) - bound cardinality, never per-network/device.
        upgrade_counts: dict[tuple[str, str], int] = {}
        pending_counts: dict[str, int] = {}

        for event in upgrades:
            product_type = event.get("productTypes", "unknown")
            status = event.get("status", "unknown")

            key = (product_type, status)
            upgrade_counts[key] = upgrade_counts.get(key, 0) + 1

            if status in _PENDING_STATUSES:
                pending_counts[product_type] = pending_counts.get(product_type, 0) + 1

        org_data = {"id": org_id, "name": org_name}

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

        logger.info(
            "Collected firmware upgrade metrics",
            org_id=org_id,
            org_name=org_name,
            total_events=len(upgrades),
            pending_product_types=len(pending_counts),
        )
