"""Meraki MS (Switch) metrics collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ...core.async_utils import ManagedTaskGroup
from ...core.constants import MSMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels, create_port_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName, create_labels
from ...core.otel_tracing import trace_method
from ...core.scheduler import EndpointGroupName
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Label ordering for the STP-state and 802.1X-status gauges, matching the
# ``labelnames=[...]`` order declared in ``_initialize_metrics``. Used to build
# positional ``.remove()`` calls when clearing stale label-transition series
# (see F-070: label-valued state series must not linger past a transition).
_STP_STATE_LABEL_ORDER = (
    LabelName.ORG_ID,
    LabelName.NETWORK_ID,
    LabelName.SERIAL,
    LabelName.MODEL,
    LabelName.DEVICE_TYPE,
    LabelName.PORT_ID,
    LabelName.STATE,
)

_8021X_STATUS_LABEL_ORDER = (
    LabelName.ORG_ID,
    LabelName.NETWORK_ID,
    LabelName.SERIAL,
    LabelName.MODEL,
    LabelName.DEVICE_TYPE,
    LabelName.PORT_ID,
    LabelName.STATUS,
)


class MSCollector(BaseDeviceCollector):
    """Collector for Meraki MS (Switch) devices."""

    def __init__(self, parent: Any) -> None:
        """Initialize the MS collector.

        Parameters
        ----------
        parent : Any
            Parent collector providing shared metrics and helpers.

        """
        super().__init__(parent)
        self._last_port_usage: dict[str, float] = {}
        self._last_packet_stats: dict[str, float] = {}
        self._org_port_status_supported: bool | None = None
        # Cached probe for the org-wide port usage/PoE endpoints (F-168).
        self._org_port_usage_supported: bool | None = None
        # Tracks which device serials were seen during the current collection cycle
        self._active_serials: set[str] = set()
        # Tracks the last emitted STP state(s) / 802.1X status(es) per
        # (serial, port_id) so a transition can remove the now-stale label
        # series instead of relying on TTL expiration (see F-070).
        self._emitted_stp_states: dict[tuple[str, str], set[str]] = {}
        self._emitted_8021x_statuses: dict[tuple[str, str], set[str]] = {}
        # Timestamp of the last successful STP priority collection, used to
        # gate collect_stp_priorities to the SLOW cadence even though it is
        # invoked from the MEDIUM-tier DeviceCollector cycle (see F-037).
        self._last_stp_collection: float = 0.0
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize MS-specific metrics."""
        # Switch port metrics
        self._switch_port_status = self.parent._create_gauge(
            MSMetricName.MS_PORT_STATUS,
            "Switch port status (1 = connected, 0 = disconnected)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.LINK_SPEED,
                LabelName.DUPLEX,
            ],
        )

        self._switch_port_traffic = self.parent._create_gauge(
            MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND,
            "Switch port traffic rate in bytes per second (averaged over 1 hour)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.DIRECTION,
            ],
        )

        self._switch_port_usage = self.parent._create_gauge(
            MSMetricName.MS_PORT_USAGE_BYTES,
            "Switch port data usage in bytes (decimal KB x1000) over the last 1 hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.DIRECTION,
            ],
        )

        self._switch_port_client_count = self.parent._create_gauge(
            MSMetricName.MS_PORT_CLIENT_COUNT,
            "Number of clients connected to switch port",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
            ],
        )

        self._switch_port_errors = self.parent._create_gauge(
            MSMetricName.MS_PORT_ERROR_ACTIVE,
            "Active switch port errors (1 = currently active for this error_type)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.ERROR_TYPE,
            ],
        )

        self._switch_port_warnings = self.parent._create_gauge(
            MSMetricName.MS_PORT_WARNING_ACTIVE,
            "Active switch port warnings (1 = currently active for this warning_type)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.WARNING_TYPE,
            ],
        )

        # Switch power metrics
        self._switch_power = self.parent._create_gauge(
            MSMetricName.MS_POWER_USAGE_WATTS,
            "Switch power usage in watts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # POE metrics
        self._switch_poe_port_power = self.parent._create_gauge(
            MSMetricName.MS_POE_PORT_ENERGY_JOULES,
            "Per-port POE energy consumption in joules over the last 1 hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
            ],
        )

        self._switch_poe_total_power = self.parent._create_gauge(
            MSMetricName.MS_POE_TOTAL_ENERGY_JOULES,
            "Total POE energy consumption for switch in joules",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._switch_poe_budget = self.parent._create_gauge(
            MSMetricName.MS_POE_BUDGET_WATTS,
            "Total POE power budget for switch in watts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._switch_poe_network_total = self.parent._create_gauge(
            MSMetricName.MS_POE_NETWORK_TOTAL_ENERGY_JOULES,
            "Total POE energy consumption for all switches in network in joules",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        # STP metrics
        self._switch_stp_priority = self.parent._create_gauge(
            MSMetricName.MS_STP_PRIORITY,
            "Switch STP (Spanning Tree Protocol) priority",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # Per-port STP state (from the port status payload's spanningTree.statuses)
        self._switch_port_stp_state = self.parent._create_gauge(
            MSMetricName.MS_PORT_STP_STATE,
            "Switch port STP state (1 = currently active for this state)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.STATE,
            ],
        )

        # Per-port 802.1X / secure-port authentication (from the port status
        # payload's securePort object)
        self._switch_port_8021x_status = self.parent._create_gauge(
            MSMetricName.MS_PORT_8021X_STATUS,
            "Switch port 802.1X authentication status (1 = currently active for this status)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.STATUS,
            ],
        )

        self._switch_port_8021x_active = self.parent._create_gauge(
            MSMetricName.MS_PORT_8021X_ACTIVE,
            "Switch port secure-port (802.1X) active state (1 = active, 0 = inactive)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
            ],
        )

        # Port info join metric (#534): carries the mutable ``port_name`` keyed
        # on the stable (serial, port_id) so numeric per-port series stay id-only.
        # Join via: <numeric> * on(serial, port_id) group_left(port_name)
        #           meraki_ms_port_info
        self._ms_port_info = self.parent._create_gauge(
            MSMetricName.MS_PORT_INFO,
            "Switch port info (value 1); join port_name via on(serial, port_id)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
            ],
        )

        # Packet count metrics (5-minute window)
        packet_labels = [
            LabelName.ORG_ID.value,
            LabelName.NETWORK_ID.value,
            LabelName.SERIAL.value,
            LabelName.MODEL.value,
            LabelName.DEVICE_TYPE.value,
            LabelName.PORT_ID.value,
            LabelName.DIRECTION.value,
        ]

        self._switch_port_packets_total = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_COUNT,
            "Total packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_broadcast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_BROADCAST_COUNT,
            "Broadcast packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_multicast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_MULTICAST_COUNT,
            "Multicast packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_crcerrors = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_CRCERRORS_COUNT,
            "CRC align error packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_fragments = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_FRAGMENTS_COUNT,
            "Fragment packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_collisions = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_COLLISIONS_COUNT,
            "Collision packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_topologychanges = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_TOPOLOGYCHANGES_COUNT,
            "Topology change packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )

        # Packet rate metrics (packets per second)
        self._switch_port_packets_rate_total = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE,
            "Total packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_rate_broadcast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_BROADCAST,
            "Broadcast packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_rate_multicast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_MULTICAST,
            "Multicast packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_rate_crcerrors = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_CRCERRORS,
            "CRC align error packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_rate_fragments = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_FRAGMENTS,
            "Fragment packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_rate_collisions = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_COLLISIONS,
            "Collision packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        self._switch_port_packets_rate_topologychanges = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_TOPOLOGYCHANGES,
            "Topology change packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

        # Port overview metrics (org-level aggregates)
        self._ms_ports_active_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_ACTIVE,
            "Number of active switch ports",
            labelnames=[
                LabelName.ORG_ID,
            ],
        )

        self._ms_ports_inactive_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_INACTIVE,
            "Number of inactive switch ports",
            labelnames=[
                LabelName.ORG_ID,
            ],
        )

        self._ms_ports_by_media_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_BY_MEDIA,
            "Number of switch ports by media type",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.MEDIA,
                LabelName.STATUS,  # active or inactive
            ],
        )

        self._ms_ports_by_link_speed_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_BY_LINK_SPEED,
            "Number of active switch ports by link speed",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.MEDIA,
                LabelName.LINK_SPEED,  # speed in Mbps
            ],
        )

        # Rogue/unauthorized DHCP servers seen (#292). Windowed (1-day, API
        # default timespan) count that resets every collection cycle - both
        # is_allowed label values are always emitted (0 when none seen) so the
        # absence of rogue servers is an explicit, observable state rather
        # than a missing series.
        self._ms_dhcp_servers_seen = self.parent._create_gauge(
            MSMetricName.MS_DHCP_SERVERS_SEEN_COUNT,
            "Number of DHCPv4 servers seen on the network by allow-list status "
            "(1-day window, resets each collection cycle)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.IS_ALLOWED,
            ],
        )

        # Dynamic ARP Inspection coverage (#293). Rows carry serial, not
        # model/device_type (the source endpoint doesn't return a model).
        self._ms_dai_supported = self.parent._create_gauge(
            MSMetricName.MS_DAI_SUPPORTED,
            "Switch supports Dynamic ARP Inspection (1 = supported, 0 = not supported)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
            ],
        )

        self._ms_dai_trusted_port = self.parent._create_gauge(
            MSMetricName.MS_DAI_TRUSTED_PORT_CONFIGURED,
            "Switch has at least one Dynamic ARP Inspection trusted port configured "
            "(1 = configured, 0 = not configured)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
            ],
        )

        # Org-wide PoE draw (#294), sourced from a bucketed history endpoint -
        # the most recent bucket lags real-time by roughly the bucket width
        # (~20 minutes).
        self._ms_org_poe_draw_watts = self.parent._create_gauge(
            MSMetricName.MS_ORG_POE_DRAW_WATTS,
            "Organization-wide switch PoE power draw in watts (most recent history "
            "bucket; lags real-time by ~20 minutes)",
            labelnames=[
                LabelName.ORG_ID,
            ],
        )

        # Link aggregation (LACP) groups + membership (#295).
        self._ms_link_aggregations = self.parent._create_gauge(
            MSMetricName.MS_LINK_AGGREGATIONS,
            "Number of link aggregation (LACP) groups configured in the network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        self._ms_link_aggregation_member = self.parent._create_gauge(
            MSMetricName.MS_LINK_AGGREGATION_MEMBER,
            "Switch port is a member of a link aggregation group (value 1)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.LAG_ID,
                LabelName.SERIAL,
                LabelName.PORT_ID,
            ],
        )

        # CDP/LLDP neighbor presence (#296) - reuses the cdp/lldp objects
        # already present in the port-status payload, no additional API call.
        self._switch_port_neighbor_present = self.parent._create_gauge(
            MSMetricName.MS_PORT_NEIGHBOR_PRESENT,
            "Switch port has an advertised CDP/LLDP neighbor this cycle (value 1; "
            "series absent when no neighbor is advertised via this protocol)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.TYPE,
            ],
        )

    def _evict_stale_serials(self, active_serials: set[str]) -> None:
        """Remove timestamp cache entries for serials not seen this collection cycle.

        Parameters
        ----------
        active_serials : set[str]
            Device serials that were processed during the current cycle.
            Entries for serials absent from this set are evicted from both
            ``_last_port_usage`` and ``_last_packet_stats``.

        """
        stale = (set(self._last_port_usage) | set(self._last_packet_stats)) - active_serials
        for serial in stale:
            self._last_port_usage.pop(serial, None)
            self._last_packet_stats.pop(serial, None)
        if stale:
            logger.debug(
                "Evicted stale MS collector serial cache entries",
                evicted_count=len(stale),
                remaining_port_usage=len(self._last_port_usage),
                remaining_packet_stats=len(self._last_packet_stats),
            )

    def _should_collect_port_usage(self, serial: str) -> bool:
        # Interval sourced from the scheduler's solved MS_PORT_USAGE interval
        # (#617): floor 600s, stretchable, pinnable via ms_port_usage_interval.
        interval: float = self.parent._group_interval(EndpointGroupName.MS_PORT_USAGE)
        if interval <= 0:
            return True
        last = self._last_port_usage.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_port_usage_collected(self, serial: str) -> None:
        self._last_port_usage[serial] = time.time()

    def _should_collect_packet_stats(self, serial: str) -> bool:
        # Interval sourced from the scheduler's solved MS_PACKET_STATS interval
        # (#617): floor 600s, stretchable, pinnable via ms_packet_stats_interval.
        interval: float = self.parent._group_interval(EndpointGroupName.MS_PACKET_STATS)
        if interval <= 0:
            return True
        last = self._last_packet_stats.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_packet_stats_collected(self, serial: str) -> None:
        self._last_packet_stats[serial] = time.time()

    def _emit_port_info(
        self,
        device: dict[str, Any],
        port: dict[str, Any],
        org_id: str,
        ttl_seconds: float | None = None,
    ) -> None:
        """Emit the ``meraki_ms_port_info`` join series for a port (#534).

        Carries the mutable ``port_name`` keyed on the stable
        ``(serial, port_id)`` so the numeric per-port series can stay id-only.
        The port name is already in hand at every emission site (no extra API
        call). Emitted via ``parent._set_metric`` so the series expires when a
        port disappears (DeviceCollector expiration bucket).

        Parameters
        ----------
        device : dict[str, Any]
            Device (or device-like) data used for id label construction.
        port : dict[str, Any]
            Port status data from the API (source of ``portId``/``name``).
        org_id : str
            Organization ID.
        ttl_seconds : float | None
            Per-series TTL for the MS_PORT_STATUS group (#617), forwarded to
            ``_set_metric``. ``None`` ⇒ tier-derived TTL.

        """
        port_id = str(port.get("portId", ""))
        port_name = port.get("name", f"Port {port_id}")
        info_labels = create_labels(
            org_id=org_id,
            network_id=device.get("networkId", ""),
            serial=device.get("serial", ""),
            port_id=port_id,
            port_name=port_name,
        )
        self.parent._set_metric(
            self._ms_port_info,
            info_labels,
            1,
            MSMetricName.MS_PORT_INFO.value,
            ttl_seconds=ttl_seconds,
        )

    def _emit_port_error_warning_metrics(
        self,
        device: dict[str, Any],
        port: dict[str, Any],
        org_id: str,
        org_name: str,
        ttl_seconds: float | None = None,
    ) -> None:
        """Emit gauges for a port's currently active errors/warnings.

        Only strings present in the port's ``errors``/``warnings`` arrays *this*
        collection cycle are emitted (value 1). Emission goes through
        ``parent._set_metric`` (not ``.labels().set()``) so that an error/warning
        which clears (i.e. stops appearing in the API response) expires
        automatically via the metric expiration manager instead of leaving a
        stale series behind. Ports with no errors/warnings emit nothing.

        Parameters
        ----------
        device : dict[str, Any]
            Device (or device-like) data used for label construction.
        port : dict[str, Any]
            Port status data from the API, potentially containing ``errors``
            and ``warnings`` string arrays.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        ttl_seconds : float | None
            Per-series TTL for the MS_PORT_STATUS group (#617), forwarded to
            ``_set_metric``. ``None`` ⇒ tier-derived TTL.

        """
        for error_type in port.get("errors") or []:
            error_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, error_type=error_type
            )
            self.parent._set_metric(
                self._switch_port_errors,
                error_labels,
                1,
                MSMetricName.MS_PORT_ERROR_ACTIVE.value,
                ttl_seconds=ttl_seconds,
            )

        for warning_type in port.get("warnings") or []:
            warning_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, warning_type=warning_type
            )
            self.parent._set_metric(
                self._switch_port_warnings,
                warning_labels,
                1,
                MSMetricName.MS_PORT_WARNING_ACTIVE.value,
                ttl_seconds=ttl_seconds,
            )

    def _remove_stale_label_series(
        self,
        gauge: Any,
        labels: dict[str, str],
        label_order: tuple[LabelName, ...],
    ) -> None:
        """Remove a single stale label-valued series, tolerating absence.

        Parameters
        ----------
        gauge : Any
            The Gauge metric to remove a child series from.
        labels : dict[str, str]
            Full label dict (as returned by ``create_port_labels``) for the
            stale series to remove.
        label_order : tuple[LabelName, ...]
            The exact order the gauge's ``labelnames`` were declared in -
            ``Gauge.remove`` takes positional values in that order.

        """
        try:
            gauge.remove(*[labels[name.value] for name in label_order])
        except KeyError:
            pass  # Series doesn't exist (already removed or never emitted)

    def _emit_port_stp_8021x_metrics(
        self,
        device: dict[str, Any],
        port: dict[str, Any],
        org_id: str,
        org_name: str,
        ttl_seconds: float | None = None,
    ) -> None:
        """Emit gauges for a port's STP state and 802.1X/secure-port auth status.

        Extracted from the same port-status payload already processed by
        ``_emit_port_error_warning_metrics`` - no additional API call. Emission
        goes through ``parent._set_metric`` so that a state/status which stops
        appearing in the API response also expires eventually via TTL as a
        backstop. In addition, any state/status previously emitted for this
        exact port that is NOT part of the current cycle's set is explicitly
        removed here so a transition (e.g. Forwarding -> Blocking) doesn't
        leave two mutually-exclusive series both reporting 1 for the 600-900s
        TTL window (see F-070). Ports with no ``spanningTree``/``securePort``
        data emit nothing (and any previously-emitted series for that port
        are cleared).

        Parameters
        ----------
        device : dict[str, Any]
            Device (or device-like) data used for label construction.
        port : dict[str, Any]
            Port status data from the API, potentially containing
            ``spanningTree`` and ``securePort`` objects.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        ttl_seconds : float | None
            Per-series TTL for the MS_PORT_STATUS group (#617), forwarded to
            ``_set_metric``. ``None`` ⇒ tier-derived TTL.

        """
        serial = device.get("serial", "")
        port_id = str(port.get("portId", ""))
        port_key = (serial, port_id)

        spanning = port.get("spanningTree") or {}
        statuses = spanning.get("statuses") or []
        current_states: set[str] = set(statuses)
        for state in statuses:
            stp_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, state=state
            )
            self.parent._set_metric(
                self._switch_port_stp_state,
                stp_labels,
                1,
                MSMetricName.MS_PORT_STP_STATE.value,
                ttl_seconds=ttl_seconds,
            )

        previous_states = self._emitted_stp_states.get(port_key, set())
        for stale_state in previous_states - current_states:
            stale_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, state=stale_state
            )
            self._remove_stale_label_series(
                self._switch_port_stp_state, stale_labels, _STP_STATE_LABEL_ORDER
            )

        if current_states:
            self._emitted_stp_states[port_key] = current_states
        else:
            self._emitted_stp_states.pop(port_key, None)

        secure = port.get("securePort") or {}
        if not secure:
            # No secure-port data this cycle: clear any previously-emitted
            # 802.1X status series for this port too.
            previous_statuses = self._emitted_8021x_statuses.pop(port_key, set())
            for stale_status in previous_statuses:
                stale_labels = create_port_labels(
                    device, port, org_id=org_id, org_name=org_name, status=stale_status
                )
                self._remove_stale_label_series(
                    self._switch_port_8021x_status, stale_labels, _8021X_STATUS_LABEL_ORDER
                )
            return

        active = secure.get("active", False)
        active_labels = create_port_labels(device, port, org_id=org_id, org_name=org_name)
        self.parent._set_metric(
            self._switch_port_8021x_active,
            active_labels,
            1 if active else 0,
            MSMetricName.MS_PORT_8021X_ACTIVE.value,
            ttl_seconds=ttl_seconds,
        )

        auth = secure.get("authenticationStatus")
        current_statuses: set[str] = {auth} if auth else set()
        if auth:
            status_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, status=auth
            )
            self.parent._set_metric(
                self._switch_port_8021x_status,
                status_labels,
                1,
                MSMetricName.MS_PORT_8021X_STATUS.value,
                ttl_seconds=ttl_seconds,
            )

        previous_statuses = self._emitted_8021x_statuses.get(port_key, set())
        for stale_status in previous_statuses - current_statuses:
            stale_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, status=stale_status
            )
            self._remove_stale_label_series(
                self._switch_port_8021x_status, stale_labels, _8021X_STATUS_LABEL_ORDER
            )

        if current_statuses:
            self._emitted_8021x_statuses[port_key] = current_statuses
        else:
            self._emitted_8021x_statuses.pop(port_key, None)

    def _emit_port_neighbor_metrics(
        self,
        device: dict[str, Any],
        port: dict[str, Any],
        org_id: str,
        org_name: str,
        ttl_seconds: float | None = None,
    ) -> None:
        """Emit CDP/LLDP neighbor-presence flags for a port (#296).

        Reuses the ``cdp``/``lldp`` objects already present in the port-status
        payload (both the org-wide ``getOrganizationSwitchPortsStatusesBySwitch``
        and per-device ``getDeviceSwitchPortsStatuses`` responses share this
        shape) - no additional API call. Only *presence* of a neighbor
        advertisement is emitted (value 1); the remote system name/platform
        strings inside the cdp/lldp objects are deliberately NOT emitted
        (attacker-influenced free text - cardinality/injection risk). Absence
        is conveyed by the series not being (re-)set this cycle - mirrors
        ``MS_PORT_ERROR_ACTIVE``: no explicit zero or removal, TTL expiration
        is the sole backstop once a neighbor stops being advertised.

        Parameters
        ----------
        device : dict[str, Any]
            Device (or device-like) data used for label construction.
        port : dict[str, Any]
            Port status data from the API, potentially containing ``cdp``
            and/or ``lldp`` objects.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        ttl_seconds : float | None
            Per-series TTL for the MS_PORT_STATUS group (#617), forwarded to
            ``_set_metric``. ``None`` ⇒ tier-derived TTL.

        """
        for protocol in ("cdp", "lldp"):
            neighbor = port.get(protocol)
            if not neighbor:
                continue
            neighbor_labels = create_port_labels(
                device, port, org_id=org_id, org_name=org_name, type=protocol
            )
            self.parent._set_metric(
                self._switch_port_neighbor_present,
                neighbor_labels,
                1,
                MSMetricName.MS_PORT_NEIGHBOR_PRESENT.value,
                ttl_seconds=ttl_seconds,
            )

    @log_api_call("getOrganizationSwitchPortsStatusesBySwitch")
    @with_error_handling(
        operation="Collect MS switch port statuses (org)",
        continue_on_error=True,
    )
    async def collect_port_statuses_by_switch(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
    ) -> bool:
        """Collect port status metrics using the org-level switch endpoint."""
        # #617 gate: skip when MS_PORT_STATUS is not due this cycle. Return True
        # (not a failure) so the coordinator does not fall back to per-device.
        if not self.parent._should_run_group(EndpointGroupName.MS_PORT_STATUS):
            return True
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PORT_STATUS)

        if self._org_port_status_supported is None:
            self._org_port_status_supported = hasattr(
                self.api.switch,
                "getOrganizationSwitchPortsStatusesBySwitch",
            )
            if not self._org_port_status_supported:
                logger.warning(
                    "Org-level switch port status endpoint not available in SDK; "
                    "falling back to per-device collection",
                    org_id=org_id,
                )

        if not self._org_port_status_supported:
            return False

        device_lookup = {device.get("serial"): device for device in devices}
        serials = [device.get("serial") for device in devices if device.get("serial")]
        if not serials:
            return True

        with LogContext(org_id=org_id):
            response = await asyncio.to_thread(
                self.api.switch.getOrganizationSwitchPortsStatusesBySwitch,
                org_id,
                serials=serials,
                perPage=20,
                total_pages="all",
            )
            switches = validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationSwitchPortsStatusesBySwitch",
            )

        for switch in switches:
            serial = switch.get("serial")
            if not serial:
                continue

            device_info = device_lookup.get(serial, {})
            network = switch.get("network", {}) or {}
            network_id = network.get("id", device_info.get("networkId", ""))
            network_name = network.get("name", device_info.get("networkName", network_id))

            device_data = {
                "serial": serial,
                "name": switch.get("name", device_info.get("name", serial)),
                "model": switch.get("model", device_info.get("model", "")),
                "networkId": network_id,
                "networkName": network_name,
                "orgId": org_id,
                "orgName": org_name,
            }

            for port in switch.get("ports", []) or []:
                speed = port.get("speed", "")
                duplex = port.get("duplex", "")
                port_labels = create_port_labels(
                    device_data,
                    port,
                    org_id=org_id,
                    org_name=org_name,
                    link_speed=speed,
                    duplex=duplex,
                )

                is_connected = 1 if port.get("status") == "Connected" else 0
                self.parent._set_metric(
                    self._switch_port_status,
                    port_labels,
                    is_connected,
                    MSMetricName.MS_PORT_STATUS.value,
                    ttl_seconds=ttl,
                )

                self._emit_port_error_warning_metrics(
                    device_data, port, org_id, org_name, ttl_seconds=ttl
                )
                self._emit_port_stp_8021x_metrics(
                    device_data, port, org_id, org_name, ttl_seconds=ttl
                )
                self._emit_port_info(device_data, port, org_id, ttl_seconds=ttl)
                self._emit_port_neighbor_metrics(
                    device_data, port, org_id, org_name, ttl_seconds=ttl
                )

        self.parent._mark_group_ran(EndpointGroupName.MS_PORT_STATUS)
        return True

    @trace_method("process.device")
    @log_api_call("getDeviceSwitchPortsStatuses")
    @with_error_handling(
        operation="Collect MS device metrics",
        continue_on_error=True,
    )
    async def collect(self, device: dict[str, Any]) -> None:
        """Collect switch-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Switch device data.

        """
        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        # Track this serial as active in the current collection cycle
        serial_key = device_labels["serial"]
        self._active_serials.add(serial_key)

        # #617: this is the per-device fallback path (org endpoint unavailable /
        # failed), invoked once per device inside a batch fan-out, so it is NOT
        # group-gated here (a group mark_ran mid-batch would skip the remaining
        # devices). It emits both the port-status family and the port-usage/PoE
        # family from a single getDeviceSwitchPortsStatuses call, so thread each
        # family's solved TTL onto its own emissions.
        status_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PORT_STATUS)
        usage_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PORT_USAGE)

        try:
            # Get port statuses with 1-hour timespan
            with LogContext(serial=device_labels["serial"], name=device.get("name", "")):
                port_statuses = await asyncio.to_thread(
                    self.api.switch.getDeviceSwitchPortsStatuses,
                    device_labels["serial"],
                    timespan=3600,  # 1 hour timespan for better accuracy
                )
                port_statuses = validate_response_format(
                    port_statuses, expected_type=list, operation="getDeviceSwitchPortsStatuses"
                )

            for port in port_statuses:
                # Create port labels with additional attributes
                speed = port.get("speed", "")  # e.g., "1 Gbps", "100 Mbps"
                duplex = port.get("duplex", "")  # e.g., "full", "half"
                port_labels = create_port_labels(
                    device, port, org_id=org_id, org_name=org_name, link_speed=speed, duplex=duplex
                )

                # Port status with speed and duplex
                is_connected = 1 if port.get("status") == "Connected" else 0
                self.parent._set_metric(
                    self._switch_port_status,
                    port_labels,
                    is_connected,
                    MSMetricName.MS_PORT_STATUS.value,
                    ttl_seconds=status_ttl,
                )

                # Active port errors/warnings (expire automatically once cleared)
                self._emit_port_error_warning_metrics(
                    device, port, org_id, org_name, ttl_seconds=status_ttl
                )

                # STP state and 802.1X/secure-port auth status (same payload)
                self._emit_port_stp_8021x_metrics(
                    device, port, org_id, org_name, ttl_seconds=status_ttl
                )

                # Port info join series (#534): port_name keyed on serial+port_id
                self._emit_port_info(device, port, org_id, ttl_seconds=status_ttl)

                # CDP/LLDP neighbor presence (#296), same payload
                self._emit_port_neighbor_metrics(
                    device, port, org_id, org_name, ttl_seconds=status_ttl
                )

                # Traffic counters (rate in bytes per second)
                if "trafficInKbps" in port:
                    traffic_counters = port["trafficInKbps"]

                    if "recv" in traffic_counters:
                        rx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="rx"
                        )
                        self.parent._set_metric(
                            self._switch_port_traffic,
                            rx_labels,
                            traffic_counters["recv"] * 1000 / 8,  # Convert kbps to bytes/sec
                            MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND.value,
                            ttl_seconds=usage_ttl,
                        )

                    if "sent" in traffic_counters:
                        tx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="tx"
                        )
                        self.parent._set_metric(
                            self._switch_port_traffic,
                            tx_labels,
                            traffic_counters["sent"] * 1000 / 8,  # Convert kbps to bytes/sec
                            MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND.value,
                            ttl_seconds=usage_ttl,
                        )

                # Usage counters (total bytes over timespan)
                if "usageInKb" in port:
                    usage_counters = port["usageInKb"]

                    if "recv" in usage_counters:
                        rx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="rx"
                        )
                        self.parent._set_metric(
                            self._switch_port_usage,
                            rx_labels,
                            usage_counters["recv"]
                            * 1000,  # decimal KB->bytes (D5: x1000, not KiB x1024)
                            MSMetricName.MS_PORT_USAGE_BYTES.value,
                            ttl_seconds=usage_ttl,
                        )

                    if "sent" in usage_counters:
                        tx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="tx"
                        )
                        self.parent._set_metric(
                            self._switch_port_usage,
                            tx_labels,
                            usage_counters["sent"]
                            * 1000,  # decimal KB->bytes (D5: x1000, not KiB x1024)
                            MSMetricName.MS_PORT_USAGE_BYTES.value,
                            ttl_seconds=usage_ttl,
                        )

                    if "total" in usage_counters:
                        total_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="total"
                        )
                        self.parent._set_metric(
                            self._switch_port_usage,
                            total_labels,
                            usage_counters["total"]
                            * 1000,  # decimal KB->bytes (D5: x1000, not KiB x1024)
                            MSMetricName.MS_PORT_USAGE_BYTES.value,
                            ttl_seconds=usage_ttl,
                        )

                # Client count
                client_count = port.get("clientCount", 0)
                # Use base port labels without direction for client count
                port_labels_no_extra = create_port_labels(
                    device, port, org_id=org_id, org_name=org_name
                )
                self.parent._set_metric(
                    self._switch_port_client_count,
                    port_labels_no_extra,
                    client_count,
                    MSMetricName.MS_PORT_CLIENT_COUNT.value,
                    ttl_seconds=usage_ttl,
                )

            # Extract POE data from port statuses (POE data is included in port status)
            total_poe_consumption = 0

            for port in port_statuses:
                # Create port labels for POE metrics
                port_labels = create_port_labels(device, port, org_id=org_id, org_name=org_name)

                # Check if port has POE data
                poe_info = port.get("poe", {})
                if poe_info.get("isAllocated", False):
                    # Port is drawing POE power. API reports watt-hours (Wh);
                    # keep total_poe_consumption in Wh (also feeds the watts
                    # approximation below) and convert to joules (D3: x3600)
                    # only at the energy-metric emit sites.
                    power_used = port.get("powerUsageInWh", 0)
                    self.parent._set_metric(
                        self._switch_poe_port_power,
                        port_labels,
                        power_used * 3600,  # Wh -> J
                        MSMetricName.MS_POE_PORT_ENERGY_JOULES.value,
                        ttl_seconds=usage_ttl,
                    )
                    total_poe_consumption += power_used
                else:
                    # Port is not drawing POE power
                    self.parent._set_metric(
                        self._switch_poe_port_power,
                        port_labels,
                        0,
                        MSMetricName.MS_POE_PORT_ENERGY_JOULES.value,
                        ttl_seconds=usage_ttl,
                    )

            # Set switch-level POE total (Wh -> J)
            self.parent._set_metric(
                self._switch_poe_total_power,
                device_labels,
                total_poe_consumption * 3600,
                MSMetricName.MS_POE_TOTAL_ENERGY_JOULES.value,
                ttl_seconds=usage_ttl,
            )

            # Set total switch power usage (POE consumption is the main power draw)
            # This is an approximation - actual switch base power consumption varies
            # by model. Deliberately left unconverted (Wh treated as a watts stand-in,
            # not an energy metric - MS_POWER_USAGE_WATTS is out of scope for #531).
            self.parent._set_metric(
                self._switch_power,
                device_labels,
                total_poe_consumption,
                MSMetricName.MS_POWER_USAGE_WATTS.value,
                ttl_seconds=usage_ttl,
            )

            # Note: POE budget is not available via API, would need a lookup table by model

            # Collect packet statistics
            await self._collect_packet_statistics(device)
            self._mark_port_usage_collected(device_labels["serial"])

        except Exception:
            logger.exception(
                "Failed to collect switch metrics",
                serial=device_labels["serial"],
            )

    @log_api_call("getDeviceSwitchPortsStatuses")
    @with_error_handling(
        operation="Collect MS port usage metrics",
        continue_on_error=True,
    )
    async def collect_device_port_usage_metrics(self, device: dict[str, Any]) -> None:
        """Collect per-port usage and POE metrics for a switch."""
        serial = device.get("serial")
        if not serial:
            return

        if not self._should_collect_port_usage(serial):
            logger.debug(
                "Skipping switch port usage collection",
                serial=serial,
                interval_seconds=self.parent._group_interval(EndpointGroupName.MS_PORT_USAGE),
            )
            return

        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        # #617: per-device usage fallback, gated per-serial above; thread the
        # MS_PORT_USAGE solved TTL onto every emission.
        usage_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PORT_USAGE)

        with LogContext(serial=device_labels["serial"], name=device_labels["name"]):
            port_statuses = await asyncio.to_thread(
                self.api.switch.getDeviceSwitchPortsStatuses,
                device_labels["serial"],
                timespan=3600,
            )
            port_statuses = validate_response_format(
                port_statuses, expected_type=list, operation="getDeviceSwitchPortsStatuses"
            )

        for port in port_statuses:
            # Traffic counters (rate in bytes per second)
            if "trafficInKbps" in port:
                traffic_counters = port["trafficInKbps"]

                if "recv" in traffic_counters:
                    rx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="rx"
                    )
                    self.parent._set_metric(
                        self._switch_port_traffic,
                        rx_labels,
                        traffic_counters["recv"] * 1000 / 8,
                        MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND.value,
                        ttl_seconds=usage_ttl,
                    )

                if "sent" in traffic_counters:
                    tx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="tx"
                    )
                    self.parent._set_metric(
                        self._switch_port_traffic,
                        tx_labels,
                        traffic_counters["sent"] * 1000 / 8,
                        MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND.value,
                        ttl_seconds=usage_ttl,
                    )

            # Usage counters (total bytes over timespan)
            if "usageInKb" in port:
                usage_counters = port["usageInKb"]

                if "recv" in usage_counters:
                    rx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="rx"
                    )
                    self.parent._set_metric(
                        self._switch_port_usage,
                        rx_labels,
                        usage_counters["recv"] * 1000,  # decimal KB x1000
                        MSMetricName.MS_PORT_USAGE_BYTES.value,
                        ttl_seconds=usage_ttl,
                    )

                if "sent" in usage_counters:
                    tx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="tx"
                    )
                    self.parent._set_metric(
                        self._switch_port_usage,
                        tx_labels,
                        usage_counters["sent"] * 1000,  # decimal KB x1000
                        MSMetricName.MS_PORT_USAGE_BYTES.value,
                        ttl_seconds=usage_ttl,
                    )

                if "total" in usage_counters:
                    total_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="total"
                    )
                    self.parent._set_metric(
                        self._switch_port_usage,
                        total_labels,
                        usage_counters["total"] * 1000,  # decimal KB x1000
                        MSMetricName.MS_PORT_USAGE_BYTES.value,
                        ttl_seconds=usage_ttl,
                    )

            # Client count
            client_count = port.get("clientCount", 0)
            port_labels_no_extra = create_port_labels(
                device, port, org_id=org_id, org_name=org_name
            )
            self.parent._set_metric(
                self._switch_port_client_count,
                port_labels_no_extra,
                client_count,
                MSMetricName.MS_PORT_CLIENT_COUNT.value,
                ttl_seconds=usage_ttl,
            )

        # Extract POE data from port statuses (POE data is included in port status)
        total_poe_consumption = 0

        for port in port_statuses:
            port_labels = create_port_labels(device, port, org_id=org_id, org_name=org_name)
            poe_info = port.get("poe", {})
            if poe_info.get("isAllocated", False):
                # API reports watt-hours (Wh); keep total_poe_consumption in Wh
                # (also feeds the watts approximation below) and convert to
                # joules (D3: x3600) only at the energy-metric emit sites.
                power_used = port.get("powerUsageInWh", 0)
                self.parent._set_metric(
                    self._switch_poe_port_power,
                    port_labels,
                    power_used * 3600,  # Wh -> J
                    MSMetricName.MS_POE_PORT_ENERGY_JOULES.value,
                    ttl_seconds=usage_ttl,
                )
                total_poe_consumption += power_used
            else:
                self.parent._set_metric(
                    self._switch_poe_port_power,
                    port_labels,
                    0,
                    MSMetricName.MS_POE_PORT_ENERGY_JOULES.value,
                    ttl_seconds=usage_ttl,
                )

        self.parent._set_metric(
            self._switch_poe_total_power,
            device_labels,
            total_poe_consumption * 3600,  # Wh -> J
            MSMetricName.MS_POE_TOTAL_ENERGY_JOULES.value,
            ttl_seconds=usage_ttl,
        )
        # Unconverted (Wh treated as a watts stand-in) - MS_POWER_USAGE_WATTS is
        # out of scope for #531 (checked-OK, see spec §3).
        self.parent._set_metric(
            self._switch_power,
            device_labels,
            total_poe_consumption,
            MSMetricName.MS_POWER_USAGE_WATTS.value,
            ttl_seconds=usage_ttl,
        )
        self._mark_port_usage_collected(serial)

    @log_api_call("getOrganizationSwitchPortsUsageHistoryByDeviceByInterval")
    @with_error_handling(
        operation="Collect MS switch port usage/PoE (org)",
        continue_on_error=True,
    )
    async def collect_port_usage_by_switch(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
    ) -> bool:
        """Collect per-port usage/traffic/PoE/client-count via org-wide endpoints.

        Replaces the per-switch ``getDeviceSwitchPortsStatuses`` usage/PoE loop
        with two org-wide bulk calls (F-168): the switch ports usage-history
        endpoint (per-port ``data.usage`` KB, ``bandwidth.usage`` kbps and
        ``energy.usage.total`` watt-hours - the PoE signal) and the switch ports
        clients-overview endpoint (per-port online client counts). This cuts the
        MS usage/PoE cost from ~1 call per switch to ~2 calls per org per cycle.

        Emits exactly the same metrics/labels as the per-device fallback
        (``collect_device_port_usage_metrics``): ``meraki_ms_port_traffic_bytes_per_second``,
        ``meraki_ms_port_usage_bytes``, ``meraki_ms_port_client_count``,
        ``meraki_ms_poe_port_energy_joules``,
        ``meraki_ms_poe_total_energy_joules`` and ``meraki_ms_power_usage_watts``.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            The MS devices to collect usage for (used to scope the org query via
            ``serials=`` and to enrich labels when the response omits fields).

        Returns
        -------
        bool
            ``True`` when the org-wide path ran (and metrics were emitted);
            ``False`` when the SDK lacks the usage-history endpoint, signalling
            the coordinator to fall back to the per-device loop.

        """
        # #617 gate: skip when MS_PORT_USAGE is not due this cycle. Return True
        # (not a failure) so the coordinator does not fall back to per-device.
        if not self.parent._should_run_group(EndpointGroupName.MS_PORT_USAGE):
            return True
        usage_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PORT_USAGE)

        if self._org_port_usage_supported is None:
            self._org_port_usage_supported = hasattr(
                self.api.switch,
                "getOrganizationSwitchPortsUsageHistoryByDeviceByInterval",
            ) and hasattr(
                self.api.switch,
                "getOrganizationSwitchPortsClientsOverviewByDevice",
            )
            if not self._org_port_usage_supported:
                logger.warning(
                    "Org-level switch port usage endpoints not available in SDK; "
                    "falling back to per-device usage collection",
                    org_id=org_id,
                )

        if not self._org_port_usage_supported:
            return False

        device_lookup = {device.get("serial"): device for device in devices}
        serials = [device.get("serial") for device in devices if device.get("serial")]
        if not serials:
            return True

        with LogContext(org_id=org_id):
            usage_response = await asyncio.to_thread(
                self.api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval,
                org_id,
                serials=serials,
                timespan=3600,
                perPage=50,
                total_pages="all",
            )
            usage_switches = validate_response_format(
                usage_response,
                expected_type=list,
                operation="getOrganizationSwitchPortsUsageHistoryByDeviceByInterval",
            )

            clients_response = await asyncio.to_thread(
                self.api.switch.getOrganizationSwitchPortsClientsOverviewByDevice,
                org_id,
                serials=serials,
                timespan=3600,
                perPage=20,
                total_pages="all",
            )
            clients_switches = validate_response_format(
                clients_response,
                expected_type=list,
                operation="getOrganizationSwitchPortsClientsOverviewByDevice",
            )

        # Build a (serial, port_id) -> online client count lookup. The
        # clients-overview endpoint only lists ports with >=1 online client, so
        # ports absent here default to 0 (matching the per-device behaviour).
        client_counts: dict[tuple[str, str], int] = {}
        for switch in clients_switches:
            switch_serial = switch.get("serial")
            if not switch_serial:
                continue
            for port in switch.get("ports", []) or []:
                port_id = str(port.get("portId", ""))
                online = (port.get("counts", {}) or {}).get("byStatus", {}).get("online", 0)
                client_counts[(switch_serial, port_id)] = online

        for switch in usage_switches:
            serial = switch.get("serial")
            if not serial:
                continue

            device_info = device_lookup.get(serial, {})
            network = switch.get("network", {}) or {}
            network_id = network.get("id", device_info.get("networkId", ""))
            network_name = network.get("name", device_info.get("networkName", network_id))

            device_data = {
                "serial": serial,
                "name": switch.get("name", device_info.get("name", serial)),
                "model": switch.get("model", device_info.get("model", "")),
                "networkId": network_id,
                "networkName": network_name,
                "orgId": org_id,
                "orgName": org_name,
            }
            device_labels = create_device_labels(device_data, org_id=org_id, org_name=org_name)

            total_poe_consumption: float = 0.0

            for port in switch.get("ports", []) or []:
                port_id = str(port.get("portId", ""))
                intervals = port.get("intervals", []) or []

                # Aggregate the per-interval series into the same shape the
                # per-device endpoint returns as a single value: sum usage
                # (KB) and energy (Wh) over the window, average bandwidth (kbps).
                usage_up_kb = 0.0
                usage_down_kb = 0.0
                usage_total_kb = 0.0
                have_usage = False
                bw_up_samples: list[float] = []
                bw_down_samples: list[float] = []
                energy_wh = 0.0

                for interval in intervals:
                    data_usage = (interval.get("data", {}) or {}).get("usage")
                    if data_usage:
                        have_usage = True
                        usage_up_kb += data_usage.get("upstream", 0) or 0
                        usage_down_kb += data_usage.get("downstream", 0) or 0
                        usage_total_kb += data_usage.get("total", 0) or 0

                    bw_usage = (interval.get("bandwidth", {}) or {}).get("usage")
                    if bw_usage:
                        if bw_usage.get("upstream") is not None:
                            bw_up_samples.append(bw_usage["upstream"])
                        if bw_usage.get("downstream") is not None:
                            bw_down_samples.append(bw_usage["downstream"])

                    energy_usage = (interval.get("energy", {}) or {}).get("usage")
                    if energy_usage:
                        energy_wh += energy_usage.get("total", 0) or 0

                # Traffic rate (bytes/sec), averaged over the window. upstream ==
                # sent (tx), downstream == recv (rx). kbps -> bytes/sec = *1000/8.
                if bw_down_samples:
                    rx_labels = create_port_labels(
                        device_data, port, org_id=org_id, org_name=org_name, direction="rx"
                    )
                    self.parent._set_metric(
                        self._switch_port_traffic,
                        rx_labels,
                        (sum(bw_down_samples) / len(bw_down_samples)) * 1000 / 8,
                        MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND.value,
                        ttl_seconds=usage_ttl,
                    )
                if bw_up_samples:
                    tx_labels = create_port_labels(
                        device_data, port, org_id=org_id, org_name=org_name, direction="tx"
                    )
                    self.parent._set_metric(
                        self._switch_port_traffic,
                        tx_labels,
                        (sum(bw_up_samples) / len(bw_up_samples)) * 1000 / 8,
                        MSMetricName.MS_PORT_TRAFFIC_BYTES_PER_SECOND.value,
                        ttl_seconds=usage_ttl,
                    )

                # Usage bytes over the window. Decimal KB -> bytes = *1000 (D5:
                # Meraki dashboard data-volume KB is decimal, not KiB).
                if have_usage:
                    rx_labels = create_port_labels(
                        device_data, port, org_id=org_id, org_name=org_name, direction="rx"
                    )
                    self.parent._set_metric(
                        self._switch_port_usage,
                        rx_labels,
                        usage_down_kb * 1000,
                        MSMetricName.MS_PORT_USAGE_BYTES.value,
                        ttl_seconds=usage_ttl,
                    )
                    tx_labels = create_port_labels(
                        device_data, port, org_id=org_id, org_name=org_name, direction="tx"
                    )
                    self.parent._set_metric(
                        self._switch_port_usage,
                        tx_labels,
                        usage_up_kb * 1000,
                        MSMetricName.MS_PORT_USAGE_BYTES.value,
                        ttl_seconds=usage_ttl,
                    )
                    total_labels = create_port_labels(
                        device_data, port, org_id=org_id, org_name=org_name, direction="total"
                    )
                    self.parent._set_metric(
                        self._switch_port_usage,
                        total_labels,
                        usage_total_kb * 1000,
                        MSMetricName.MS_PORT_USAGE_BYTES.value,
                        ttl_seconds=usage_ttl,
                    )

                # Client count (default 0 for ports with no online clients).
                port_labels_no_extra = create_port_labels(
                    device_data, port, org_id=org_id, org_name=org_name
                )
                self.parent._set_metric(
                    self._switch_port_client_count,
                    port_labels_no_extra,
                    client_counts.get((serial, port_id), 0),
                    MSMetricName.MS_PORT_CLIENT_COUNT.value,
                    ttl_seconds=usage_ttl,
                )

                # Per-port PoE (Wh delivered over the window, converted to
                # joules at emit time - D3: x3600). total_poe_consumption stays
                # in Wh so it can also feed the watts approximation below.
                self.parent._set_metric(
                    self._switch_poe_port_power,
                    port_labels_no_extra,
                    energy_wh * 3600,  # Wh -> J
                    MSMetricName.MS_POE_PORT_ENERGY_JOULES.value,
                    ttl_seconds=usage_ttl,
                )
                total_poe_consumption += energy_wh

            # Switch-level PoE total (Wh -> J) and (approximated, unconverted)
            # total power draw - MS_POWER_USAGE_WATTS is out of scope for #531.
            self.parent._set_metric(
                self._switch_poe_total_power,
                device_labels,
                total_poe_consumption * 3600,
                MSMetricName.MS_POE_TOTAL_ENERGY_JOULES.value,
                ttl_seconds=usage_ttl,
            )
            self.parent._set_metric(
                self._switch_power,
                device_labels,
                total_poe_consumption,
                MSMetricName.MS_POWER_USAGE_WATTS.value,
                ttl_seconds=usage_ttl,
            )

            self._mark_port_usage_collected(serial)

        self.parent._mark_group_ran(EndpointGroupName.MS_PORT_USAGE)
        return True

    def _should_collect_stp_priorities(self) -> bool:
        """Return whether enough time has elapsed to (re)collect STP priorities.

        STP bridge priority is near-static configuration; this collector is
        invoked every MEDIUM-tier (300s) DeviceCollector cycle but is
        self-gated here to the SLOW cadence (see F-037), mirroring the
        ``_should_collect_port_usage`` throttle pattern.

        The interval is sourced from the scheduler's solved MS_STP interval
        (#617, floor 900s) rather than the raw SLOW setting, so solver
        stretching/pins apply.
        """
        interval: float = self.parent._group_interval(EndpointGroupName.MS_STP)
        if interval <= 0:
            return True
        return (time.time() - self._last_stp_collection) >= interval

    def _mark_stp_priorities_collected(self) -> None:
        """Record that STP priorities were just collected for this org."""
        self._last_stp_collection = time.time()

    @with_error_handling(
        operation="Collect STP priorities",
        continue_on_error=True,
    )
    async def collect_stp_priorities(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]] | None = None
    ) -> None:
        """Collect STP priorities for all switches in an organization.

        Interval-gated to the ``ms_stp`` group's solved interval
        (``parent._group_interval(EndpointGroupName.MS_STP)``, 900s floor)
        and fans out per-network fetches concurrently via ``ManagedTaskGroup``
        (bounded by ``settings.api.concurrency_limit``) instead of a sequential
        loop (see F-037).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]] | None
            Device lookup table. If not provided, defaults to empty dict.

        """
        from ...core.domain_models import STPConfiguration

        # #292/#293/#295 (Phase 4, #618): DHCP-security posture (rogue DHCP +
        # DAI coverage) and link-aggregation membership ride this already
        # per-org-invoked call site instead of adding new device.py
        # invocations. Each is independently gated via its own scheduler group
        # (MS_DHCP_SECURITY / MS_LINK_AGGREGATIONS) - NOT the STP timestamp
        # gate below - so their cadence is unaffected by MS_STP's solved
        # interval.
        await self.collect_dhcp_security(org_id, org_name)
        await self.collect_link_aggregations(org_id, org_name)

        if not self._should_collect_stp_priorities():
            logger.debug(
                "Skipping STP priority collection (interval gate)",
                org_id=org_id,
                interval_seconds=self.parent._group_interval(EndpointGroupName.MS_STP),
            )
            return

        stp_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_STP)

        try:
            # Fetch networks via the shared inventory cache so the network
            # filter applies and we share the result with sibling collectors.
            with LogContext(org_id=org_id):
                networks = await self.parent.inventory.get_networks(org_id)

            # Filter to only networks with switches
            switch_networks = [n for n in networks if "switch" in n.get("productTypes", [])]

            logger.debug(
                "Found switch networks for STP collection",
                org_id=org_id,
                total_networks=len(networks),
                switch_networks=len(switch_networks),
            )

            # Use provided device lookup or parent's
            devices = device_lookup or getattr(self.parent, "_device_lookup", {})

            async def _collect_network_stp(network: dict[str, Any]) -> None:
                network_id = network["id"]

                try:
                    # Fetch STP configuration for the network
                    with LogContext(network_id=network_id):
                        # This nested per-network fetch is not decorated with
                        # @log_api_call, so acquire the rate limiter explicitly
                        # (keyed by the owning org) to avoid bypassing throttling.
                        rate_limiter = getattr(self.parent, "rate_limiter", None)
                        if rate_limiter is not None:
                            await rate_limiter.acquire(org_id, "getNetworkSwitchStp")
                        stp_data = await asyncio.to_thread(
                            self.api.switch.getNetworkSwitchStp,
                            network_id,
                        )
                        stp_data = validate_response_format(
                            stp_data,
                            expected_type=dict,
                            operation="getNetworkSwitchStp",
                        )

                    # Parse the STP configuration
                    stp_config = STPConfiguration.model_validate(stp_data)

                    # Set metrics for each switch in the network
                    switch_priorities = stp_config.switch_priorities
                    network_name = network.get("name", network_id)

                    for switch_serial, priority in switch_priorities.items():
                        # Get switch details from device lookup. Copy the entry
                        # (never mutate the shared lookup) and always stamp the
                        # real serial from the STP config. The shared lookup now
                        # carries a "serial" key (#669), but a switch present in
                        # the STP config yet absent from the lookup falls back to
                        # {} here, so this stamp is still required: without it
                        # create_device_labels would emit serial="" and two
                        # same-named switches in a network would collide on
                        # (network, name) (F-174).
                        device_info = dict(devices.get(switch_serial, {}))
                        device_info["serial"] = switch_serial
                        device_info["networkId"] = network_id
                        device_info["networkName"] = network_name
                        device_info["orgId"] = org_id
                        device_info["orgName"] = org_name

                        # Create standard device labels
                        labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                        self.parent._set_metric(
                            self._switch_stp_priority,
                            labels,
                            priority,
                            MSMetricName.MS_STP_PRIORITY.value,
                            ttl_seconds=stp_ttl,
                        )

                        logger.debug(
                            "Set STP priority",
                            serial=switch_serial,
                            name=device_info.get("name", ""),
                            network_id=network_id,
                            priority=priority,
                        )

                except Exception:
                    logger.exception(
                        "Failed to collect STP data for network",
                        network_id=network_id,
                    )

            async with ManagedTaskGroup(
                name="ms_stp",
                max_concurrency=self.settings.api.concurrency_limit,
            ) as group:
                for network in switch_networks:
                    await group.create_task(
                        _collect_network_stp(network),
                        name=f"stp_{network['id']}",
                    )

            self._mark_stp_priorities_collected()

        except Exception:
            logger.exception(
                "Failed to collect STP priorities",
                org_id=org_id,
            )

    @log_api_call("getDeviceSwitchPortsStatusesPackets")
    @with_error_handling(
        operation="Collect MS packet statistics",
        continue_on_error=True,
    )
    async def _collect_packet_statistics(self, device: dict[str, Any]) -> None:
        """Collect packet statistics for a switch.

        Parameters
        ----------
        device : dict[str, Any]
            Switch device data.

        """
        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        serial = device_labels.get("serial")
        if serial and not self._should_collect_packet_stats(serial):
            logger.debug(
                "Skipping packet statistics collection",
                serial=serial,
                interval_seconds=self.parent._group_interval(EndpointGroupName.MS_PACKET_STATS),
            )
            return

        # #617: thread the MS_PACKET_STATS solved TTL onto every emission.
        packet_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PACKET_STATS)

        try:
            # Get packet statistics with 5-minute timespan
            with LogContext(serial=device_labels["serial"], name=device.get("name", "")):
                packet_stats = await asyncio.to_thread(
                    self.api.switch.getDeviceSwitchPortsStatusesPackets,
                    device_labels["serial"],
                    timespan=300,  # 5-minute window
                )
                packet_stats = validate_response_format(
                    packet_stats,
                    expected_type=list,
                    operation="getDeviceSwitchPortsStatusesPackets",
                )

            # Mapping of API descriptions to metric types (gauge + metric-name pairs
            # for count/rate, so _set_metric can track expiration correctly).
            metric_map = {
                "Total": (
                    self._switch_port_packets_total,
                    self._switch_port_packets_rate_total,
                    MSMetricName.MS_PORT_PACKETS_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE.value,
                ),
                "Broadcast": (
                    self._switch_port_packets_broadcast,
                    self._switch_port_packets_rate_broadcast,
                    MSMetricName.MS_PORT_PACKETS_BROADCAST_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE_BROADCAST.value,
                ),
                "Multicast": (
                    self._switch_port_packets_multicast,
                    self._switch_port_packets_rate_multicast,
                    MSMetricName.MS_PORT_PACKETS_MULTICAST_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE_MULTICAST.value,
                ),
                "CRC align errors": (
                    self._switch_port_packets_crcerrors,
                    self._switch_port_packets_rate_crcerrors,
                    MSMetricName.MS_PORT_PACKETS_CRCERRORS_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE_CRCERRORS.value,
                ),
                "Fragments": (
                    self._switch_port_packets_fragments,
                    self._switch_port_packets_rate_fragments,
                    MSMetricName.MS_PORT_PACKETS_FRAGMENTS_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE_FRAGMENTS.value,
                ),
                "Collisions": (
                    self._switch_port_packets_collisions,
                    self._switch_port_packets_rate_collisions,
                    MSMetricName.MS_PORT_PACKETS_COLLISIONS_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE_COLLISIONS.value,
                ),
                "Topology changes": (
                    self._switch_port_packets_topologychanges,
                    self._switch_port_packets_rate_topologychanges,
                    MSMetricName.MS_PORT_PACKETS_TOPOLOGYCHANGES_COUNT.value,
                    MSMetricName.MS_PORT_PACKETS_RATE_TOPOLOGYCHANGES.value,
                ),
            }

            for port_data in packet_stats:
                packets = port_data.get("packets", [])

                for packet_type in packets:
                    desc = packet_type.get("desc", "")

                    if desc in metric_map:
                        count_metric, rate_metric, count_metric_name, rate_metric_name = metric_map[
                            desc
                        ]

                        # Total counts
                        total = packet_type.get("total", 0)
                        sent = packet_type.get("sent", 0)
                        recv = packet_type.get("recv", 0)

                        # Create port labels for each direction
                        total_labels = create_port_labels(
                            device, port_data, org_id=org_id, org_name=org_name, direction="total"
                        )
                        sent_labels = create_port_labels(
                            device, port_data, org_id=org_id, org_name=org_name, direction="sent"
                        )
                        recv_labels = create_port_labels(
                            device, port_data, org_id=org_id, org_name=org_name, direction="recv"
                        )

                        # Set count metrics
                        self.parent._set_metric(
                            count_metric,
                            total_labels,
                            total,
                            count_metric_name,
                            ttl_seconds=packet_ttl,
                        )
                        self.parent._set_metric(
                            count_metric,
                            sent_labels,
                            sent,
                            count_metric_name,
                            ttl_seconds=packet_ttl,
                        )
                        self.parent._set_metric(
                            count_metric,
                            recv_labels,
                            recv,
                            count_metric_name,
                            ttl_seconds=packet_ttl,
                        )

                        # Rate per second
                        rate_data = packet_type.get("ratePerSec", {})
                        rate_total = rate_data.get("total", 0)
                        rate_sent = rate_data.get("sent", 0)
                        rate_recv = rate_data.get("recv", 0)

                        # Set rate metrics
                        self.parent._set_metric(
                            rate_metric,
                            total_labels,
                            rate_total,
                            rate_metric_name,
                            ttl_seconds=packet_ttl,
                        )
                        self.parent._set_metric(
                            rate_metric,
                            sent_labels,
                            rate_sent,
                            rate_metric_name,
                            ttl_seconds=packet_ttl,
                        )
                        self.parent._set_metric(
                            rate_metric,
                            recv_labels,
                            rate_recv,
                            rate_metric_name,
                            ttl_seconds=packet_ttl,
                        )

            logger.debug(
                "Collected packet statistics",
                serial=device_labels["serial"],
                name=device.get("name", ""),
                port_count=len(packet_stats),
            )
            if serial:
                self._mark_packet_stats_collected(serial)

        except Exception:
            logger.exception(
                "Failed to collect packet statistics",
                serial=device_labels["serial"],
            )

    @log_api_call("getOrganizationSwitchPortsOverview")
    @with_error_handling(
        operation="Collect switch port overview",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_port_overview(self, org_id: str, org_name: str) -> None:
        """Collect switch port overview metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # #294 (Phase 4, #618): org-wide PoE draw rides this already
        # per-org-invoked single-org-call site instead of adding a new
        # device.py invocation. Independently gated via MS_POWER_SUMMARY, so
        # it runs on its own cadence regardless of the MS_PORT_OVERVIEW gate
        # checked below.
        await self.collect_power_history(org_id, org_name)

        # #617 gate: MS_PORT_OVERVIEW is a low-volatility single org call (floor
        # 3600). Skip when not due; mark_ran after a successful fetch.
        if not self.parent._should_run_group(EndpointGroupName.MS_PORT_OVERVIEW):
            return

        # #617 §1f: thread the solved MS_PORT_OVERVIEW group TTL onto every
        # emission so slow-polled (floor-3600s) port-overview series expire on
        # their own cadence instead of lingering forever after ports change.
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_PORT_OVERVIEW)

        # Call the API with required timespan
        overview = await asyncio.to_thread(
            self.api.switch.getOrganizationSwitchPortsOverview,
            org_id,
            timespan=43200,  # 12 hours as required
        )
        overview = validate_response_format(
            overview,
            expected_type=dict,
            operation="getOrganizationSwitchPortsOverview",
        )

        # Parse the counts structure
        counts = overview.get("counts", {})

        # Set total active/inactive counts
        active_count = counts.get("byStatus", {}).get("active", {}).get("total", 0)
        inactive_count = counts.get("byStatus", {}).get("inactive", {}).get("total", 0)

        self.parent._set_metric(
            self._ms_ports_active_total,
            create_labels(org_id=org_id),
            active_count,
            MSMetricName.MS_PORTS_ACTIVE.value,
            ttl_seconds=ttl,
        )
        self.parent._set_metric(
            self._ms_ports_inactive_total,
            create_labels(org_id=org_id),
            inactive_count,
            MSMetricName.MS_PORTS_INACTIVE.value,
            ttl_seconds=ttl,
        )

        logger.debug(
            "Set port overview totals",
            org_id=org_id,
            active_count=active_count,
            inactive_count=inactive_count,
        )

        # Process active ports by media and link speed
        active_data = counts.get("byStatus", {}).get("active", {})
        by_media_speed = active_data.get("byMediaAndLinkSpeed", {})

        for media_type, media_data in by_media_speed.items():
            # Set total for this media type (active)
            media_total = media_data.get("total", 0)
            self.parent._set_metric(
                self._ms_ports_by_media_total,
                create_labels(org_id=org_id, media=media_type, status="active"),
                media_total,
                MSMetricName.MS_PORTS_BY_MEDIA.value,
                ttl_seconds=ttl,
            )

            # Set breakdown by link speed
            for speed, count in media_data.items():
                if speed != "total" and isinstance(count, (int, float)):
                    self.parent._set_metric(
                        self._ms_ports_by_link_speed_total,
                        create_labels(org_id=org_id, media=media_type, link_speed=str(speed)),
                        count,
                        MSMetricName.MS_PORTS_BY_LINK_SPEED.value,
                        ttl_seconds=ttl,
                    )

                    logger.debug(
                        "Set port link speed count",
                        org_id=org_id,
                        media=media_type,
                        speed=speed,
                        count=count,
                    )

        # Process inactive ports by media
        inactive_data = counts.get("byStatus", {}).get("inactive", {})
        by_media = inactive_data.get("byMedia", {})

        for media_type, media_data in by_media.items():
            media_total = media_data.get("total", 0)
            self.parent._set_metric(
                self._ms_ports_by_media_total,
                create_labels(org_id=org_id, media=media_type, status="inactive"),
                media_total,
                MSMetricName.MS_PORTS_BY_MEDIA.value,
                ttl_seconds=ttl,
            )

        self.parent._mark_group_ran(EndpointGroupName.MS_PORT_OVERVIEW)

        logger.debug(
            "Completed switch port overview collection",
            org_id=org_id,
        )

    @log_api_call("getOrganizationSummarySwitchPowerHistory")
    @with_error_handling(
        operation="Collect MS org-wide PoE draw",
        continue_on_error=True,
    )
    async def collect_power_history(self, org_id: str, org_name: str) -> None:
        """Collect org-wide switch PoE power draw (#294).

        Single org-wide bulk call (``getOrganizationSummarySwitchPowerHistory``)
        returning a history of PoE-draw datapoints; only the MOST-RECENT
        datapoint is emitted (a snapshot-from-history pattern), since this is a
        Gauge, not a time series import. The response is bucketed, so the
        latest datapoint lags real-time by roughly the bucket width
        (documented as ~20 minutes - unconfirmed against a live org, see #618
        Phase-6 verification notes).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name (unused; kept for call-site symmetry with
            sibling org-wide collectors).

        """
        # #617 gate: MS_POWER_SUMMARY is a single org-wide call (floor 900).
        if not self.parent._should_run_group(EndpointGroupName.MS_POWER_SUMMARY):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_POWER_SUMMARY)

        with LogContext(org_id=org_id):
            response = await asyncio.to_thread(
                self.api.switch.getOrganizationSummarySwitchPowerHistory,
                org_id,
            )
            history = validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationSummarySwitchPowerHistory",
            )

        if not history:
            logger.debug(
                "No switch power history datapoints returned",
                org_id=org_id,
            )
            self.parent._mark_group_ran(EndpointGroupName.MS_POWER_SUMMARY)
            return

        # Most-recent datapoint: the endpoint documents a chronological
        # history, so prefer the latest end-of-window timestamp when present
        # (falls back to array order otherwise). ⚠ field name unverified
        # against a live org - see #618 Phase-6 notes.
        latest = max(
            history,
            key=lambda dp: dp.get("endTs") or dp.get("startTs") or "",
        )
        draw = latest.get("draw", latest.get("usage"))
        if draw is None:
            logger.debug(
                "Switch power history datapoint missing draw/usage field",
                org_id=org_id,
                datapoint_keys=list(latest.keys()),
            )
            self.parent._mark_group_ran(EndpointGroupName.MS_POWER_SUMMARY)
            return

        labels = create_labels(org_id=org_id)
        self.parent._set_metric(
            self._ms_org_poe_draw_watts,
            labels,
            draw,
            MSMetricName.MS_ORG_POE_DRAW_WATTS.value,
            ttl_seconds=ttl,
        )

        self.parent._mark_group_ran(EndpointGroupName.MS_POWER_SUMMARY)

    @with_error_handling(
        operation="Collect MS DHCP security posture",
        continue_on_error=True,
    )
    async def collect_dhcp_security(self, org_id: str, org_name: str) -> None:
        """Collect rogue-DHCP (#292) and DAI coverage (#293) posture per switch network.

        Two calls per switch network: ``getNetworkSwitchDhcpV4ServersSeen``
        (rogue/unauthorized DHCP servers seen in the last day) and
        ``getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice``
        (Dynamic ARP Inspection coverage by device). Fanned out concurrently
        via ``ManagedTaskGroup`` bounded by ``settings.api.concurrency_limit``,
        matching the ``collect_stp_priorities`` pattern.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # #617 gate: MS_DHCP_SECURITY covers both calls, gated as one family.
        if not self.parent._should_run_group(EndpointGroupName.MS_DHCP_SECURITY):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_DHCP_SECURITY)
        rate_limiter = getattr(self.parent, "rate_limiter", None)

        try:
            with LogContext(org_id=org_id):
                networks = await self.parent.inventory.get_networks(org_id)

            switch_networks = [n for n in networks if "switch" in n.get("productTypes", [])]

            async def _collect_network_dhcp_security(network: dict[str, Any]) -> None:
                network_id = network["id"]

                # Rogue/unauthorized DHCP servers seen (#292).
                try:
                    with LogContext(network_id=network_id):
                        if rate_limiter is not None:
                            await rate_limiter.acquire(org_id, "getNetworkSwitchDhcpV4ServersSeen")
                        servers_response = await asyncio.to_thread(
                            self.api.switch.getNetworkSwitchDhcpV4ServersSeen,
                            network_id,
                            total_pages="all",
                        )
                        servers_seen = validate_response_format(
                            servers_response,
                            expected_type=list,
                            operation="getNetworkSwitchDhcpV4ServersSeen",
                        )

                    # Aggregate by is_allowed only (never label by the
                    # attacker-influenced server MAC - cardinality/PII risk).
                    # Both label values are always emitted (0 when absent) so
                    # this windowed count resets cleanly every cycle instead
                    # of leaving a stale nonzero value behind via TTL.
                    allowed_count = 0
                    not_allowed_count = 0
                    for server in servers_seen:
                        # ⚠ field name unverified against a live org (#618
                        # Phase-6 notes) - defaults to "not allowed" (the
                        # safer/more alerting-visible assumption) if absent.
                        if server.get("isAllowed", False):
                            allowed_count += 1
                        else:
                            not_allowed_count += 1

                    self.parent._set_metric(
                        self._ms_dhcp_servers_seen,
                        create_labels(org_id=org_id, network_id=network_id, is_allowed="true"),
                        allowed_count,
                        MSMetricName.MS_DHCP_SERVERS_SEEN_COUNT.value,
                        ttl_seconds=ttl,
                    )
                    self.parent._set_metric(
                        self._ms_dhcp_servers_seen,
                        create_labels(org_id=org_id, network_id=network_id, is_allowed="false"),
                        not_allowed_count,
                        MSMetricName.MS_DHCP_SERVERS_SEEN_COUNT.value,
                        ttl_seconds=ttl,
                    )
                except Exception:
                    logger.exception(
                        "Failed to collect DHCPv4 servers seen",
                        network_id=network_id,
                    )

                # Dynamic ARP Inspection coverage (#293).
                try:
                    with LogContext(network_id=network_id):
                        if rate_limiter is not None:
                            await rate_limiter.acquire(
                                org_id,
                                "getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice",
                            )
                        dai_response = await asyncio.to_thread(
                            self.api.switch.getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice,
                            network_id,
                            total_pages="all",
                        )
                        dai_rows = validate_response_format(
                            dai_response,
                            expected_type=list,
                            operation=(
                                "getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice"
                            ),
                        )

                    for row in dai_rows:
                        serial = row.get("serial")
                        if not serial:
                            continue
                        # Rows carry serial only, not model (#618 spec) - do
                        # NOT use create_device_labels here.
                        dai_labels = create_labels(
                            org_id=org_id, network_id=network_id, serial=serial
                        )

                        # ⚠ field names unverified against a live org (#618
                        # Phase-6 notes). Only emit when present so an
                        # unrecognized row shape doesn't fabricate a false 0.
                        supports_inspection = row.get("supportsInspection")
                        if supports_inspection is not None:
                            self.parent._set_metric(
                                self._ms_dai_supported,
                                dai_labels,
                                1 if supports_inspection else 0,
                                MSMetricName.MS_DAI_SUPPORTED.value,
                                ttl_seconds=ttl,
                            )

                        has_trusted_port = row.get("hasTrustedPort")
                        if has_trusted_port is not None:
                            self.parent._set_metric(
                                self._ms_dai_trusted_port,
                                dai_labels,
                                1 if has_trusted_port else 0,
                                MSMetricName.MS_DAI_TRUSTED_PORT_CONFIGURED.value,
                                ttl_seconds=ttl,
                            )
                except Exception:
                    logger.exception(
                        "Failed to collect DAI coverage",
                        network_id=network_id,
                    )

            async with ManagedTaskGroup(
                name="ms_dhcp_security",
                max_concurrency=self.settings.api.concurrency_limit,
            ) as group:
                for network in switch_networks:
                    await group.create_task(
                        _collect_network_dhcp_security(network),
                        name=f"dhcp_security_{network['id']}",
                    )

            self.parent._mark_group_ran(EndpointGroupName.MS_DHCP_SECURITY)

        except Exception:
            logger.exception(
                "Failed to collect MS DHCP security posture",
                org_id=org_id,
            )

    @with_error_handling(
        operation="Collect MS link aggregations",
        continue_on_error=True,
    )
    async def collect_link_aggregations(self, org_id: str, org_name: str) -> None:
        """Collect link aggregation (LACP) groups + membership per switch network (#295).

        One call per switch network (``getNetworkSwitchLinkAggregations``).
        Fanned out concurrently via ``ManagedTaskGroup`` bounded by
        ``settings.api.concurrency_limit``, matching ``collect_stp_priorities``.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self.parent._should_run_group(EndpointGroupName.MS_LINK_AGGREGATIONS):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_LINK_AGGREGATIONS)
        rate_limiter = getattr(self.parent, "rate_limiter", None)

        try:
            with LogContext(org_id=org_id):
                networks = await self.parent.inventory.get_networks(org_id)

            switch_networks = [n for n in networks if "switch" in n.get("productTypes", [])]

            async def _collect_network_lags(network: dict[str, Any]) -> None:
                network_id = network["id"]
                try:
                    with LogContext(network_id=network_id):
                        if rate_limiter is not None:
                            await rate_limiter.acquire(org_id, "getNetworkSwitchLinkAggregations")
                        response = await asyncio.to_thread(
                            self.api.switch.getNetworkSwitchLinkAggregations,
                            network_id,
                        )
                        lags = validate_response_format(
                            response,
                            expected_type=list,
                            operation="getNetworkSwitchLinkAggregations",
                        )

                    self.parent._set_metric(
                        self._ms_link_aggregations,
                        create_labels(org_id=org_id, network_id=network_id),
                        len(lags),
                        MSMetricName.MS_LINK_AGGREGATIONS.value,
                        ttl_seconds=ttl,
                    )

                    # ⚠ shape unverified against a live org (#618 Phase-6
                    # notes): expects each LAG as {"id": ..., "switchPorts":
                    # [{"serial": ..., "portId": ...}, ...]}.
                    for lag in lags:
                        lag_id = str(lag.get("id", ""))
                        for member in lag.get("switchPorts", []) or []:
                            member_serial = member.get("serial", "")
                            member_port_id = str(member.get("portId", ""))
                            self.parent._set_metric(
                                self._ms_link_aggregation_member,
                                create_labels(
                                    org_id=org_id,
                                    network_id=network_id,
                                    lag_id=lag_id,
                                    serial=member_serial,
                                    port_id=member_port_id,
                                ),
                                1,
                                MSMetricName.MS_LINK_AGGREGATION_MEMBER.value,
                                ttl_seconds=ttl,
                            )
                except Exception:
                    logger.exception(
                        "Failed to collect link aggregations",
                        network_id=network_id,
                    )

            async with ManagedTaskGroup(
                name="ms_link_aggregations",
                max_concurrency=self.settings.api.concurrency_limit,
            ) as group:
                for network in switch_networks:
                    await group.create_task(
                        _collect_network_lags(network),
                        name=f"link_agg_{network['id']}",
                    )

            self.parent._mark_group_ran(EndpointGroupName.MS_LINK_AGGREGATIONS)

        except Exception:
            logger.exception(
                "Failed to collect MS link aggregations",
                org_id=org_id,
            )
