"""Client overview collector for organization client and usage metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ClientOverviewCollector(BaseOrganizationCollector):
    """Collector for organization client overview metrics."""

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
            timespan=1800,  # 30 minutes - minimum required for valid data
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
                # Use 30-minute timespan (minimum required for valid data)
                client_overview = await self._fetch_client_overview(org_id)

                logger.debug(
                    "Fetched client overview data",
                    org_id=org_id,
                    has_data=bool(client_overview),
                    data_keys=list(client_overview.keys()) if client_overview else [],
                )

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

                self._set_metric_value(
                    "_clients_total",
                    {
                        "org_id": org_id,
                        "org_name": org_name,
                    },
                    total_clients,
                )

                # Extract usage data (in KB)
                usage = client_overview.get("usage", {})
                overall_usage = usage.get("overall", {})

                total_kb = overall_usage.get("total", 0)
                downstream_kb = overall_usage.get("downstream", 0)
                upstream_kb = overall_usage.get("upstream", 0)

                logger.debug(
                    "Client overview metrics",
                    org_id=org_id,
                    total_clients=total_clients,
                    total_kb=total_kb,
                    downstream_kb=downstream_kb,
                    upstream_kb=upstream_kb,
                )

                logger.debug(
                    "Client overview metrics",
                    org_id=org_id,
                    total_clients=total_clients,
                    total_kb=total_kb,
                    downstream_kb=downstream_kb,
                    upstream_kb=upstream_kb,
                )

                # Set usage metrics
                self._set_metric_value(
                    "_usage_total_kb",
                    {
                        "org_id": org_id,
                        "org_name": org_name,
                    },
                    total_kb,
                )

                self._set_metric_value(
                    "_usage_downstream_kb",
                    {
                        "org_id": org_id,
                        "org_name": org_name,
                    },
                    downstream_kb,
                )

                self._set_metric_value(
                    "_usage_upstream_kb",
                    {
                        "org_id": org_id,
                        "org_name": org_name,
                    },
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
