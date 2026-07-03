"""Per-SSID wireless performance collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.error_handling import validate_response_format
from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from ...core.scheduler import EndpointGroupName
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
    async def _fetch_failed_connections(
        self, network_id: str, org_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch failed wireless connections for a network.

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
            List of failed connection entries grouped by SSID and failure step.

        """
        _ = org_id  # Consumed by the @log_api_call decorator for rate-limit keying.
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessFailedConnections,
            network_id,
            timespan=3600,  # 1 hour
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getNetworkWirelessFailedConnections",
            ),
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
                failed_connections = await self._fetch_failed_connections(network_id, org_id=org_id)

            if not failed_connections:
                return

            # Aggregate failed connections by SSID number and failure step.
            # getNetworkWirelessFailedConnections returns one row per failure EVENT
            # (fields: ssidNumber, vlan, clientMac, serial, radio, failureStep, type,
            # ts) — there is no pre-aggregated `failures` count field in the response
            # (F-159), so each row counts as exactly one failure.
            failure_counts: dict[tuple[str, str], int] = {}
            for entry in failed_connections:
                ssid_raw = entry.get("ssidNumber")
                ssid = str(ssid_raw) if ssid_raw is not None else "unknown"
                failure_step = entry.get("failureStep") or "unknown"
                key = (ssid, failure_step)
                failure_counts[key] = failure_counts.get(key, 0) + 1

            # Set metrics per SSID / failure step combination
            base_labels = create_network_labels(
                network,
                org_id=org_id,
                org_name=org_name,
            )
            # Per-series TTL from the group's solved interval (#617 §1f) — this
            # 3600s-windowed series must not flap under a stretched interval.
            ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_FAILED_CONNECTIONS)
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
                    ttl_seconds=ttl_seconds,
                )

        except Exception as e:
            error_str = str(e)
            if (
                "400" in error_str
                or "404" in error_str
                or "Bad Request" in error_str
                or "rate limit" in error_str.lower()
            ):
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
