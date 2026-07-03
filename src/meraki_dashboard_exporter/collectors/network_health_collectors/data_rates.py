"""Data rates collector for wireless network throughput metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

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


class DataRatesCollector(BaseNetworkHealthCollector):
    """Collector for network-wide wireless data rate metrics."""

    @log_api_call("getNetworkWirelessDataRateHistory")
    async def _fetch_data_rate_history(
        self, network_id: str, org_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch network wireless data rate history.

        Parameters
        ----------
        network_id : str
            Network ID.
        org_id : str | None
            Organization ID for logging and rate-limiting context (F-170). The
            @log_api_call decorator reads it from kwargs so the client-side rate
            limiter keys by the owning org instead of the shared "global" bucket.

        Returns
        -------
        list[dict[str, Any]]
            Data rate history.

        """
        _ = org_id  # Consumed by the @log_api_call decorator for rate-limit keying.
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessDataRateHistory,
            network_id,
            timespan=300,
            resolution=300,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getNetworkWirelessDataRateHistory",
            ),
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
                data_rate_history = await self._fetch_data_rate_history(network_id, org_id=org_id)

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

                # Extract download and upload rates. The API reports these fields
                # (downloadKbps/uploadKbps) in kilobytes-per-second, not kilobits,
                # per the OpenAPI spec (F-065) -- convert x1000 to bytes/second
                # (#531 D5/APIDEV-03; NOT /8, this is not a bit conversion).
                # On a quiet network the latest bucket has the keys PRESENT but
                # null, so `.get(k, 0)` returns None -> coalesce to 0 to avoid a
                # TypeError on the multiply (#632). An all-null bucket emits 0.
                download_bytes_per_second = (latest_data.get("downloadKbps") or 0) * 1000
                upload_bytes_per_second = (latest_data.get("uploadKbps") or 0) * 1000

                # Create network labels using helper
                labels = create_network_labels(
                    network,
                    org_id=org_id,
                    org_name=org_name,
                )

                # Per-series TTL from the group's solved interval (#617 §1f).
                ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_DATA_RATES)

                # Set the metrics
                self._set_metric_value(
                    "_network_wireless_download_kbps",
                    labels,
                    download_bytes_per_second,
                    ttl_seconds=ttl_seconds,
                )

                self._set_metric_value(
                    "_network_wireless_upload_kbps",
                    labels,
                    upload_bytes_per_second,
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
