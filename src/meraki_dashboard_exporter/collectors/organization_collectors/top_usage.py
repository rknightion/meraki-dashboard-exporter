"""Org-wide top-N usage collector (#299).

Collects the organization "summary top" usage leaderboards (top clients, top
SSIDs, top client-device manufacturers) over the API's default trailing 1-day
window. All three are pre-aggregated org-wide summaries (the analog of the
application-usage summary), so — like ``_collect_application_usage_metrics`` on
the coordinator — they are emitted unfiltered rather than row-filtered by
NetworkFilter (there is no per-network breakdown to filter on).
"""

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
    pass

logger = get_logger(__name__)

# Bounded top-N requested from each leaderboard endpoint.
_TOP_N = 10

# ⚠ Phase-6 live verification: the summary-top usage fields are reported in
# decimal kilobytes (matching getOrganizationClientsOverview, converted ×1000 in
# client_overview.py). We follow that established codebase convention so the
# *_total_bytes gauges carry base SI units, but the exact unit + the `usage`/`id`
# field names must be confirmed against the live API before Phase 6 closes.
_USAGE_KB_TO_BYTES = 1000


class TopUsageCollector(BaseOrganizationCollector):
    """Collector for organization-wide top-N usage leaderboards."""

    @log_api_call("getOrganizationSummaryTopClientsByUsage")
    async def _fetch_top_clients(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the top-N clients by usage."""
        self._track_api_call("getOrganizationSummaryTopClientsByUsage")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationSummaryTopClientsByUsage,
            org_id,
            quantity=_TOP_N,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationSummaryTopClientsByUsage",
            ),
        )

    @log_api_call("getOrganizationSummaryTopSsidsByUsage")
    async def _fetch_top_ssids(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the top-N SSIDs by usage."""
        self._track_api_call("getOrganizationSummaryTopSsidsByUsage")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationSummaryTopSsidsByUsage,
            org_id,
            quantity=_TOP_N,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationSummaryTopSsidsByUsage",
            ),
        )

    @log_api_call("getOrganizationSummaryTopClientsManufacturersByUsage")
    async def _fetch_top_manufacturers(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the top-N client-device manufacturers by usage."""
        self._track_api_call("getOrganizationSummaryTopClientsManufacturersByUsage")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationSummaryTopClientsManufacturersByUsage,
            org_id,
            quantity=_TOP_N,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationSummaryTopClientsManufacturersByUsage",
            ),
        )

    @staticmethod
    def _usage_total_bytes(entry: dict[str, Any]) -> float:
        """Extract an entry's total usage and convert to base-unit bytes.

        ⚠ The ``usage`` container and its ``total`` key need live verification
        (Phase 6); handled leniently so an unexpected shape yields 0 rather than
        raising.
        """
        usage = entry.get("usage")
        total: Any = 0
        if isinstance(usage, dict):
            total = usage.get("total", 0)
        elif isinstance(usage, (int, float)) and not isinstance(usage, bool):
            # Some summary endpoints report usage as a bare number.
            total = usage
        if not isinstance(total, (int, float)) or isinstance(total, bool):
            return 0.0
        return float(total) * _USAGE_KB_TO_BYTES

    @with_error_handling(
        operation="Collect org top usage metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect org-wide top-N usage metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success or when the endpoints are unavailable for this
            org (404/400). On a real failure the error is re-raised so the
            decorator can retry rate limits and then swallow it; the coordinator
            treats any non-``True`` result as a failure (F-172).

        """
        if not self.parent._should_run_group(EndpointGroupName.ORG_TOP_USAGE):
            return True

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                clients = await self._fetch_top_clients(org_id)
                ssids = await self._fetch_top_ssids(org_id)
                manufacturers = await self._fetch_top_manufacturers(org_id)

            self.parent._mark_group_ran(EndpointGroupName.ORG_TOP_USAGE)
            ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_TOP_USAGE)
            org_data = {"id": org_id, "name": org_name}

            for entry in clients:
                # ID-only per #533; name joins via meraki_client_info.
                client_id = entry.get("id") or entry.get("clientId")
                if not client_id:
                    continue
                labels = create_org_labels(org_data, client_id=str(client_id))
                self._set_metric_value(
                    "_org_top_client_usage_total_bytes",
                    labels,
                    self._usage_total_bytes(entry),
                    ttl_seconds=ttl,
                )

            for entry in ssids:
                ssid_name = entry.get("name")
                if ssid_name is None:
                    continue
                labels = create_org_labels(org_data, ssid=str(ssid_name))
                self._set_metric_value(
                    "_org_top_ssid_usage_total_bytes",
                    labels,
                    self._usage_total_bytes(entry),
                    ttl_seconds=ttl,
                )

            for entry in manufacturers:
                manufacturer = entry.get("name")
                if manufacturer is None:
                    continue
                labels = create_org_labels(org_data, manufacturer=str(manufacturer))
                self._set_metric_value(
                    "_org_top_manufacturer_usage_total_bytes",
                    labels,
                    self._usage_total_bytes(entry),
                    ttl_seconds=ttl,
                )

            logger.debug(
                "Collected org top usage metrics",
                org_id=org_id,
                clients=len(clients),
                ssids=len(ssids),
                manufacturers=len(manufacturers),
            )
            return True

        except Exception as e:
            if "404" in str(e) or "400" in str(e):
                logger.debug(
                    "Org top usage endpoints not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle non-404 errors (retry + swallow)
