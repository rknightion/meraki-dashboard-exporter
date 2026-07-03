"""API usage collector for organization API metrics."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict

from ...core.error_handling import validate_response_format
from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Cardinality guard for the per-operation breakdown (#274): the
# getOrganizationApiRequests endpoint returns one row per request, so we
# aggregate client-side and only keep the top-N operations by request count;
# every other operation collapses into a single "other" bucket. Bounded by
# construction: at most _MAX_TRACKED_OPERATIONS + 1 distinct endpoint labels
# per org, times the handful of HTTP status codes actually observed.
_MAX_TRACKED_OPERATIONS = 20
_OTHER_OPERATION = "other"


class ApiRequestEntry(BaseModel):
    """A single Meraki API request row from getOrganizationApiRequests.

    Only the two bounded, non-PII fields we aggregate on are modelled;
    ``extra="ignore"`` deliberately drops adminId / sourceIp / path / userAgent
    so PII can never reach a metric label even by accident (#274).
    """

    model_config = ConfigDict(extra="ignore")

    operationId: str | None = None
    responseCode: int | None = None


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

    @log_api_call("getOrganizationApiRequests")
    async def _fetch_api_requests(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the raw per-request API request log for the last hour.

        Returns one row per API request (across all clients of the org's
        Dashboard API). Callers MUST aggregate client-side before emitting any
        metric - the row set is unbounded and carries PII fields.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            Raw API request rows.

        """
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationApiRequests,
            org_id,
            timespan=3600,  # Last 1 hour, aligned with the overview call
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationApiRequests",
            ),
        )

    def _aggregate_requests_by_operation(
        self, entries: list[dict[str, Any]]
    ) -> dict[tuple[str, str], int]:
        """Aggregate raw request rows into bounded (operation, status_code) counts.

        Counts requests per ``(operationId, responseCode)``, then caps the
        distinct operations to the top ``_MAX_TRACKED_OPERATIONS`` by total
        request count; every other operation (and any row missing an
        operationId) collapses into the ``_OTHER_OPERATION`` bucket. This keeps
        the emitted label set bounded regardless of how many distinct endpoints
        or admins hit the org's API (#274).

        Parameters
        ----------
        entries : list[dict[str, Any]]
            Raw API request rows.

        Returns
        -------
        dict[tuple[str, str], int]
            Mapping of ``(operation, status_code)`` -> request count, with
            operations already capped/bucketed.

        """
        raw_counts: dict[tuple[str, str], int] = defaultdict(int)
        per_op_totals: dict[str, int] = defaultdict(int)

        for entry in entries:
            row = ApiRequestEntry.model_validate(entry)
            operation = row.operationId or _OTHER_OPERATION
            status_code = "" if row.responseCode is None else str(row.responseCode)
            raw_counts[(operation, status_code)] += 1
            per_op_totals[operation] += 1

        # Rank operations by total request count; keep the busiest N named.
        top_operations = {
            op
            for op, _ in sorted(per_op_totals.items(), key=lambda kv: kv[1], reverse=True)[
                :_MAX_TRACKED_OPERATIONS
            ]
        }

        capped: dict[tuple[str, str], int] = defaultdict(int)
        for (operation, status_code), count in raw_counts.items():
            key_op = operation if operation in top_operations else _OTHER_OPERATION
            capped[(key_op, status_code)] += count
        return dict(capped)

    async def _collect_requests_by_operation(
        self, org_id: str, org_name: str, org_data: dict[str, str]
    ) -> None:
        """Fetch, aggregate and emit the per-operation API request breakdown.

        Best-effort enrichment (#274): a failure here must not lose the primary
        status-code metrics, so callers invoke this in its own guarded block.
        """
        entries = await self._fetch_api_requests(org_id)
        by_operation = self._aggregate_requests_by_operation(entries)

        for (operation, status_code), count in by_operation.items():
            labels = create_org_labels(
                org_data,
                endpoint=operation,
                status_code=status_code,
            )
            self._set_metric_value("_api_requests_by_operation", labels, count)

        logger.debug(
            "Collected API requests by operation",
            org_id=org_id,
            org_name=org_name,
            operations=len({op for op, _ in by_operation}),
            series=len(by_operation),
        )

    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect API usage metrics.

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
            org (404); ``False`` on a real (non-404) failure. The parent
            coordinator uses this signal so an isolated failure here is counted
            by ``OrgHealthTracker`` (F-172) instead of being silently swallowed.

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

                # Per-operation breakdown (#274) is best-effort enrichment on a
                # separate, heavier endpoint: keep its failure from discarding
                # the status-code metrics already emitted above, and from
                # flipping the org-health signal returned below.
                with LogContext(org_id=org_id, org_name=org_name):
                    try:
                        await self._collect_requests_by_operation(org_id, org_name, org_data)
                    except Exception:
                        logger.warning(
                            "Failed to collect API requests by operation; "
                            "status-code metrics are unaffected",
                            org_id=org_id,
                            org_name=org_name,
                            exc_info=True,
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

            # Reached only when no exception was raised (success or benign
            # no-data). Signal success so the parent does not count this cycle
            # as a failure (F-172).
            return True

        except Exception as e:
            # A 404 means the endpoint is not available for this org -- expected,
            # not a health failure. Any other error is a real failure that must
            # be surfaced to OrgHealthTracker via the parent (F-172).
            if "404" in str(e):
                logger.debug(
                    "API usage endpoint not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            logger.exception(
                "Failed to collect API metrics",
                org_id=org_id,
                org_name=org_name,
            )
            return False
