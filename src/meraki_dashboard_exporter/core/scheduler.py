"""Adaptive budget-aware endpoint scheduler (#617).

This module owns the pure interval solver and the ``EndpointScheduler``
runtime that gates endpoint-group fetches against the shared Meraki API
budget. Each endpoint group runs at its own solved interval, floored at its
volatility floor; the scheduler only stretches group intervals (never below the
floor) to fit estimated steady-state demand inside ``budget × target_utilization``.

Frozen seam per #617/#631 — names/signatures are compiled against by sibling
modules (collector.py gate helpers, manager.py wiring, inventory OrgShape
computation, rate-limiter AIMD feedback, the per-collector group-clocked loops
in app.py which read ``seconds_until_due``).

Settings are read dynamically (``settings.scheduler.*``, ``settings.api.*``,
``settings.monitoring.*``) rather than importing ``config_models`` — this avoids
an import cycle and lets tests supply a plain namespace.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from prometheus_client import Gauge

from .constants.metrics_constants import CollectorMetricName
from .logging import get_logger
from .metrics import LabelName

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .config import Settings
    from .rate_limiter import OrgRateLimiter

logger = get_logger(__name__)

# Frozen defaults mirroring SchedulerSettings (core/config_models.py); used
# only as fall-backs when a namespace-style settings object omits a knob.
_DEFAULTS: dict[str, Any] = {
    "mode": "adaptive",
    "target_utilization": 0.7,
    "max_stretch_factor": 4.0,
    "max_interval_seconds": 3600,
    "resolve_interval_seconds": 900,
    "failure_retry_seconds": 300,
    "aimd_enabled": True,
    "aimd_backoff_multiplier": 0.5,
    "aimd_recovery_rps_per_minute": 0.1,
    "aimd_resolve_hysteresis": 0.2,
    "group_interval_overrides": {},
}

# Fraction of the solved interval that must elapse before a group re-runs.
# 10% tolerance so wake-time jitter/smoothing can't cause skip-a-beat aliasing.
_GATE_TOLERANCE = 0.9

# Multiplicative step applied to the chosen group's interval per stretch round.
_STRETCH_STEP = 1.5


class EndpointGroupName(StrEnum):
    """Wire names for scheduler groups (label values of LabelName.GROUP)."""

    # FAST — MT sensor
    MT_SENSOR_READINGS = "mt_sensor_readings"
    # MEDIUM — DeviceCollector
    DEVICE_AVAILABILITY = "device_availability"
    DEVICE_MEMORY = "device_memory"
    MR_WIRELESS_CLIENTS = "mr_wireless_clients"
    MR_CONNECTION_STATS = "mr_connection_stats"
    MR_ETHERNET_STATUS = "mr_ethernet_status"
    MR_PACKET_LOSS = "mr_packet_loss"
    MR_CPU_LOAD = "mr_cpu_load"
    MR_SSID_STATUS = "mr_ssid_status"
    MR_SSID_USAGE = "mr_ssid_usage"
    MS_PORT_STATUS = "ms_port_status"
    MS_PORT_USAGE = "ms_port_usage"
    MS_PACKET_STATS = "ms_packet_stats"
    MS_PORT_OVERVIEW = "ms_port_overview"
    MS_POWER = "ms_power"
    MS_STACKS = "ms_stacks"
    MS_STP = "ms_stp"
    MX_UPLINK_STATUS = "mx_uplink_status"
    MX_UPLINK_HEALTH = "mx_uplink_health"
    MX_UPLINK_USAGE = "mx_uplink_usage"
    MX_PERFORMANCE = "mx_performance"
    MX_HA = "mx_ha"
    MX_VPN = "mx_vpn"
    MX_SECURITY_EVENTS = "mx_security_events"
    MX_FIREWALL_CONFIG = "mx_firewall_config"
    MV_ANALYTICS = "mv_analytics"
    MG_UPLINK_STATUS = "mg_uplink_status"
    # MEDIUM — NetworkHealthCollector
    NH_CHANNEL_UTILIZATION = "nh_channel_utilization"
    NH_CONNECTION_STATS = "nh_connection_stats"
    NH_DATA_RATES = "nh_data_rates"
    NH_BLUETOOTH = "nh_bluetooth"
    NH_FAILED_CONNECTIONS = "nh_failed_connections"
    NH_LATENCY_STATS = "nh_latency_stats"
    NH_AIR_MARSHAL = "nh_air_marshal"
    # MEDIUM — OrganizationCollector
    ORG_AVAILABILITIES = "org_availabilities"
    ORG_AVAILABILITY_HISTORY = "org_availability_history"
    ORG_API_USAGE = "org_api_usage"
    ORG_CLIENT_OVERVIEW = "org_client_overview"
    ORG_DEVICE_MODEL_OVERVIEW = "org_device_model_overview"
    ORG_PACKET_CAPTURES = "org_packet_captures"
    ORG_APP_USAGE = "org_app_usage"
    ORG_FIRMWARE = "org_firmware"
    ORG_LICENSES = "org_licenses"
    # MEDIUM — Alerts / MT alerts / Clients
    ALERTS_ASSURANCE = "alerts_assurance"
    ALERTS_SENSOR_OVERVIEW = "alerts_sensor_overview"
    MT_SENSOR_ALERTS = "mt_sensor_alerts"
    CLIENTS_LIST = "clients_list"
    CLIENTS_APP_USAGE = "clients_app_usage"
    CLIENTS_SIGNAL_QUALITY = "clients_signal_quality"
    # SLOW — ConfigCollector
    CONFIG_ORG = "config_org"
    # Ungated overhead (demand accounting only, gated=False)
    INVENTORY_WARM = "inventory_warm"
    ORG_METADATA = "org_metadata"

    # Phase 4 (#618)
    MX_SECURITY_CONFIG = "mx_security_config"
    MX_DHCP_SUBNETS = "mx_dhcp_subnets"
    MX_VPN_CONFIG = "mx_vpn_config"
    MX_NAT_CONFIG = "mx_nat_config"
    MX_VLAN_CONFIG = "mx_vlan_config"
    MR_SSID_FIREWALL = "mr_ssid_firewall"
    MR_RF_PROFILES = "mr_rf_profiles"
    MS_DHCP_SECURITY = "ms_dhcp_security"
    MS_POWER_SUMMARY = "ms_power_summary"
    MS_LINK_AGGREGATIONS = "ms_link_aggregations"
    ORG_CONFIG_TEMPLATES = "org_config_templates"
    ORG_ADAPTIVE_POLICY = "org_adaptive_policy"
    ORG_TOP_USAGE = "org_top_usage"
    ORG_WEBHOOK_LOGS = "org_webhook_logs"
    ORG_FIRMWARE_COMPLIANCE = "org_firmware_compliance"
    MT_ALERT_PROFILES = "mt_alert_profiles"
    MT_RELATIONSHIPS = "mt_relationships"
    MV_SENSE_CONFIG = "mv_sense_config"
    MV_ONBOARDING = "mv_onboarding"
    MG_CELLULAR_CONFIG = "mg_cellular_config"
    NH_MESH = "nh_mesh"

    # Phase 4B (#618)
    MR_SIGNAL_QUALITY = "mr_signal_quality"
    MR_POWER_MODE = "mr_power_mode"
    MR_WIRELESS_CONTROLLER = "mr_wireless_controller"
    MG_ESIMS = "mg_esims"
    MG_HA = "mg_ha"
    MX_UPLINKS_OVERVIEW = "mx_uplinks_overview"
    INSIGHT_APPLICATIONS = "insight_applications"
    INSIGHT_APP_HEALTH = "insight_app_health"


def pages(n: int, per_page: int) -> int:
    """Pagination helper: max(1, ceil(n / per_page)).

    Parameters
    ----------
    n : int
        Number of items to paginate.
    per_page : int
        Page size.

    Returns
    -------
    int
        Estimated number of API calls (pages); at least 1.

    """
    return max(1, math.ceil(n / per_page)) if n > 0 else 1


@dataclass(frozen=True, slots=True)
class OrgShape:
    """Sizing snapshot of the (single) organization, computed by inventory."""

    org_id: str
    network_count: int
    wireless_network_count: int
    switch_network_count: int
    appliance_network_count: int
    sensor_network_count: int
    camera_network_count: int
    cellular_network_count: int
    device_count: int
    ap_count: int
    switch_count: int
    appliance_count: int
    physical_mx_count: int
    camera_count: int
    sensor_count: int
    cellular_count: int
    # Phase 4B (#618) — defaulted so existing keyword constructors stay valid.
    catalyst_ap_count: int = 0  # wireless devices whose model starts with "CW" (#326/#624)
    signal_quality_ap_count: int = 0  # APs selected for #324: ap_count when
    # collectors.ap_signal_quality_tags is empty, else wireless devices whose
    # `tags` intersect the configured set; 0 when collect_ap_signal_quality is False


@dataclass(frozen=True, slots=True)
class EndpointGroup:
    """Declaration of one schedulable endpoint group (declared on coordinators)."""

    name: EndpointGroupName
    priority: int  # 1=up-ness/alerts, 2=sensor, 3=perf/health, 4=config/inventory
    floor_seconds: float  # natural data window; never poll faster
    cost_fn: Callable[[OrgShape], float]  # estimated API calls per ONE execution
    gated: bool = True  # False = demand-accounting only; should_run always True
    setting_pin: str | None = None  # legacy APISettings field that pins this group
    enabled_fn: Callable[[OrgShape], bool] | None = (
        None  # NEW (#623): None => always enabled; evaluated against the last-resolved OrgShape
    )


class SolvedInterval(NamedTuple):
    """Solver output for one endpoint group."""

    interval_seconds: float
    stretch_factor: float  # interval / floor
    cost_per_cycle: float
    demand_rps: float  # cost_per_cycle / interval_seconds
    pinned: bool


def solve_intervals(
    groups: Iterable[EndpointGroup],
    shape: OrgShape,
    budget_rps: float,
    target_utilization: float,
    overrides: dict[str, int],
    max_stretch_factor: float,
    max_interval_seconds: float,
) -> dict[EndpointGroupName, SolvedInterval]:
    """Pure, deterministic interval solver (no I/O, no clock).

    Frozen algorithm (#617/#631):

    1. ``interval[g] = floor`` — every group starts at its volatility floor
       (there is no tier heartbeat any more; each group runs at its own solved
       interval).
    2. Apply ``overrides`` (operator pins): set exactly; a pin below the group's
       floor is honoured with a WARNING log. Pinned groups are excluded from
       stretching.
    3. ``demand = Σ cost_fn(shape) / interval`` over ALL groups (including
       ``gated=False`` overhead groups).
    4. While ``demand > budget_rps × target_utilization``: stretch the
       unpinned, gated group chosen by sort key
       ``(-priority, stretch_factor, name)`` — lowest-priority class first,
       least-stretched first within a class, name as deterministic tiebreak —
       by ×1.5, capped at ``min(floor × max_stretch_factor,
       max_interval_seconds)``. Break when no candidates remain (over budget).
    5. Return the full map. Identical inputs yield identical output.

    Fixed mode is expressed by passing ``budget_rps=math.inf`` (steps 1-2 only).
    """
    group_list = sorted(groups, key=lambda g: str(g.name))

    intervals: dict[EndpointGroupName, float] = {}
    base: dict[EndpointGroupName, float] = {}
    pinned: dict[EndpointGroupName, bool] = {}
    costs: dict[EndpointGroupName, float] = {}

    # Step 1: every group starts at its volatility floor.
    for g in group_list:
        b = float(g.floor_seconds)
        base[g.name] = b
        intervals[g.name] = b
        pinned[g.name] = False
        enabled = g.enabled_fn is None or g.enabled_fn(shape)
        costs[g.name] = float(g.cost_fn(shape)) if enabled else 0.0

    # Step 2: operator overrides / pins.
    for g in group_list:
        raw = overrides.get(str(g.name))
        if raw is None:
            continue
        value = float(raw)
        if value < g.floor_seconds:
            logger.warning(
                "Endpoint group pinned below its volatility floor; honouring pin",
                group=str(g.name),
                pin_seconds=value,
                floor_seconds=float(g.floor_seconds),
            )
        intervals[g.name] = value
        pinned[g.name] = True

    # Steps 3-4: stretch until demand fits budget × target (adaptive only).
    def demand() -> float:
        return sum(costs[name] / intervals[name] for name in intervals)

    target = budget_rps * target_utilization
    while demand() > target:
        candidates: list[tuple[EndpointGroup, float]] = []
        for g in group_list:
            if pinned[g.name] or not g.gated:
                continue
            # Disabled groups contribute zero demand and never stretch, so their
            # SolvedInterval stays pinned at base (interval never flaps) — #623.
            if g.enabled_fn is not None and not g.enabled_fn(shape):
                continue
            cap = min(float(g.floor_seconds) * max_stretch_factor, max_interval_seconds)
            if intervals[g.name] < cap:
                candidates.append((g, cap))
        if not candidates:
            break  # over budget: caller derives the flag from final demand

        def sort_key(item: tuple[EndpointGroup, float]) -> tuple[float, float, str]:
            g, _cap = item
            return (-g.priority, intervals[g.name] / base[g.name], str(g.name))

        chosen, cap = min(candidates, key=sort_key)
        intervals[chosen.name] = min(intervals[chosen.name] * _STRETCH_STEP, cap)

    # Step 5: assemble the full map (insertion order = sorted names).
    result: dict[EndpointGroupName, SolvedInterval] = {}
    for g in group_list:
        interval = intervals[g.name]
        result[g.name] = SolvedInterval(
            interval_seconds=interval,
            stretch_factor=interval / base[g.name],
            cost_per_cycle=costs[g.name],
            demand_rps=costs[g.name] / interval,
            pinned=pinned[g.name],
        )
    return result


class EndpointScheduler:
    """Runtime scheduler: solved intervals + per-group run gates + gauges.

    Constructed once by ``CollectorManager`` and injected into every
    collector. ``resolve()`` is synchronous pure CPU — callers fetch the
    ``OrgShape`` (cached inventory reads) and hand it in.
    """

    _metrics_initialized: ClassVar[bool] = False
    _demand_gauge: ClassVar[Gauge | None] = None
    _budget_gauge: ClassVar[Gauge | None] = None
    _effective_budget_gauge: ClassVar[Gauge | None] = None
    _utilization_gauge: ClassVar[Gauge | None] = None
    _interval_gauge: ClassVar[Gauge | None] = None
    _stretch_gauge: ClassVar[Gauge | None] = None

    def __init__(self, settings: Settings, rate_limiter: OrgRateLimiter) -> None:
        """Initialize the scheduler.

        Parameters
        ----------
        settings : Settings
            Application settings (``scheduler``/``api``/``monitoring`` sections
            read dynamically).
        rate_limiter : OrgRateLimiter
            Shared client-side limiter; provides the AIMD-adjusted effective
            budget via ``effective_rate_per_second()``.

        """
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._groups: dict[EndpointGroupName, EndpointGroup] = {}
        self._solved: dict[EndpointGroupName, SolvedInterval] = {}
        self._last_ran: dict[EndpointGroupName, float] = {}
        # Monotonic timestamp of the last should_run()==True (attempt), whether
        # or not it then succeeded. Drives failure-retry spacing (#631): when the
        # most recent attempt failed (last_attempt > last_ran, or never ran), the
        # next attempt is spaced by failure_retry_seconds to avoid a hot loop.
        self._last_attempt: dict[EndpointGroupName, float] = {}
        self._last_shape: OrgShape | None = None
        self._last_resolve_ts: float | None = None
        self._budget_used_at_last_solve: float | None = None
        self._total_demand_rps: float = 0.0
        self._over_budget: bool = False
        self._init_metrics()

    # -- settings access (dynamic; no config_models import) -----------------

    def _sched(self, name: str) -> Any:
        section = getattr(self._settings, "scheduler", None)
        default = _DEFAULTS[name]
        if section is None:
            return default
        return getattr(section, name, default)

    def configured_budget_rps(self) -> float:
        """Configured API budget: requests_per_second × shared_fraction."""
        api = getattr(self._settings, "api", None)
        rps = float(getattr(api, "rate_limit_requests_per_second", 10.0))
        fraction = float(getattr(api, "rate_limit_shared_fraction", 0.8))
        return max(0.0, rps * fraction)

    def _effective_budget_rps(self) -> float:
        """AIMD-adjusted budget from the rate limiter; configured when N/A."""
        if not bool(self._sched("aimd_enabled")) or str(self._sched("mode")) != "adaptive":
            return self.configured_budget_rps()
        reader = getattr(self._rate_limiter, "effective_rate_per_second", None)
        if callable(reader):
            return float(reader())
        return self.configured_budget_rps()

    def _collect_overrides(self) -> dict[str, int]:
        """Merge legacy setting_pins with scheduler.group_interval_overrides.

        Explicit ``group_interval_overrides`` entries win over legacy pins.
        """
        overrides: dict[str, int] = {}
        api = getattr(self._settings, "api", None)
        fields_set = set(getattr(api, "model_fields_set", set()) or set())
        for group in self._groups.values():
            pin = group.setting_pin
            if pin and pin in fields_set:
                value = getattr(api, pin, None)
                if value is not None:
                    overrides[str(group.name)] = int(value)
        configured = dict(self._sched("group_interval_overrides") or {})
        known = {str(name) for name in self._groups}
        for name, value in configured.items():
            if str(name) not in known:
                logger.warning(
                    "Unknown endpoint group in scheduler.group_interval_overrides",
                    group=str(name),
                )
                continue
            overrides[str(name)] = int(value)
        return overrides

    # -- registration --------------------------------------------------------

    def register_groups(self, groups: Iterable[EndpointGroup]) -> None:
        """Register endpoint groups (collected from all collectors at startup)."""
        for group in groups:
            if group.name in self._groups:
                raise ValueError(f"duplicate endpoint group registration: {group.name}")
            self._groups[group.name] = group

    # -- solving --------------------------------------------------------------

    def resolve(self, shape: OrgShape) -> None:
        """Recompute intervals from the org shape; emit gauges and log.

        Synchronous pure CPU. In ``fixed`` mode only floors + pins apply
        (the stretch loop is disabled by an infinite budget).
        """
        mode = str(self._sched("mode"))
        target_utilization = float(self._sched("target_utilization"))
        configured_budget = self.configured_budget_rps()
        effective_budget = self._effective_budget_rps()
        solve_budget = math.inf if mode == "fixed" else effective_budget

        solved = solve_intervals(
            self._groups.values(),
            shape,
            solve_budget,
            target_utilization,
            self._collect_overrides(),
            float(self._sched("max_stretch_factor")),
            float(self._sched("max_interval_seconds")),
        )

        total_demand = sum(s.demand_rps for s in solved.values())
        over_budget = bool(solved) and total_demand > effective_budget * target_utilization

        self._solved = solved
        self._last_shape = shape
        self._last_resolve_ts = time.time()
        self._budget_used_at_last_solve = effective_budget
        self._total_demand_rps = total_demand
        self._over_budget = over_budget

        self._emit_gauges(configured_budget, effective_budget, total_demand)

        stretched = sorted(
            (str(name), s.interval_seconds, s.stretch_factor)
            for name, s in solved.items()
            if s.stretch_factor > 1.0
        )
        logger.info(
            "Scheduler resolved endpoint-group intervals",
            mode=mode,
            groups=len(solved),
            total_demand_rps=round(total_demand, 3),
            budget_rps=round(configured_budget, 3),
            effective_budget_rps=round(effective_budget, 3),
            target_utilization=target_utilization,
            over_budget=over_budget,
            stretched=[f"{n} {i:.0f}s ({f:.2f}x)" for n, i, f in stretched],
        )
        if over_budget:
            shed_candidates = sorted(
                str(g.name) for g in self._groups.values() if g.priority >= 3 and g.gated
            )
            logger.warning(
                "Estimated API demand exceeds budget even with every group at its "
                "interval cap; consider disabling low-priority collectors",
                total_demand_rps=round(total_demand, 3),
                effective_budget_rps=round(effective_budget, 3),
                target_utilization=target_utilization,
                lowest_priority_groups=shed_candidates,
            )

    # -- gates -----------------------------------------------------------------

    def interval_for(self, group: EndpointGroupName) -> float:
        """Current interval for a group; pre-resolve = the group's floor."""
        solved = self._solved.get(group)
        if solved is not None:
            return solved.interval_seconds
        declared = self._groups.get(group)
        if declared is None:
            raise KeyError(f"unknown endpoint group: {group}")
        # Pre-resolve the interval is simply the group's volatility floor.
        return float(declared.floor_seconds)

    def _failure_retry_seconds(self) -> float:
        return float(self._sched("failure_retry_seconds"))

    @staticmethod
    def _last_attempt_failed(last_ran: float | None, last_attempt: float | None) -> bool:
        """True when the most recent attempt did not produce a success.

        ``should_run`` records ``last_attempt`` at the START of a cycle and
        ``mark_ran`` records ``last_ran`` at the END of a successful fetch, so a
        successful cycle always leaves ``last_ran > last_attempt`` while a failed
        one leaves ``last_attempt > last_ran`` (or never a success at all).
        """
        if last_attempt is None:
            return False
        return last_ran is None or last_attempt > last_ran

    def should_run(self, group: EndpointGroupName, now: float | None = None) -> bool:
        """True when the group is due; records the attempt when it returns True.

        Due when ``interval×0.9`` has elapsed since the last SUCCESS (or the
        group never succeeded). If the most recent attempt FAILED (open gate),
        retries are additionally spaced by ``failure_retry_seconds`` so a
        persistently-failing group cannot hot-loop (#631). The normal successful
        cadence is never delayed by ``failure_retry_seconds``. Ungated and
        unregistered groups always run (fail-open).
        """
        declared = self._groups.get(group)
        if declared is None or not declared.gated:
            return True
        # #623: skip a group whose enabled_fn is False against the last-resolved
        # shape. Fail-open pre-resolve (no shape yet) — matches the gated contract.
        if (
            declared.enabled_fn is not None
            and self._last_shape is not None
            and not declared.enabled_fn(self._last_shape)
        ):
            return False
        if now is None:
            now = time.monotonic()
        last_ran = self._last_ran.get(group)
        last_attempt = self._last_attempt.get(group)
        # Base due-ness: interval since last success (never-ran ⇒ always due).
        if last_ran is not None and (now - last_ran) < self.interval_for(group) * _GATE_TOLERANCE:
            return False
        # If the last attempt failed, space retries so failures don't hot-loop.
        if self._last_attempt_failed(last_ran, last_attempt):
            assert last_attempt is not None
            if (now - last_attempt) < self._failure_retry_seconds():
                return False
        self._last_attempt[group] = now
        return True

    def next_due(self, group: EndpointGroupName, now: float | None = None) -> float:
        """Absolute monotonic time the group next becomes due (fail-open ⇒ now).

        ``next_due = last_ran + interval×0.9``, floored at
        ``last_attempt + failure_retry_seconds`` when the last attempt failed.
        Never-succeeded groups are due now (subject to the failure-retry floor).
        """
        if now is None:
            now = time.monotonic()
        declared = self._groups.get(group)
        if declared is None or not declared.gated:
            return now
        last_ran = self._last_ran.get(group)
        last_attempt = self._last_attempt.get(group)
        base = now if last_ran is None else last_ran + self.interval_for(group) * _GATE_TOLERANCE
        if self._last_attempt_failed(last_ran, last_attempt):
            assert last_attempt is not None
            base = max(base, last_attempt + self._failure_retry_seconds())
        return base

    def seconds_until_due(
        self, groups: Iterable[EndpointGroupName], now: float | None = None
    ) -> float | None:
        """Seconds until the earliest gated, enabled group in ``groups`` is due.

        Skips disabled (#623) and ungated groups. Returns ``None`` when none of
        the given groups is schedulable (the collector's loop then just sleeps a
        resolve period and re-checks). Clamped at 0 for already-due groups.
        """
        if now is None:
            now = time.monotonic()
        best: float | None = None
        for group in groups:
            declared = self._groups.get(group)
            if declared is None or not declared.gated:
                continue
            if (
                declared.enabled_fn is not None
                and self._last_shape is not None
                and not declared.enabled_fn(self._last_shape)
            ):
                continue
            due = self.next_due(group, now)
            best = due if best is None else min(best, due)
        if best is None:
            return None
        return max(0.0, best - now)

    def mark_ran(self, group: EndpointGroupName, now: float | None = None) -> None:
        """Record a successful fetch (call only after success; failures retry)."""
        self._last_ran[group] = time.monotonic() if now is None else now

    def is_enabled(self, group: EndpointGroupName) -> bool:
        """True when the group is registered and enabled against the last shape.

        Fail-open pre-resolve (no shape yet) and for groups with no
        ``enabled_fn``; unregistered groups are ``False``.
        """
        declared = self._groups.get(group)
        if declared is None:
            return False
        if declared.enabled_fn is None or self._last_shape is None:
            return True
        return bool(declared.enabled_fn(self._last_shape))

    def ttl_seconds_for(self, group: EndpointGroupName) -> float:
        """Metric TTL for the group: interval × monitoring.metric_ttl_multiplier."""
        monitoring = getattr(self._settings, "monitoring", None)
        multiplier = float(getattr(monitoring, "metric_ttl_multiplier", 2.0))
        return self.interval_for(group) * multiplier

    def fastest_effective_interval_seconds(self) -> float:
        """Fastest current group interval across all registered groups.

        Load-bearing for liveness (3× this). Falls back to
        ``resolve_interval_seconds`` when no groups are registered.
        """
        if self._groups:
            return min(self.interval_for(name) for name in self._groups)
        return float(self._sched("resolve_interval_seconds"))

    # -- AIMD hysteresis ---------------------------------------------------------

    def needs_resolve(self) -> bool:
        """True when the AIMD-effective budget moved past the hysteresis band."""
        if str(self._sched("mode")) != "adaptive":
            return False
        if not bool(self._sched("aimd_enabled")):
            return False
        baseline = self._budget_used_at_last_solve
        if baseline is None or baseline <= 0:
            return True
        hysteresis = float(self._sched("aimd_resolve_hysteresis"))
        effective = self._effective_budget_rps()
        return abs(effective - baseline) / baseline > hysteresis

    # -- observability -------------------------------------------------------------

    def diagnostics(self) -> dict[str, Any]:
        """Structured snapshot for get_scheduling_diagnostics()/the /status page."""
        now = time.monotonic()
        groups: list[dict[str, Any]] = []
        for name in sorted(self._groups, key=str):
            declared = self._groups[name]
            solved = self._solved.get(name)
            last_ran = self._last_ran.get(name)
            groups.append({
                "name": str(name),
                "priority": declared.priority,
                "floor_seconds": float(declared.floor_seconds),
                "interval_seconds": self.interval_for(name),
                "stretch_factor": solved.stretch_factor if solved else 1.0,
                "pinned": solved.pinned if solved else False,
                "cost_per_cycle": solved.cost_per_cycle if solved else None,
                "demand_rps": solved.demand_rps if solved else None,
                "last_ran_ago_seconds": (now - last_ran) if last_ran is not None else None,
                # #623: True when always-enabled, no shape yet, or enabled against last shape.
                "enabled": (
                    declared.enabled_fn is None
                    or self._last_shape is None
                    or declared.enabled_fn(self._last_shape)
                ),
            })
        return {
            "mode": str(self._sched("mode")),
            "org_shape": asdict(self._last_shape) if self._last_shape is not None else None,
            "budget_rps": self.configured_budget_rps(),
            "effective_budget_rps": self._effective_budget_rps(),
            "target_utilization": float(self._sched("target_utilization")),
            "over_budget": self._over_budget,
            "total_demand_rps": self._total_demand_rps,
            "last_resolve_ts": self._last_resolve_ts,
            "groups": groups,
        }

    # -- metrics -----------------------------------------------------------------

    @classmethod
    def _init_metrics(cls) -> None:
        if cls._metrics_initialized:
            return
        cls._demand_gauge = Gauge(
            CollectorMetricName.SCHEDULER_ESTIMATED_DEMAND_RPS.value,
            "Estimated steady-state API demand per endpoint group in requests/second "
            "(computed schedule output, refreshed on each solver resolve; not a "
            "measured rate)",
            labelnames=[LabelName.GROUP.value],
        )
        cls._budget_gauge = Gauge(
            CollectorMetricName.SCHEDULER_BUDGET_RPS.value,
            "Configured API budget in requests/second (rate_limit_requests_per_second "
            "x rate_limit_shared_fraction; computed schedule input)",
        )
        cls._effective_budget_gauge = Gauge(
            CollectorMetricName.SCHEDULER_EFFECTIVE_BUDGET_RPS.value,
            "AIMD-adjusted effective API budget in requests/second (computed schedule "
            "input, lowered after 429 throttling and recovered additively)",
        )
        cls._utilization_gauge = Gauge(
            CollectorMetricName.SCHEDULER_BUDGET_UTILIZATION_RATIO.value,
            "Total estimated demand divided by the effective budget (computed "
            "schedule output, refreshed on each solver resolve)",
        )
        cls._interval_gauge = Gauge(
            CollectorMetricName.SCHEDULER_INTERVAL_SECONDS.value,
            "Solved collection interval per endpoint group in seconds (computed "
            "schedule output, refreshed on each solver resolve)",
            labelnames=[LabelName.GROUP.value],
        )
        cls._stretch_gauge = Gauge(
            CollectorMetricName.SCHEDULER_STRETCH_FACTOR.value,
            "Solved interval divided by the group's volatility floor; "
            "1.0 = unstretched (computed schedule output, refreshed on each "
            "solver resolve)",
            labelnames=[LabelName.GROUP.value],
        )
        cls._metrics_initialized = True

    def _emit_gauges(
        self, configured_budget: float, effective_budget: float, total_demand: float
    ) -> None:
        cls = type(self)
        if cls._budget_gauge is not None:
            cls._budget_gauge.set(configured_budget)
        if cls._effective_budget_gauge is not None:
            cls._effective_budget_gauge.set(effective_budget)
        if cls._utilization_gauge is not None:
            cls._utilization_gauge.set(
                total_demand / effective_budget if effective_budget > 0 else 0.0
            )
        for name, solved in self._solved.items():
            if cls._demand_gauge is not None:
                cls._demand_gauge.labels(group=str(name)).set(solved.demand_rps)
            if cls._interval_gauge is not None:
                cls._interval_gauge.labels(group=str(name)).set(solved.interval_seconds)
            if cls._stretch_gauge is not None:
                cls._stretch_gauge.labels(group=str(name)).set(solved.stretch_factor)
