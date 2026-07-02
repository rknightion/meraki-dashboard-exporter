"""Air Marshal rogue AP / SSID-spoofing detection collector.

NOTE (deviation from the original roadmap issue): the actual
getNetworkWirelessAirMarshal response shape has no ``types``/encryption
fields to split out - it only has ``ssid``, ``bssids`` (each with
``bssid``/``contained``/``detectedBy``), ``channels``, ``firstSeen``,
``lastSeen``, ``wiredMacs``, ``wiredVlans``, and ``wiredLastSeen``. This
collector therefore emits only bounded network-level counts and never
labels by SSID/BSSID (both are attacker-influenced and unbounded).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import NetworkHealthMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AirMarshalCollector(BaseNetworkHealthCollector):
    """Collector for Air Marshal rogue AP / SSID-spoofing detection counts.

    Collects bounded network-level counts (foreign SSID entries observed,
    total BSSIDs across those entries, contained BSSIDs, and entries with a
    wired detection) via getNetworkWirelessAirMarshal.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize the Air Marshal collector.

        Parameters
        ----------
        parent : Any
            Parent NetworkHealthCollector instance that exposes
            ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        super().__init__(parent)
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize Air Marshal Prometheus gauge metrics."""
        labelnames = [
            LabelName.ORG_ID,
            LabelName.NETWORK_ID,
        ]
        self._air_marshal_ssids_total = self.parent._create_gauge(
            NetworkHealthMetricName.MR_AIR_MARSHAL_SSIDS_COUNT,
            "Number of foreign SSID entries observed by Air Marshal over the last hour",
            labelnames=labelnames,
        )
        self._air_marshal_bssids_total = self.parent._create_gauge(
            NetworkHealthMetricName.MR_AIR_MARSHAL_BSSIDS_COUNT,
            "Total number of BSSIDs across all Air Marshal SSID entries, last hour",
            labelnames=labelnames,
        )
        self._air_marshal_contained_bssids_total = self.parent._create_gauge(
            NetworkHealthMetricName.MR_AIR_MARSHAL_CONTAINED_BSSIDS_COUNT,
            "Number of Air Marshal BSSIDs currently contained, last hour",
            labelnames=labelnames,
        )
        self._air_marshal_wired_detected_total = self.parent._create_gauge(
            NetworkHealthMetricName.MR_AIR_MARSHAL_WIRED_DETECTED_COUNT,
            "Number of Air Marshal SSID entries also detected on the wired network, last hour",
            labelnames=labelnames,
        )

    @log_api_call("getNetworkWirelessAirMarshal")
    @with_error_handling(
        operation="Collect Air Marshal rogue AP detection",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_air_marshal(self, network_id: str) -> list[dict[str, Any]] | None:
        """Fetch Air Marshal entries for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of Air Marshal SSID entries, or None on error (handled by
            the error decorator).

        """
        response = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessAirMarshal,
            network_id,
            timespan=3600,
        )
        result: list[dict[str, Any]] = validate_response_format(
            response,
            expected_type=list,
            operation="getNetworkWirelessAirMarshal",
        )
        return result

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect Air Marshal rogue AP detection counts for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data including id, name, orgId, and orgName. Already
            NetworkFilter-filtered by the coordinator.

        """
        network_id = network["id"]
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        entries = await self._fetch_air_marshal(network_id)
        if entries is None:
            return

        ssids_total = len(entries)
        bssids_total = 0
        contained_bssids_total = 0
        wired_detected_total = 0

        for entry in entries:
            bssids = entry.get("bssids") or []
            bssids_total += len(bssids)
            contained_bssids_total += sum(1 for b in bssids if b.get("contained") is True)

            if entry.get("wiredMacs"):
                wired_detected_total += 1

        labels = create_network_labels(network, org_id=org_id, org_name=org_name)

        self.parent._set_metric(
            self._air_marshal_ssids_total,
            labels,
            float(ssids_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_SSIDS_COUNT.value,
        )
        self.parent._set_metric(
            self._air_marshal_bssids_total,
            labels,
            float(bssids_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_BSSIDS_COUNT.value,
        )
        self.parent._set_metric(
            self._air_marshal_contained_bssids_total,
            labels,
            float(contained_bssids_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_CONTAINED_BSSIDS_COUNT.value,
        )
        self.parent._set_metric(
            self._air_marshal_wired_detected_total,
            labels,
            float(wired_detected_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_WIRED_DETECTED_COUNT.value,
        )
