"""Client overview collector for organization client and usage metrics."""

from __future__ import annotations

import asyncio
import time
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


class ClientOverviewCollector(BaseOrganizationCollector):
    """Collector for organization client overview metrics."""

    # F-101: bound the stale-zero replay guard below so a genuinely-zero org can't
    # replay a stale non-zero snapshot forever. MEDIUM tier collects every 300s;
    # allow up to 3 consecutive all-zero cycles (~15 min) to be absorbed as the known
    # API glitch, and independently distrust any cached snapshot older than the same
    # ~15 minute budget. Either bound tripping forces the real (truthful) zero to be
    # emitted.
    _MAX_CONSECUTIVE_ZERO_REPLAYS: int = 3
    _MAX_CACHE_AGE_SECONDS: float = 900.0

    def __init__(self, parent: Any) -> None:
        """Initialize the collector with caching for last non-zero values."""
        super().__init__(parent)
        # Cache for last non-zero values per org
        self._last_non_zero_values: dict[str, dict[str, float]] = {}
        # When each org's cache was last refreshed with a genuine non-zero response
        self._last_non_zero_timestamp: dict[str, float] = {}
        # How many consecutive all-zero responses have replayed the cache for this org
        self._consecutive_zero_replays: dict[str, int] = {}

    @log_api_call("getOrganizationClientsOverview")
    async def _fetch_client_overview(self, org_id: str) -> dict[str, Any]:
        """Fetch organization client overview.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any]
            Client overview data.

        """
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationClientsOverview,
            org_id,
            timespan=3600,  # 1 hour - required for reliable data
        )
        return cast(
            dict[str, Any],
            validate_response_format(
                response,
                expected_type=dict,
                operation="getOrganizationClientsOverview",
            ),
        )

    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect client overview metrics.

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
                # Use 1-hour timespan for reliable data
                client_overview = await self._fetch_client_overview(org_id)

                logger.debug(
                    "Fetched client overview data",
                    org_id=org_id,
                    has_data=bool(client_overview),
                    data_keys=list(client_overview.keys()) if client_overview else [],
                )

            if client_overview:
                # Extract client count
                counts = client_overview.get("counts", {})
                total_clients = counts.get("total", 0)

                # Extract usage data (in KB)
                usage = client_overview.get("usage", {})
                overall_usage = usage.get("overall", {})

                total_kb = overall_usage.get("total", 0)
                downstream_kb = overall_usage.get("downstream", 0)
                upstream_kb = overall_usage.get("upstream", 0)

                # Check if all values are zero (likely an API issue)
                if total_clients == 0 and total_kb == 0 and downstream_kb == 0 and upstream_kb == 0:
                    cached = self._last_non_zero_values.get(org_id)
                    cached_at = self._last_non_zero_timestamp.get(org_id)
                    replay_count = self._consecutive_zero_replays.get(org_id, 0)

                    cache_is_fresh = cached_at is not None and (
                        time.time() - cached_at <= self._MAX_CACHE_AGE_SECONDS
                    )
                    within_replay_budget = replay_count < self._MAX_CONSECUTIVE_ZERO_REPLAYS

                    if cached is not None and cache_is_fresh and within_replay_budget:
                        logger.warning(
                            "API returned all zero values, using cached non-zero values",
                            org_id=org_id,
                            replay_count=replay_count + 1,
                            max_replays=self._MAX_CONSECUTIVE_ZERO_REPLAYS,
                        )

                        total_clients = cached.get("total_clients", 0)
                        total_kb = cached.get("total_kb", 0)
                        downstream_kb = cached.get("downstream_kb", 0)
                        upstream_kb = cached.get("upstream_kb", 0)
                        self._consecutive_zero_replays[org_id] = replay_count + 1

                        logger.info(
                            "Using cached non-zero values",
                            org_id=org_id,
                            total_clients=total_clients,
                            total_kb=total_kb,
                        )
                    else:
                        # Replay budget or cache age exceeded (or no cache at all) - trust
                        # the API and emit the real, truthful zero instead of replaying a
                        # stale snapshot forever (F-101).
                        logger.warning(
                            "API returned all zero values; stale-zero cache exhausted, "
                            "emitting real zero values",
                            org_id=org_id,
                            had_cache=cached is not None,
                            cache_fresh=cache_is_fresh,
                            replay_count=replay_count,
                        )
                else:
                    # Update cache with non-zero values
                    self._last_non_zero_values[org_id] = {
                        "total_clients": total_clients,
                        "total_kb": total_kb,
                        "downstream_kb": downstream_kb,
                        "upstream_kb": upstream_kb,
                    }
                    self._last_non_zero_timestamp[org_id] = time.time()
                    self._consecutive_zero_replays[org_id] = 0

                logger.debug(
                    "Client overview metrics",
                    org_id=org_id,
                    total_clients=total_clients,
                    total_kb=total_kb,
                    downstream_kb=downstream_kb,
                    upstream_kb=upstream_kb,
                )

                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}
                org_labels = create_org_labels(org_data)

                # Set metrics
                self._set_metric_value(
                    "_clients_total",
                    org_labels,
                    total_clients,
                )

                self._set_metric_value(
                    "_usage_total_kb",
                    org_labels,
                    total_kb,
                )

                self._set_metric_value(
                    "_usage_downstream_kb",
                    org_labels,
                    downstream_kb,
                )

                self._set_metric_value(
                    "_usage_upstream_kb",
                    org_labels,
                    upstream_kb,
                )

            else:
                logger.warning("No client overview data available", org_id=org_id)

            # Reached only when no exception was raised (success or benign
            # no-data). Signal success so the parent does not count this cycle
            # as a failure (F-172).
            return True

        except Exception as e:
            # Check if this is a 404 error (endpoint might not be available)
            if "404" in str(e):
                logger.debug(
                    "Client overview API not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                # Not available for this org is expected, not a health failure.
                return True
            logger.exception(
                "Failed to collect client overview metrics",
                org_id=org_id,
                org_name=org_name,
            )
            # A real (non-404) failure must be surfaced to OrgHealthTracker via
            # the parent (F-172).
            return False
