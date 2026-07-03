"""Air Marshal rogue AP / SSID-spoofing detection collector.

NOTE (deviation from the original roadmap issue, refreshed for #612): as of
the current cached OpenAPI spec snapshot (``spec/meraki-openapi.json.gz``),
the ``getNetworkWirelessAirMarshal`` response shape still has no
``types``/encryption fields to split out - it only documents ``ssid``,
``bssids`` (each with ``bssid``/``contained``/``detectedBy``), ``channels``,
``firstSeen``, ``lastSeen``, ``wiredMacs``, ``wiredVlans``, and
``wiredLastSeen``. This collector therefore still emits bounded
network-level counts and never labels by SSID/BSSID (both are
attacker-influenced and unbounded).

#612 adds a threat-type breakdown (``MR_AIR_MARSHAL_BSSIDS_BY_THREAT_TYPE_COUNT``)
that reads an entry-level threat/classification field *leniently*: it checks
for ``type``/``threatType`` keys (neither is in the documented schema above)
and buckets any observed value into the bounded label set
``{rogue, spoof, other}`` (unrecognized values -> ``other``). Entries with
neither key present are skipped for this metric only (the four original
bounded counts above are unaffected and still always emitted).

⚠ Phase-6 LIVE VERIFICATION (do before freezing): confirm against a live
homelab MR whether any threat/classification field is actually present on
the wire (it is undocumented in the OpenAPI spec) and, if so, its exact key
name and value vocabulary. If the live response has no such field at all,
the threat-type gauge will always emit all-zero counts and #612 should be
treated as docstring-refresh-only (drop the gauge in a follow-up).
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
from ...core.scheduler import EndpointGroupName
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Bounded label set for the #612 threat-type breakdown. Any recognized wire
# value normalizes to one of these three; unrecognized/absent values that
# nonetheless carry SOME classification map to "other" rather than being
# dropped (only a row with no classification field at all is skipped).
_THREAT_TYPE_VALUES = frozenset({"rogue", "spoof", "other"})


def _normalize_threat_type(raw: Any) -> str:
    """Map a wire threat/classification value to the bounded label set.

    Parameters
    ----------
    raw : Any
        The raw value read from an entry's ``type``/``threatType`` field.

    Returns
    -------
    str
        One of ``"rogue"``, ``"spoof"``, ``"other"``.

    """
    if not isinstance(raw, str):
        return "other"
    normalized = raw.strip().lower()
    if normalized in _THREAT_TYPE_VALUES:
        return normalized
    if "rogue" in normalized:
        return "rogue"
    if "spoof" in normalized:
        return "spoof"
    return "other"


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
        # #612: BSSID counts broken out by threat type (bounded rogue/spoof/other).
        self._air_marshal_bssids_by_threat_type = self.parent._create_gauge(
            NetworkHealthMetricName.MR_AIR_MARSHAL_BSSIDS_BY_THREAT_TYPE_COUNT,
            "Number of Air Marshal BSSIDs observed by threat type, last hour "
            "(rogue/spoof/other; entries without a threat-type field are not counted)",
            labelnames=[*labelnames, LabelName.THREAT_TYPE],
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
        # #612: bucketed by threat type; a row lacking a threat-type field
        # entirely does not contribute to any bucket (lenient skip), but the
        # three buckets are still always emitted below (defaulting to 0).
        threat_type_bssid_counts: dict[str, int] = dict.fromkeys(_THREAT_TYPE_VALUES, 0)

        for entry in entries:
            bssids = entry.get("bssids") or []
            bssids_total += len(bssids)
            contained_bssids_total += sum(1 for b in bssids if b.get("contained") is True)

            if entry.get("wiredMacs"):
                wired_detected_total += 1

            # ⚠ Phase-6: neither key is in the documented OpenAPI schema today
            # (see module docstring) - this is a forward-leaning, lenient read
            # in case a future API/firmware revision adds one of them.
            raw_threat_type = entry.get("type")
            if raw_threat_type is None:
                raw_threat_type = entry.get("threatType")
            if raw_threat_type is None:
                continue
            threat_type = _normalize_threat_type(raw_threat_type)
            threat_type_bssid_counts[threat_type] += len(bssids)

        labels = create_network_labels(network, org_id=org_id, org_name=org_name)
        # Per-series TTL from the group's solved interval (#617 §1f) — this
        # 3600s-windowed series must not flap under a stretched interval.
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_AIR_MARSHAL)

        self.parent._set_metric(
            self._air_marshal_ssids_total,
            labels,
            float(ssids_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_SSIDS_COUNT.value,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._air_marshal_bssids_total,
            labels,
            float(bssids_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_BSSIDS_COUNT.value,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._air_marshal_contained_bssids_total,
            labels,
            float(contained_bssids_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_CONTAINED_BSSIDS_COUNT.value,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._air_marshal_wired_detected_total,
            labels,
            float(wired_detected_total),
            NetworkHealthMetricName.MR_AIR_MARSHAL_WIRED_DETECTED_COUNT.value,
            ttl_seconds=ttl_seconds,
        )
        # #612: always emit all three bounded buckets (defaulting to 0) so the
        # series doesn't flap in/out of existence as threat types come and go.
        for threat_type, count in threat_type_bssid_counts.items():
            self.parent._set_metric(
                self._air_marshal_bssids_by_threat_type,
                {**labels, LabelName.THREAT_TYPE: threat_type},
                float(count),
                NetworkHealthMetricName.MR_AIR_MARSHAL_BSSIDS_BY_THREAT_TYPE_COUNT.value,
                ttl_seconds=ttl_seconds,
            )
