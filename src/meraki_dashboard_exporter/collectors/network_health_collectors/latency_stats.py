"""MR wireless latency stats collector (per-device and network client aggregate)."""

from __future__ import annotations

import asyncio
from statistics import mean
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import NetworkHealthMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ...core.scheduler import EndpointGroupName
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Maps the traffic_class label value to the corresponding key in the API's
# latencyStats object.
_TRAFFIC_CLASS_KEYS: dict[str, str] = {
    "background": "backgroundTraffic",
    "best_effort": "bestEffortTraffic",
    "video": "videoTraffic",
    "voice": "voiceTraffic",
}


class LatencyStatsCollector(BaseNetworkHealthCollector):
    """Collector for MR wireless latency statistics.

    Collects per-AP average wireless latency (by traffic class) via
    getNetworkWirelessDevicesLatencyStats, and a network-wide client latency
    aggregate (mean of per-client averages, by traffic class) via
    getNetworkWirelessClientsLatencyStats. Per-client rows are never labeled
    individually (unbounded cardinality) - only the network-wide mean is
    emitted.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize the latency stats collector.

        Parameters
        ----------
        parent : Any
            Parent NetworkHealthCollector instance that exposes
            ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        super().__init__(parent)
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize latency stats Prometheus gauge metrics."""
        self._mr_device_latency_ms = self.parent._create_gauge(
            NetworkHealthMetricName.MR_DEVICE_LATENCY_SECONDS,
            "MR access point average wireless latency in seconds by traffic class, 1-h window",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.TRAFFIC_CLASS,
            ],
        )
        self._mr_network_client_latency_ms = self.parent._create_gauge(
            NetworkHealthMetricName.MR_NETWORK_CLIENT_LATENCY_SECONDS,
            "Network-wide average wireless client latency in seconds by traffic class, 1-h window",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.TRAFFIC_CLASS,
            ],
        )

    @log_api_call("getNetworkWirelessDevicesLatencyStats")
    @with_error_handling(
        operation="Collect MR wireless devices latency stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_device_latency_stats(self, network_id: str) -> list[dict[str, Any]] | None:
        """Fetch per-device (AP) wireless latency stats for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of per-device latency stat entries, or None on error
            (handled by the error decorator).

        """
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessDevicesLatencyStats,
            network_id,
            timespan=3600,
            fields="avg",
        )
        result: list[dict[str, Any]] = validate_response_format(
            response,
            expected_type=list,
            operation="getNetworkWirelessDevicesLatencyStats",
        )
        return result

    @log_api_call("getNetworkWirelessClientsLatencyStats")
    @with_error_handling(
        operation="Collect MR wireless clients latency stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_client_latency_stats(self, network_id: str) -> list[dict[str, Any]] | None:
        """Fetch per-client wireless latency stats for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of per-client latency stat entries, or None on error
            (handled by the error decorator).

        """
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessClientsLatencyStats,
            network_id,
            timespan=3600,
            fields="avg",
        )
        result: list[dict[str, Any]] = validate_response_format(
            response,
            expected_type=list,
            operation="getNetworkWirelessClientsLatencyStats",
        )
        return result

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect wireless latency stats for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data including id, name, orgId, and orgName. Already
            NetworkFilter-filtered by the coordinator.

        """
        network_id = network["id"]
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        base_labels = create_network_labels(network, org_id=org_id, org_name=org_name)
        # Per-series TTL from the group's solved interval (#617 §1f) — this
        # 3600s-windowed series must not flap under a stretched interval.
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_LATENCY_STATS)

        device_rows = await self._fetch_device_latency_stats(network_id)
        if device_rows:
            for row in device_rows:
                serial = row.get("serial", "")
                latency_stats = row.get("latencyStats") or {}
                device_labels_base = {**base_labels, LabelName.SERIAL: serial}

                for traffic_class, api_key in _TRAFFIC_CLASS_KEYS.items():
                    avg = (latency_stats.get(api_key) or {}).get("avg")
                    if avg is None:
                        continue

                    labels = {**device_labels_base, LabelName.TRAFFIC_CLASS: traffic_class}
                    # API reports latency in milliseconds; convert to seconds (#531).
                    self.parent._set_metric(
                        self._mr_device_latency_ms,
                        labels,
                        float(avg) / 1000,
                        NetworkHealthMetricName.MR_DEVICE_LATENCY_SECONDS.value,
                        ttl_seconds=ttl_seconds,
                    )

        client_rows = await self._fetch_client_latency_stats(network_id)
        if client_rows:
            per_class_values: dict[str, list[float]] = {tc: [] for tc in _TRAFFIC_CLASS_KEYS}

            for row in client_rows:
                latency_stats = row.get("latencyStats") or {}
                for traffic_class, api_key in _TRAFFIC_CLASS_KEYS.items():
                    avg = (latency_stats.get(api_key) or {}).get("avg")
                    if avg is None:
                        continue
                    per_class_values[traffic_class].append(float(avg))

            for traffic_class, values in per_class_values.items():
                if not values:
                    continue

                labels = {**base_labels, LabelName.TRAFFIC_CLASS: traffic_class}
                # API reports latency in milliseconds; convert to seconds (#531).
                self.parent._set_metric(
                    self._mr_network_client_latency_ms,
                    labels,
                    mean(values) / 1000,
                    NetworkHealthMetricName.MR_NETWORK_CLIENT_LATENCY_SECONDS.value,
                    ttl_seconds=ttl_seconds,
                )
