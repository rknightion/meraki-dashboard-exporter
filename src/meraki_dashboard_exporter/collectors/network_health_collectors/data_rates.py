"""Data rates collector for wireless network throughput metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class DataRatesCollector(BaseNetworkHealthCollector):
    """Collector for network-wide wireless data rate metrics."""

    @log_api_call("getNetworkWirelessDataRateHistory")
    async def _fetch_data_rate_history(self, network_id: str) -> list[dict[str, Any]]:
        """Fetch network wireless data rate history.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]]
            Data rate history.

        """
        return await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessDataRateHistory,
            network_id,
            timespan=300,
            resolution=300,
        )

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless data rate metrics.

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
                # Use 300 second (5 minute) resolution with recent timespan
                # Using timespan of 300 seconds to get the most recent 5-minute data block
                data_rate_history = await self._fetch_data_rate_history(network_id)

            # Handle empty response
            if not data_rate_history:
                logger.debug(
                    "No data rate history available",
                    network_id=network_id,
                )
                return

            # Get the most recent data point
            if isinstance(data_rate_history, list) and len(data_rate_history) > 0:
                # Sort by endTs to ensure we get the most recent
                sorted_data = sorted(
                    data_rate_history, key=lambda x: x.get("endTs", ""), reverse=True
                )
                latest_data = sorted_data[0]

                # Extract download and upload rates
                download_kbps = latest_data.get("downloadKbps", 0)
                upload_kbps = latest_data.get("uploadKbps", 0)

                # Create network labels using helper
                labels = create_network_labels(
                    network,
                    org_id=org_id,
                    org_name=org_name,
                )

                # Set the metrics
                self._set_metric_value(
                    "_network_wireless_download_kbps",
                    labels,
                    download_kbps,
                )

                self._set_metric_value(
                    "_network_wireless_upload_kbps",
                    labels,
                    upload_kbps,
                )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Network data rates not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect network data rates",
                    network_id=network_id,
                    network_name=network_name,
                )
