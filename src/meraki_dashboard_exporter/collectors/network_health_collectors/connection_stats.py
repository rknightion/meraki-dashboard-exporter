"""Connection statistics collector for wireless network connection metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.domain_models import ConnectionStats, NetworkConnectionStats
from ...core.logging import get_logger
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ConnectionStatsCollector(BaseNetworkHealthCollector):
    """Collector for network-wide wireless connection statistics."""

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless connection statistics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)

        try:
            logger.debug(
                "Fetching network connection stats",
                network_id=network_id,
                network_name=network_name,
            )

            # Track API call
            self._track_api_call("getNetworkWirelessConnectionStats")

            # Use 30 minute (1800 second) timespan as minimum
            connection_stats = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessConnectionStats,
                network_id,
                timespan=1800,  # 30 minutes
            )

            # Parse response using domain model
            if not connection_stats:
                # Create empty stats when no data
                stats = ConnectionStats()
            else:
                # Parse API response to domain model
                stats = ConnectionStats(**connection_stats)

            # Create full network stats model
            network_stats = NetworkConnectionStats(networkId=network_id, connectionStats=stats)

            # Set metrics for each connection stat type
            for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                value = getattr(network_stats.connectionStats, stat_type, 0)
                self._set_metric_value(
                    "_network_connection_stats",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                        "stat_type": stat_type,
                    },
                    value,
                )

            logger.debug(
                "Successfully collected network connection stats",
                network_id=network_id,
                stats=network_stats.connectionStats.model_dump(),
            )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
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
