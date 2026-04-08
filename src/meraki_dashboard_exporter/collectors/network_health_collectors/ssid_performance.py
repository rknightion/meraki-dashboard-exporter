"""Per-SSID wireless performance collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SSIDPerformanceCollector(BaseNetworkHealthCollector):
    """Collector for per-SSID wireless performance metrics.

    Collects failed wireless connection counts broken down by SSID and
    failure step (assoc, auth, dhcp, dns) using the Meraki
    getNetworkWirelessFailedConnections API endpoint.
    """

    @log_api_call("getNetworkWirelessFailedConnections")
    async def _fetch_failed_connections(self, network_id: str) -> list[dict[str, Any]]:
        """Fetch failed wireless connections for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]]
            List of failed connection entries grouped by SSID and failure step.

        """
        return await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessFailedConnections,
            network_id,
            timespan=3600,  # 1 hour
        )

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect per-SSID wireless performance metrics for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data including id, name, orgId, and orgName.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        try:
            with LogContext(network_id=network_id, network_name=network_name, org_id=org_id):
                failed_connections = await self._fetch_failed_connections(network_id)

            if not failed_connections:
                return

            # Aggregate failed connections by SSID number and failure step
            # The API returns one entry per client connection failure; we sum counts
            failure_counts: dict[tuple[str, str], int] = {}
            for entry in failed_connections:
                ssid_raw = entry.get("ssidNumber")
                ssid = str(ssid_raw) if ssid_raw is not None else "unknown"
                failure_step = entry.get("failureStep") or "unknown"
                count = int(entry.get("failures", 1))
                key = (ssid, failure_step)
                failure_counts[key] = failure_counts.get(key, 0) + count

            # Set metrics per SSID / failure step combination
            base_labels = create_network_labels(
                network,
                org_id=org_id,
                org_name=org_name,
            )
            for (ssid, failure_step), count in failure_counts.items():
                labels = {
                    **base_labels,
                    LabelName.SSID: ssid,
                    LabelName.FAILURE_STEP: failure_step,
                }
                self._set_metric_value(
                    "_ssid_failed_connections",
                    labels,
                    count,
                )

        except Exception as e:
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "SSID failed connections API not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect SSID performance metrics",
                    network_id=network_id,
                    network_name=network_name,
                )
