"""Client overview collector for organization client and usage metrics."""

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


class ClientOverviewCollector(BaseOrganizationCollector):
    """Collector for organization client overview metrics."""

    def __init__(self, parent: Any) -> None:
        """Initialize the collector with caching for last non-zero values."""
        super().__init__(parent)
        # Cache for last non-zero values per org
        self._last_non_zero_values: dict[str, dict[str, float]] = {}

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
        self._track_api_call("getOrganizationClientsOverview")
        return await asyncio.to_thread(
            self.api.organizations.getOrganizationClientsOverview,
            org_id,
            timespan=3600,  # 1 hour - required for reliable data
        )

    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect client overview metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

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
                    logger.warning(
                        "API returned all zero values, using cached non-zero values if available",
                        org_id=org_id,
                    )

                    # Use cached values if available
                    if org_id in self._last_non_zero_values:
                        cached = self._last_non_zero_values[org_id]
                        total_clients = cached.get("total_clients", 0)
                        total_kb = cached.get("total_kb", 0)
                        downstream_kb = cached.get("downstream_kb", 0)
                        upstream_kb = cached.get("upstream_kb", 0)

                        logger.info(
                            "Using cached non-zero values",
                            org_id=org_id,
                            total_clients=total_clients,
                            total_kb=total_kb,
                        )
                else:
                    # Update cache with non-zero values
                    self._last_non_zero_values[org_id] = {
                        "total_clients": total_clients,
                        "total_kb": total_kb,
                        "downstream_kb": downstream_kb,
                        "upstream_kb": upstream_kb,
                    }

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

        except Exception as e:
            # Check if this is a 404 error (endpoint might not be available)
            if "404" in str(e):
                logger.debug(
                    "Client overview API not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
            else:
                logger.exception(
                    "Failed to collect client overview metrics",
                    org_id=org_id,
                    org_name=org_name,
                )
