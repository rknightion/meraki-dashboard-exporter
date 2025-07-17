"""API usage collector for organization API metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...core.logging import get_logger
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class APIUsageCollector(BaseOrganizationCollector):
    """Collector for organization API usage metrics."""

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
            logger.debug("Fetching API requests", org_id=org_id)
            self._track_api_call("getOrganizationApiRequests")
            api_requests = await asyncio.to_thread(
                self.api.organizations.getOrganizationApiRequests,
                org_id,
                total_pages="all",
                timespan=86400,  # Last 24 hours
            )

            if api_requests:
                # Sum up total requests
                total_requests = sum(req.get("total", 0) for req in api_requests)
                self._set_metric_value(
                    "_api_requests_total",
                    {
                        "org_id": org_id,
                        "org_name": org_name,
                    },
                    total_requests,
                )

                # Get rate limit if available
                # Rate limit is usually consistent across all requests
                if api_requests and api_requests[0].get("responseCodeCounts"):
                    # Look for 429 responses which indicate rate limiting
                    # This is a simplified approach - actual rate limit may vary
                    # TODO: Get actual rate limit from headers or API response
                    logger.debug(
                        "Successfully collected API metrics",
                        org_id=org_id,
                        total_requests=total_requests,
                    )
                else:
                    logger.debug("No API request data available", org_id=org_id)

        except Exception:
            logger.exception(
                "Failed to collect API metrics",
                org_id=org_id,
                org_name=org_name,
            )
