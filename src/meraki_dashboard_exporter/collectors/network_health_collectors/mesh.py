"""Wireless mesh link health collector for MR repeater access points (#307).

Repeater APs relay traffic to a "gateway" AP over a wireless mesh link;
``getNetworkWirelessMeshStatuses`` reports the current link quality per
repeater. The overwhelming majority of networks have no mesh topology at
all (no repeater APs configured) - for those, the endpoint returns an empty
list or a 400/404. Both cases are logged at debug and are NOT collection
failures, mirroring ``bluetooth.py``'s not-available handling (see
``network_health_collectors/CLAUDE.md`` - "error handling is not uniform").

⚠ Phase-6 LIVE VERIFICATION (do before freezing): the response shape here is
coded against the OpenAPI spec (array of ``{serial, meshRoute:[serial,...],
latestMeshPerformance:{mbps, metric, usagePercentage}}``). Unverified on the
wire:
- whether ``usagePercentage`` is really a percent-suffixed string (``"100%"``)
  as the spec example shows, or a bare number on some firmware - this
  collector parses both leniently;
- whether ``mbps``/``metric`` can be null/absent on a freshly-joined repeater
  (handled leniently - a missing sub-field just skips that one series).
No repeater APs exist in the homelab reference environment, so this
collector is expected to stay spec-only (no emitted series) until a real
mesh deployment is available to verify against.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import NetworkHealthMetricName
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


class MeshCollector(BaseNetworkHealthCollector):
    """Collector for wireless mesh link health (repeater APs) - #307.

    Collects per-repeater-AP mesh throughput, route-quality metric, and link
    utilization percentage via ``getNetworkWirelessMeshStatuses``. Absent on
    any network with no repeaters configured (the common case).
    """

    def __init__(self, parent: Any) -> None:
        """Initialize the mesh collector.

        Parameters
        ----------
        parent : Any
            Parent NetworkHealthCollector instance that exposes
            ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        super().__init__(parent)
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize wireless mesh Prometheus gauge metrics."""
        labelnames = [
            LabelName.ORG_ID,
            LabelName.NETWORK_ID,
            LabelName.SERIAL,
        ]
        self._mesh_throughput_bps = self.parent._create_gauge(
            NetworkHealthMetricName.MR_MESH_THROUGHPUT_BYTES_PER_SECOND,
            "Wireless mesh repeater link throughput in bytes per second (API Mbps x1e6/8)",
            labelnames=labelnames,
        )
        self._mesh_route_metric = self.parent._create_gauge(
            NetworkHealthMetricName.MR_MESH_ROUTE_METRIC,
            "Wireless mesh route quality metric from repeater to gateway AP, "
            "unitless, lower is better",
            labelnames=labelnames,
        )
        self._mesh_usage_percent = self.parent._create_gauge(
            NetworkHealthMetricName.MR_MESH_USAGE_PERCENT,
            "Wireless mesh link utilization percentage (0-100)",
            labelnames=labelnames,
        )

    @log_api_call("getNetworkWirelessMeshStatuses")
    async def _fetch_mesh_statuses(self, network_id: str) -> list[dict[str, Any]]:
        """Fetch wireless mesh statuses for repeaters in a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]]
            List of per-repeater mesh status entries (empty on networks with
            no repeaters).

        """
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessMeshStatuses,
            network_id,
            total_pages="all",
        )
        result: list[dict[str, Any]] = validate_response_format(
            response,
            expected_type=list,
            operation="getNetworkWirelessMeshStatuses",
        )
        return result

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect wireless mesh link health for a network's repeater APs.

        Parameters
        ----------
        network : dict[str, Any]
            Network data including id, name, orgId, and orgName. Already
            NetworkFilter-filtered by the coordinator.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        try:
            with LogContext(network_id=network_id, network_name=network_name, org_id=org_id):
                entries = await self._fetch_mesh_statuses(network_id)
        except Exception as e:
            # Log at debug level if it's just not available (400/404 - the
            # network has no repeaters, by far the common case) or the API
            # exhausted retries on a rate limit. Deliberately do NOT emit any
            # value here - absence of mesh data is the expected steady state.
            error_str = str(e)
            if (
                "400" in error_str
                or "404" in error_str
                or "Bad Request" in error_str
                or "rate limit" in error_str.lower()
            ):
                logger.debug(
                    "Wireless mesh statuses API not available (no repeaters on this network)",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect wireless mesh statuses",
                    network_id=network_id,
                    network_name=network_name,
                )
            return

        if not entries:
            return

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_MESH)
        base_labels = create_network_labels(network, org_id=org_id, org_name=org_name)

        for entry in entries:
            serial = entry.get("serial")
            if not serial:
                # Lenient: a row without a serial can't be labeled - skip it.
                continue

            perf = entry.get("latestMeshPerformance") or {}
            labels = {**base_labels, LabelName.SERIAL: serial}

            mbps_value = self._parse_float(perf.get("mbps"))
            if mbps_value is not None:
                self.parent._set_metric(
                    self._mesh_throughput_bps,
                    labels,
                    mbps_value * 1_000_000 / 8,
                    NetworkHealthMetricName.MR_MESH_THROUGHPUT_BYTES_PER_SECOND.value,
                    ttl_seconds=ttl_seconds,
                )

            metric_value = self._parse_float(perf.get("metric"))
            if metric_value is not None:
                self.parent._set_metric(
                    self._mesh_route_metric,
                    labels,
                    metric_value,
                    NetworkHealthMetricName.MR_MESH_ROUTE_METRIC.value,
                    ttl_seconds=ttl_seconds,
                )

            usage_value = self._parse_usage_percentage(perf.get("usagePercentage"))
            if usage_value is not None:
                self.parent._set_metric(
                    self._mesh_usage_percent,
                    labels,
                    usage_value,
                    NetworkHealthMetricName.MR_MESH_USAGE_PERCENT.value,
                    ttl_seconds=ttl_seconds,
                )

    @staticmethod
    def _parse_float(raw: Any) -> float | None:
        """Parse a numeric field leniently, returning None if absent/invalid."""
        if raw is None:
            return None
        try:
            return float(raw)
        except TypeError, ValueError:
            return None

    @staticmethod
    def _parse_usage_percentage(raw: Any) -> float | None:
        """Parse ``usagePercentage`` leniently.

        The OpenAPI spec documents this field as a percent-suffixed string
        (e.g. ``"100%"``), but some firmware/API versions may return a bare
        number - handle both (#307 ⚠ Phase-6).
        """
        if raw is None:
            return None
        if isinstance(raw, int | float):
            return float(raw)
        if isinstance(raw, str):
            cleaned = raw.strip().rstrip("%").strip()
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
