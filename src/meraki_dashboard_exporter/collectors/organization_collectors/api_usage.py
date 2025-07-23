"""API usage collector for organization API metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class APIUsageCollector(BaseOrganizationCollector):
    """Collector for organization API usage metrics."""

    @log_api_call("getOrganizationApiRequestsOverview")
    async def _fetch_api_requests_overview(self, org_id: str) -> dict[str, Any]:
        """Fetch organization API requests overview.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any]
            API request overview data with response code counts.

        """
        self._track_api_call("getOrganizationApiRequestsOverview")
        return await asyncio.to_thread(
            self.api.organizations.getOrganizationApiRequestsOverview,
            org_id,
            timespan=3600,  # Last 1 hour
        )

    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect API usage metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                overview = await self._fetch_api_requests_overview(org_id)
                logger.debug(
                    "Fetched API requests overview",
                    org_id=org_id,
                    has_data=bool(overview),
                    response_type=type(overview).__name__,
                )

            if overview and isinstance(overview, dict) and "responseCodeCounts" in overview:
                response_codes = overview["responseCodeCounts"]

                # Calculate total requests
                total_requests = 0

                # Set metrics for each non-zero status code
                for status_code, count in response_codes.items():
                    if count > 0:
                        total_requests += count
                        # Create org labels using helper
                        org_data = {"id": org_id, "name": org_name}
                        labels = create_org_labels(
                            org_data,
                            status_code=status_code,
                        )
                        # Set metric for this status code
                        self._set_metric_value(
                            "_api_requests_by_status",
                            labels,
                            count,
                        )
                        logger.debug(
                            "Set API request metric",
                            org_id=org_id,
                            status_code=status_code,
                            count=count,
                        )

                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}
                org_labels = create_org_labels(org_data)

                # Also set total requests metric
                self._set_metric_value(
                    "_api_requests_total",
                    org_labels,
                    total_requests,
                )

                logger.info(
                    "Collected API usage metrics",
                    org_id=org_id,
                    org_name=org_name,
                    total_requests=total_requests,
                    unique_status_codes=sum(1 for c in response_codes.values() if c > 0),
                )
            else:
                logger.warning(
                    "No API request overview data available",
                    org_id=org_id,
                    overview_type=type(overview).__name__ if overview else "None",
                    has_response_codes="responseCodeCounts" in overview
                    if isinstance(overview, dict)
                    else False,
                )

        except Exception:
            logger.exception(
                "Failed to collect API metrics",
                org_id=org_id,
                org_name=org_name,
            )
