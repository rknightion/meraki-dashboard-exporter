"""Client overview collector for organization client and usage metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...core.logging import get_logger
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ClientOverviewCollector(BaseOrganizationCollector):
    """Collector for organization client overview metrics."""

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
            logger.debug("Fetching client overview", org_id=org_id)
            self._track_api_call("getOrganizationClientsOverview")

            # Use 5-minute timespan to get the last complete 5-minute window
            client_overview = await asyncio.to_thread(
                self.api.organizations.getOrganizationClientsOverview,
                org_id,
                timespan=300,  # 5 minutes
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
                logger.debug(
                    "Set client count",
                    org_id=org_id,
                    total_clients=total_clients,
                )

                # Extract usage data (in KB)
                usage = client_overview.get("usage", {})
                overall_usage = usage.get("overall", {})

                total_kb = overall_usage.get("total", 0)
                downstream_kb = overall_usage.get("downstream", 0)
                upstream_kb = overall_usage.get("upstream", 0)

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

                logger.debug(
                    "Successfully collected client overview metrics",
                    org_id=org_id,
                    total_clients=total_clients,
                    total_kb=total_kb,
                    downstream_kb=downstream_kb,
                    upstream_kb=upstream_kb,
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
