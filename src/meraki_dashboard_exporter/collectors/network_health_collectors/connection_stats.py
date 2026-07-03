"""Connection statistics collector for wireless network connection metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.domain_models import ConnectionStats, NetworkConnectionStats
from ...core.error_handling import validate_response_format
from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.scheduler import EndpointGroupName
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ConnectionStatsCollector(BaseNetworkHealthCollector):
    """Collector for network-wide wireless connection statistics."""

    @log_api_call("getNetworkWirelessConnectionStats")
    async def _fetch_connection_stats(
        self, network_id: str, org_id: str | None = None
    ) -> dict[str, Any]:
        """Fetch network wireless connection statistics.

        Parameters
        ----------
        network_id : str
            Network ID.
        org_id : str | None
            Organization ID for logging and rate limiting context.

        Returns
        -------
        dict[str, Any]
            Connection statistics data.

        """
        _ = org_id  # Included for logging/rate limiting context
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessConnectionStats,
            network_id,
            timespan=1800,  # 30 minutes
        )
        return cast(
            dict[str, Any],
            validate_response_format(
                response,
                expected_type=dict,
                operation="getNetworkWirelessConnectionStats",
            ),
        )

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless connection statistics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        try:
            with LogContext(network_id=network_id, network_name=network_name, org_id=org_id):
                # Use 30 minute (1800 second) timespan as minimum
                connection_stats = await self._fetch_connection_stats(network_id, org_id=org_id)

            # Parse response using domain model
            if not connection_stats:
                # Create empty stats when no data
                stats = ConnectionStats()
            else:
                # Parse API response to domain model
                stats = ConnectionStats(**connection_stats)

            # Create full network stats model
            network_stats = NetworkConnectionStats(networkId=network_id, connectionStats=stats)

            # Create network labels using helper
            labels = create_network_labels(
                network,
                org_id=org_id,
                org_name=org_name,
            )

            # Per-series TTL from the group's solved interval (#617 §1f) so the
            # 1800s-windowed series does not flap under a stretched interval.
            ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_CONNECTION_STATS)

            # Set metrics for each connection stat type
            for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                value = getattr(network_stats.connectionStats, stat_type, 0)
                # Add stat_type to labels
                stat_labels = {**labels, "stat_type": stat_type}
                self._set_metric_value(
                    "_network_connection_stats",
                    stat_labels,
                    value,
                    ttl_seconds=ttl_seconds,
                )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            # or if the API exhausted retries on a rate limit.
            error_str = str(e)
            if (
                "400" in error_str
                or "404" in error_str
                or "Bad Request" in error_str
                or "rate limit" in error_str.lower()
            ):
                logger.debug(
                    "Network connection stats not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect network connection stats",
                    network_id=network_id,
                    network_name=network_name,
                )
