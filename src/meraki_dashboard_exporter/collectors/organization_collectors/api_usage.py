"""API usage collector for organization API metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.error_handling import validate_response_format
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

    def __init__(self, parent: Any) -> None:
        """Initialize the API usage collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        super().__init__(parent)
        # Per-org set of status codes ever observed in a valid API response.
        # Cardinality is bounded by actual HTTP status codes the Meraki API
        # reports (never attacker/user controlled), so it's safe to keep
        # zeroing these on every cycle even once they stop appearing in the
        # response (F-096: prevents the gauge freezing at its last non-zero
        # value once a status code's rolling count drops to 0 or the code
        # disappears from responseCodeCounts entirely).
        self._known_status_codes: dict[str, set[str]] = {}

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
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationApiRequestsOverview,
            org_id,
            timespan=3600,  # Last 1 hour
        )
        return cast(
            dict[str, Any],
            validate_response_format(
                response,
                expected_type=dict,
                operation="getOrganizationApiRequestsOverview",
            ),
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

                # Calculate total requests, defensively skipping any
                # non-numeric entries so a single bad value can't abort the
                # whole collection cycle (F-099).
                total_requests: int | float = 0
                valid_counts: dict[str, int | float] = {}

                for status_code, count in response_codes.items():
                    if isinstance(count, bool) or not isinstance(count, int | float):
                        logger.warning(
                            "Skipping non-numeric API request count",
                            org_id=org_id,
                            status_code=status_code,
                            count=count,
                        )
                        continue
                    valid_counts[status_code] = count
                    total_requests += count

                # Track every status code ever seen for this org so it keeps
                # being emitted (as 0) once its count drops to zero or the
                # code disappears from the response entirely (F-096).
                known_codes = self._known_status_codes.setdefault(org_id, set())
                known_codes.update(valid_counts)

                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}

                # Set metrics for every known status code, including zeros
                for status_code in known_codes:
                    count = valid_counts.get(status_code, 0)
                    labels = create_org_labels(
                        org_data,
                        status_code=status_code,
                    )
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
                    unique_status_codes=sum(1 for c in valid_counts.values() if c > 0),
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
