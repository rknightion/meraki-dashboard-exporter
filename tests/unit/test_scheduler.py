"""Tests for the adaptive budget-aware endpoint scheduler (#617)."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import (
    EndpointGroup,
    EndpointGroupName,
    EndpointScheduler,
    OrgShape,
    SolvedInterval,
    pages,
    solve_intervals,
)

# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

# Every group name from the BUILD SPEC §2 endpoint-group table.
EXPECTED_GROUP_NAMES = [
    "mt_sensor_readings",
    "device_availability",
    "device_memory",
    "mr_wireless_clients",
    "mr_connection_stats",
    "mr_ethernet_status",
    "mr_packet_loss",
    "mr_cpu_load",
    "mr_ssid_status",
    "mr_ssid_usage",
    "ms_port_status",
    "ms_port_usage",
    "ms_packet_stats",
    "ms_port_overview",
    "ms_power",
    "ms_stacks",
    "ms_stp",
    "mx_uplink_status",
    "mx_uplink_health",
    "mx_uplink_usage",
    "mx_performance",
    "mx_ha",
    "mx_vpn",
    "mx_security_events",
    "mx_firewall_config",
    "mv_analytics",
    "mg_uplink_status",
    "nh_channel_utilization",
    "nh_connection_stats",
    "nh_data_rates",
    "nh_bluetooth",
    "nh_failed_connections",
    "nh_latency_stats",
    "nh_air_marshal",
    "org_availabilities",
    "org_availability_history",
    "org_api_usage",
    "org_client_overview",
    "org_device_model_overview",
    "org_packet_captures",
    "org_app_usage",
    "org_firmware",
    "org_licenses",
    "alerts_assurance",
    "alerts_sensor_overview",
    "mt_sensor_alerts",
    "clients_list",
    "clients_app_usage",
    "clients_signal_quality",
    "config_org",
    "inventory_warm",
    "org_metadata",
    # Phase 4 (#618)
    "mx_security_config",
    "mx_dhcp_subnets",
    "mx_vpn_config",
    "mx_nat_config",
    "mx_vlan_config",
    "mr_ssid_firewall",
    "mr_rf_profiles",
    "ms_dhcp_security",
    "ms_power_summary",
    "ms_link_aggregations",
    "org_config_templates",
    "org_adaptive_policy",
    "org_top_usage",
    "org_webhook_logs",
    "org_firmware_compliance",
    "mt_alert_profiles",
    "mt_relationships",
    "mv_sense_config",
    "mv_onboarding",
    "mg_cellular_config",
    "nh_mesh",
    # Phase 4B (#618)
    "mr_signal_quality",
    "mr_power_mode",
    "mr_wireless_controller",
    "mg_esims",
    "mg_ha",
    "mx_uplinks_overview",
    "insight_applications",
    "insight_app_health",
]


def _make_shape(
    *,
    networks: int = 10,
    wireless: int = 5,
    switch: int = 3,
    appliance: int = 3,
    sensor: int = 2,
    devices: int = 100,
    aps: int = 40,
    switches: int = 30,
    appliances: int = 10,
    physical_mx: int = 8,
    sensors: int = 10,
    cameras: int = 5,
) -> OrgShape:
    return OrgShape(
        org_id="123456",
        network_count=networks,
        wireless_network_count=wireless,
        switch_network_count=switch,
        appliance_network_count=appliance,
        sensor_network_count=sensor,
        camera_network_count=2,
        cellular_network_count=1,
        device_count=devices,
        ap_count=aps,
        switch_count=switches,
        appliance_count=appliances,
        physical_mx_count=physical_mx,
        camera_count=cameras,
        sensor_count=sensors,
        cellular_count=5,
    )


SMALL_SHAPE = _make_shape()  # 1 org / 10 nets / 100 devices

# LARGE per evidence/scale-and-capacity.md: 500 wireless networks / 5000 devices.
LARGE_SHAPE = _make_shape(
    networks=500,
    wireless=500,
    switch=150,
    appliance=100,
    sensor=50,
    devices=5000,
    aps=3000,
    switches=1200,
    appliances=400,
    physical_mx=350,
    sensors=300,
    cameras=100,
)

TIER_INTERVALS = {UpdateTier.FAST: 60, UpdateTier.MEDIUM: 300, UpdateTier.SLOW: 900}


def _representative_groups() -> list[EndpointGroup]:
    """Build a cross-priority, cross-tier slice of the §2 table (cost model included)."""
    return [
        EndpointGroup(
            name=EndpointGroupName.MT_SENSOR_READINGS,
            priority=2,
            floor_seconds=60,
            cost_fn=lambda s: 2 + pages(s.sensor_count, 100) - 1,
            tier=UpdateTier.FAST,
        ),
        EndpointGroup(
            name=EndpointGroupName.DEVICE_AVAILABILITY,
            priority=1,
            floor_seconds=120,
            cost_fn=lambda s: float(pages(s.device_count, 500)),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.DEVICE_MEMORY,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: float(pages(s.device_count, 20)),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_CHANNEL_UTILIZATION,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: float(s.wireless_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_DATA_RATES,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: float(s.wireless_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_BLUETOOTH,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: float(s.wireless_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_PERFORMANCE,
            priority=3,
            floor_seconds=900,
            cost_fn=lambda s: float(s.physical_mx_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_PORT_USAGE,
            priority=3,
            floor_seconds=600,
            cost_fn=lambda s: float(pages(s.switch_count, 50) + pages(s.switch_count, 20)),
            tier=UpdateTier.MEDIUM,
            setting_pin="ms_port_usage_interval",
        ),
        EndpointGroup(
            name=EndpointGroupName.MS_STP,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: float(s.switch_network_count),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.MX_FIREWALL_CONFIG,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: 2.0 * s.appliance_network_count,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_FIRMWARE,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.CONFIG_ORG,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: 3.0,
            tier=UpdateTier.SLOW,
        ),
        EndpointGroup(
            name=EndpointGroupName.INVENTORY_WARM,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda s: (
                2.0
                + pages(s.network_count, 1000)
                + pages(s.device_count, 1000)
                + (900 / 120) * pages(s.device_count, 500)
            ),
            tier=UpdateTier.SLOW,
            gated=False,
        ),
    ]


def _make_settings(
    *,
    mode: str = "adaptive",
    rps: float = 10.0,
    fraction: float = 0.8,
    overrides: dict[str, int] | None = None,
    api_fields_set: set[str] | None = None,
    ttl_multiplier: float = 2.0,
    aimd_enabled: bool = True,
    hysteresis: float = 0.2,
    **api_extra: Any,
) -> SimpleNamespace:
    api = SimpleNamespace(
        rate_limit_requests_per_second=rps,
        rate_limit_shared_fraction=fraction,
        model_fields_set=api_fields_set or set(),
        **api_extra,
    )
    return SimpleNamespace(
        api=api,
        update_intervals=SimpleNamespace(fast=60, medium=300, slow=900),
        monitoring=SimpleNamespace(metric_ttl_multiplier=ttl_multiplier),
        scheduler=SimpleNamespace(
            mode=mode,
            target_utilization=0.7,
            max_stretch_factor=4.0,
            max_interval_seconds=3600,
            resolve_interval_seconds=900,
            aimd_enabled=aimd_enabled,
            aimd_backoff_multiplier=0.5,
            aimd_recovery_rps_per_minute=0.1,
            aimd_resolve_hysteresis=hysteresis,
            group_interval_overrides=overrides or {},
        ),
    )


class _FakeRateLimiter:
    """Rate limiter test double exposing the frozen AIMD read seam."""

    def __init__(self, configured: float = 8.0, effective: float | None = None) -> None:
        self._configured = configured
        self.effective = effective if effective is not None else configured

    def effective_rate_per_second(self) -> float:
        """Return the (mutable) AIMD-adjusted rate."""
        return self.effective

    def configured_rate_per_second(self) -> float:
        """Return the configured rate."""
        return self._configured


def _make_scheduler(
    settings: SimpleNamespace | None = None,
    rate_limiter: _FakeRateLimiter | None = None,
    groups: list[EndpointGroup] | None = None,
) -> EndpointScheduler:
    settings = settings or _make_settings()
    rate_limiter = rate_limiter or _FakeRateLimiter(
        configured=settings.api.rate_limit_requests_per_second
        * settings.api.rate_limit_shared_fraction
    )
    sched = EndpointScheduler(settings, rate_limiter)  # type: ignore[arg-type]
    sched.register_groups(groups if groups is not None else _representative_groups())
    return sched


# ---------------------------------------------------------------------------
# EndpointGroupName / pages
# ---------------------------------------------------------------------------


class TestEndpointGroupName:
    """The enum must carry every §2 table group with wire value == name."""

    def test_every_spec_group_present_with_wire_value_equal_to_name(self) -> None:
        """Each spec name resolves to a member whose value equals the name."""
        for name in EXPECTED_GROUP_NAMES:
            member = EndpointGroupName(name)
            assert member.value == name
            assert member.name.lower() == name

    def test_no_extra_members(self) -> None:
        """The enum holds exactly the spec set, nothing else."""
        assert {m.value for m in EndpointGroupName} == set(EXPECTED_GROUP_NAMES)


class TestPages:
    """Pagination helper semantics."""

    @pytest.mark.parametrize(
        ("n", "per_page", "expected"),
        [(0, 100, 1), (1, 100, 1), (100, 100, 1), (101, 100, 2), (5000, 20, 250)],
    )
    def test_pages(self, n: int, per_page: int, expected: int) -> None:
        """pages() is max(1, ceil(n / per_page))."""
        assert pages(n, per_page) == expected


# ---------------------------------------------------------------------------
# Pure solver
# ---------------------------------------------------------------------------


class TestSolveIntervals:
    """Frozen deterministic algorithm of solve_intervals()."""

    def solve(
        self,
        shape: OrgShape,
        *,
        groups: list[EndpointGroup] | None = None,
        budget: float = 8.0,
        target: float = 0.7,
        overrides: dict[str, int] | None = None,
        max_stretch: float = 4.0,
        max_interval: float = 3600.0,
    ) -> dict[EndpointGroupName, SolvedInterval]:
        """Call solve_intervals with test defaults."""
        return solve_intervals(
            groups if groups is not None else _representative_groups(),
            shape,
            budget,
            target,
            TIER_INTERVALS,
            overrides or {},
            max_stretch,
            max_interval,
        )

    def test_small_shape_fits_budget_without_stretching(self) -> None:
        """SMALL shape demand fits: every interval stays at max(floor, heartbeat)."""
        solved = self.solve(SMALL_SHAPE)
        groups = {g.name: g for g in _representative_groups()}
        total_demand = sum(s.demand_rps for s in solved.values())
        assert total_demand <= 8.0 * 0.7
        for name, s in solved.items():
            g = groups[name]
            base = max(g.floor_seconds, TIER_INTERVALS[g.tier])
            assert s.interval_seconds == base
            assert s.stretch_factor == 1.0
            assert not s.pinned

    def test_small_shape_cost_and_demand_fields(self) -> None:
        """SolvedInterval carries cost_per_cycle and demand_rps = cost/interval."""
        solved = self.solve(SMALL_SHAPE)
        avail = solved[EndpointGroupName.DEVICE_AVAILABILITY]
        # pages(100, 500) == 1 call/cycle at the MEDIUM heartbeat 300s
        assert avail.cost_per_cycle == 1.0
        assert avail.interval_seconds == 300.0
        assert avail.demand_rps == pytest.approx(1.0 / 300.0)

    def test_large_shape_stretches_to_fit_budget(self) -> None:
        """LARGE shape overshoots the budget; solver stretches until demand fits."""
        solved = self.solve(LARGE_SHAPE)
        total_demand = sum(s.demand_rps for s in solved.values())
        assert total_demand <= 8.0 * 0.7
        assert any(s.stretch_factor > 1.0 for s in solved.values())

    def test_large_shape_stretches_priority4_before_priority3(self) -> None:
        """If any priority-3 group stretched, all gated priority-4 groups are at cap."""
        solved = self.solve(LARGE_SHAPE)
        groups = {g.name: g for g in _representative_groups()}
        p3_stretched = any(
            solved[n].stretch_factor > 1.0 for n, g in groups.items() if g.priority == 3
        )
        if p3_stretched:
            for name, g in groups.items():
                if g.priority == 4 and g.gated:
                    cap = min(g.floor_seconds * 4.0, 3600.0)
                    assert solved[name].interval_seconds == pytest.approx(cap)

    def test_priority1_never_stretched_while_lower_priorities_have_headroom(self) -> None:
        """Up-ness (priority 1) keeps its natural cadence at LARGE scale."""
        solved = self.solve(LARGE_SHAPE)
        assert solved[EndpointGroupName.DEVICE_AVAILABILITY].stretch_factor == 1.0

    def test_ungated_groups_count_toward_demand_but_never_stretch(self) -> None:
        """gated=False groups contribute demand but are never stretch candidates."""
        solved = self.solve(LARGE_SHAPE)
        inv = solved[EndpointGroupName.INVENTORY_WARM]
        assert inv.stretch_factor == 1.0
        assert inv.demand_rps > 0.0

    def test_determinism_identical_inputs_identical_output(self) -> None:
        """Same inputs produce a byte-identical output map."""
        a = self.solve(LARGE_SHAPE)
        b = self.solve(LARGE_SHAPE)
        assert a == b

    def test_over_budget_all_groups_capped(self) -> None:
        """A tiny budget drives every gated group with headroom to its cap."""
        solved = self.solve(LARGE_SHAPE, budget=0.001)
        groups = {g.name: g for g in _representative_groups()}
        for name, g in groups.items():
            if not g.gated:
                continue
            cap = min(g.floor_seconds * 4.0, 3600.0)
            base = max(g.floor_seconds, TIER_INTERVALS[g.tier])
            if base < cap:
                assert solved[name].interval_seconds == pytest.approx(cap)
            else:
                assert solved[name].interval_seconds == base
        total_demand = sum(s.demand_rps for s in solved.values())
        assert total_demand > 0.001 * 0.7

    def test_override_pins_group_exactly_and_excludes_from_stretching(self) -> None:
        """An override sets the interval exactly and marks the group pinned."""
        solved = self.solve(LARGE_SHAPE, overrides={"nh_data_rates": 450})
        pinned = solved[EndpointGroupName.NH_DATA_RATES]
        assert pinned.pinned
        assert pinned.interval_seconds == 450.0

    def test_pin_below_floor_honoured(self) -> None:
        """Spec: a pin below the floor is honoured (with a WARNING log), not clamped."""
        solved = self.solve(SMALL_SHAPE, overrides={"mx_performance": 400})
        s = solved[EndpointGroupName.MX_PERFORMANCE]
        assert s.pinned
        assert s.interval_seconds == 400.0  # below the 900s floor, honoured

    def test_pin_below_heartbeat_clamped_to_heartbeat(self) -> None:
        """A pin faster than the tier heartbeat is clamped up to the heartbeat."""
        solved = self.solve(SMALL_SHAPE, overrides={"nh_data_rates": 30})
        s = solved[EndpointGroupName.NH_DATA_RATES]
        assert s.pinned
        assert s.interval_seconds == 300.0  # MEDIUM heartbeat

    def test_interval_never_below_tier_heartbeat(self) -> None:
        """A floor faster than the heartbeat is lifted to the heartbeat."""
        group = EndpointGroup(
            name=EndpointGroupName.MG_UPLINK_STATUS,
            priority=1,
            floor_seconds=60,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        )
        solved = self.solve(SMALL_SHAPE, groups=[group])
        assert solved[EndpointGroupName.MG_UPLINK_STATUS].interval_seconds == 300.0

    def test_stretch_respects_max_interval_cap(self) -> None:
        """cap = min(floor x max_stretch, max_interval): the absolute cap wins here."""
        group = EndpointGroup(
            name=EndpointGroupName.NH_AIR_MARSHAL,
            priority=3,
            floor_seconds=3600,
            cost_fn=lambda s: 10_000.0,
            tier=UpdateTier.MEDIUM,
        )
        solved = self.solve(SMALL_SHAPE, groups=[group], budget=0.001)
        assert solved[EndpointGroupName.NH_AIR_MARSHAL].interval_seconds == 3600.0

    def test_stretch_multiplier_is_1_5x_steps(self) -> None:
        """Each stretch round multiplies the chosen group's interval by 1.5."""
        group = EndpointGroup(
            name=EndpointGroupName.ORG_LICENSES,
            priority=4,
            floor_seconds=300,
            cost_fn=lambda s: 300.0,  # 1 rps at floor
            tier=UpdateTier.MEDIUM,
        )
        # target = 0.9 * 0.8 = 0.72 rps -> one 1.5x stretch (300 -> 450 = 0.667 rps) fits
        solved = self.solve(SMALL_SHAPE, groups=[group], budget=0.9, target=0.8)
        assert solved[EndpointGroupName.ORG_LICENSES].interval_seconds == pytest.approx(450.0)
        assert solved[EndpointGroupName.ORG_LICENSES].stretch_factor == pytest.approx(1.5)

    def test_empty_groups(self) -> None:
        """No groups: empty result, no crash."""
        assert self.solve(SMALL_SHAPE, groups=[]) == {}


# ---------------------------------------------------------------------------
# EndpointScheduler
# ---------------------------------------------------------------------------


class TestEndpointSchedulerRegistration:
    """register_groups() and unknown-group handling."""

    def test_duplicate_registration_rejected(self) -> None:
        """Registering the same group twice raises (catches cross-lane collisions)."""
        sched = _make_scheduler(groups=[])
        groups = _representative_groups()
        sched.register_groups(groups[:1])
        with pytest.raises(ValueError, match="duplicate"):
            sched.register_groups(groups[:1])

    def test_interval_for_unknown_group_raises(self) -> None:
        """interval_for() on an unregistered group raises KeyError."""
        sched = _make_scheduler(groups=[])
        with pytest.raises(KeyError):
            sched.interval_for(EndpointGroupName.MV_ANALYTICS)


class TestEndpointSchedulerResolve:
    """resolve() semantics: solving, modes, pins, gauges."""

    def test_pre_resolve_interval_is_floor_or_heartbeat(self) -> None:
        """Before the first resolve, interval_for = max(floor, tier heartbeat)."""
        sched = _make_scheduler()
        assert sched.interval_for(EndpointGroupName.MT_SENSOR_READINGS) == 60.0
        assert sched.interval_for(EndpointGroupName.MX_PERFORMANCE) == 900.0
        assert sched.interval_for(EndpointGroupName.DEVICE_AVAILABILITY) == 300.0

    def test_resolve_small_keeps_floors(self) -> None:
        """SMALL shape resolve keeps floors and reports under-budget."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        assert sched.interval_for(EndpointGroupName.NH_DATA_RATES) == 300.0
        diag = sched.diagnostics()
        assert diag["over_budget"] is False
        assert diag["total_demand_rps"] <= 8.0 * 0.7

    def test_resolve_large_stretches_and_reports(self) -> None:
        """LARGE shape resolve stretches groups and lands within budget."""
        sched = _make_scheduler()
        sched.resolve(LARGE_SHAPE)
        diag = sched.diagnostics()
        assert diag["over_budget"] is False
        assert diag["total_demand_rps"] <= 8.0 * 0.7
        stretched = [g for g in diag["groups"] if g["stretch_factor"] > 1.0]
        assert stretched

    def test_resolve_over_budget_flag(self) -> None:
        """When even fully-capped intervals exceed budget, over_budget=True."""
        settings = _make_settings(rps=0.01, fraction=1.0)
        sched = _make_scheduler(settings=settings, rate_limiter=_FakeRateLimiter(0.01))
        sched.resolve(LARGE_SHAPE)
        assert sched.diagnostics()["over_budget"] is True

    def test_fixed_mode_floors_and_pins_only(self) -> None:
        """Fixed mode applies steps 1-2 only: no stretching even when over budget."""
        settings = _make_settings(mode="fixed", overrides={"nh_data_rates": 600})
        sched = _make_scheduler(settings=settings)
        sched.resolve(LARGE_SHAPE)  # demand hugely over budget - must NOT stretch
        diag = sched.diagnostics()
        for g in diag["groups"]:
            if g["name"] == "nh_data_rates":
                assert g["interval_seconds"] == 600.0
                assert g["pinned"] is True
            else:
                assert g["stretch_factor"] == 1.0

    def test_setting_pin_applies_when_operator_set(self) -> None:
        """A legacy APISettings gate explicitly set by the operator pins the group."""
        settings = _make_settings(
            api_fields_set={"ms_port_usage_interval"},
            ms_port_usage_interval=1200,
        )
        sched = _make_scheduler(settings=settings)
        sched.resolve(SMALL_SHAPE)
        assert sched.interval_for(EndpointGroupName.MS_PORT_USAGE) == 1200.0
        entry = next(g for g in sched.diagnostics()["groups"] if g["name"] == "ms_port_usage")
        assert entry["pinned"] is True

    def test_setting_pin_ignored_when_left_default(self) -> None:
        """A legacy gate left at its default does not pin (floor applies)."""
        settings = _make_settings(ms_port_usage_interval=600)  # not in model_fields_set
        sched = _make_scheduler(settings=settings)
        sched.resolve(SMALL_SHAPE)
        entry = next(g for g in sched.diagnostics()["groups"] if g["name"] == "ms_port_usage")
        assert entry["pinned"] is False

    def test_explicit_group_override_wins_over_setting_pin(self) -> None:
        """scheduler.group_interval_overrides beats a legacy setting_pin."""
        settings = _make_settings(
            overrides={"ms_port_usage": 1800},
            api_fields_set={"ms_port_usage_interval"},
            ms_port_usage_interval=1200,
        )
        sched = _make_scheduler(settings=settings)
        sched.resolve(SMALL_SHAPE)
        assert sched.interval_for(EndpointGroupName.MS_PORT_USAGE) == 1800.0

    def test_resolve_emits_gauges(self) -> None:
        """resolve() sets the SCHEDULER_* gauges (budget, interval, utilization)."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        assert EndpointScheduler._budget_gauge is not None
        assert EndpointScheduler._budget_gauge._value.get() == pytest.approx(8.0)
        assert EndpointScheduler._interval_gauge is not None
        child = EndpointScheduler._interval_gauge.labels(group="nh_data_rates")
        assert child._value.get() == 300.0
        assert EndpointScheduler._utilization_gauge is not None
        assert EndpointScheduler._utilization_gauge._value.get() > 0.0


class TestGateSemantics:
    """should_run()/mark_ran() gate behavior."""

    def test_never_ran_group_should_run(self) -> None:
        """A group that never ran is always due (restart => refetch once)."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        assert sched.should_run(EndpointGroupName.NH_DATA_RATES) is True

    def test_gate_timing_with_explicit_now(self) -> None:
        """Gate opens at interval x 0.9 after the last successful run."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        g = EndpointGroupName.NH_DATA_RATES  # interval 300
        sched.mark_ran(g, now=1000.0)
        assert sched.should_run(g, now=1000.0 + 100.0) is False
        # 10% tolerance: runs again at >= 270s
        assert sched.should_run(g, now=1000.0 + 269.9) is False
        assert sched.should_run(g, now=1000.0 + 270.0) is True

    def test_ungated_group_always_runs(self) -> None:
        """gated=False groups are demand-accounting only; should_run always True."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        g = EndpointGroupName.INVENTORY_WARM
        sched.mark_ran(g, now=1000.0)
        assert sched.should_run(g, now=1000.1) is True

    def test_unregistered_group_fails_open(self) -> None:
        """An unregistered group never blocks collection (fail-open)."""
        sched = _make_scheduler(groups=[])
        assert sched.should_run(EndpointGroupName.MV_ANALYTICS) is True

    def test_failed_fetch_not_marked_retries_next_heartbeat(self) -> None:
        """mark_ran is only called on success, so failures stay due."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        g = EndpointGroupName.NH_DATA_RATES
        # never mark_ran (fetch failed) -> still runnable immediately
        assert sched.should_run(g, now=5.0) is True


class TestTtlAndFastest:
    """ttl_seconds_for() and fastest_effective_interval_seconds()."""

    def test_ttl_seconds_for_is_interval_times_multiplier(self) -> None:
        """TTL = interval x monitoring.metric_ttl_multiplier."""
        sched = _make_scheduler(settings=_make_settings(ttl_multiplier=2.0))
        sched.resolve(SMALL_SHAPE)
        assert sched.ttl_seconds_for(EndpointGroupName.MX_PERFORMANCE) == 1800.0
        assert sched.ttl_seconds_for(EndpointGroupName.NH_DATA_RATES) == 600.0

    def test_ttl_tracks_stretched_interval(self) -> None:
        """TTL follows the SOLVED (possibly stretched) interval, not the floor."""
        sched = _make_scheduler()
        sched.resolve(LARGE_SHAPE)
        for g in _representative_groups():
            ttl = sched.ttl_seconds_for(g.name)
            assert ttl == pytest.approx(sched.interval_for(g.name) * 2.0)

    def test_fastest_effective_interval(self) -> None:
        """Fastest interval across groups (FAST-tier MT readings at 60s here)."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        assert sched.fastest_effective_interval_seconds() == 60.0

    def test_fastest_effective_interval_no_groups(self) -> None:
        """With no groups registered, fall back to the fastest tier heartbeat."""
        sched = _make_scheduler(groups=[])
        assert sched.fastest_effective_interval_seconds() == 60.0


class TestNeedsResolve:
    """AIMD hysteresis on needs_resolve()."""

    def test_never_resolved_needs_resolve(self) -> None:
        """Before the first resolve, a resolve is needed."""
        sched = _make_scheduler()
        assert sched.needs_resolve() is True

    def test_no_budget_movement_no_resolve(self) -> None:
        """Effective budget unchanged since last solve: no re-solve."""
        rl = _FakeRateLimiter(8.0)
        sched = _make_scheduler(rate_limiter=rl)
        sched.resolve(SMALL_SHAPE)
        assert sched.needs_resolve() is False

    def test_aimd_backoff_beyond_hysteresis_triggers_resolve(self) -> None:
        """A halved effective budget (|4-8|/8 = 0.5 > 0.2) triggers a re-solve."""
        rl = _FakeRateLimiter(8.0)
        sched = _make_scheduler(rate_limiter=rl)
        sched.resolve(SMALL_SHAPE)
        rl.effective = 4.0
        assert sched.needs_resolve() is True

    def test_movement_within_hysteresis_no_resolve(self) -> None:
        """Movement inside the band (|7-8|/8 = 0.125 <= 0.2) does not re-solve."""
        rl = _FakeRateLimiter(8.0)
        sched = _make_scheduler(rate_limiter=rl)
        sched.resolve(SMALL_SHAPE)
        rl.effective = 7.0
        assert sched.needs_resolve() is False

    def test_fixed_mode_disables_aimd_resolve(self) -> None:
        """Fixed mode disables AIMD entirely."""
        sched = _make_scheduler(settings=_make_settings(mode="fixed"))
        assert sched.needs_resolve() is False

    def test_aimd_disabled_disables_resolve(self) -> None:
        """aimd_enabled=False disables hysteresis-driven re-solves."""
        sched = _make_scheduler(settings=_make_settings(aimd_enabled=False))
        assert sched.needs_resolve() is False


class TestDiagnostics:
    """diagnostics() snapshot for /status and get_scheduling_diagnostics()."""

    def test_diagnostics_shape(self) -> None:
        """The snapshot carries the frozen top-level and per-group keys."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        sched.mark_ran(EndpointGroupName.NH_DATA_RATES)
        diag = sched.diagnostics()
        for key in (
            "mode",
            "org_shape",
            "budget_rps",
            "effective_budget_rps",
            "target_utilization",
            "over_budget",
            "total_demand_rps",
            "last_resolve_ts",
            "groups",
        ):
            assert key in diag
        assert diag["mode"] == "adaptive"
        assert diag["org_shape"]["org_id"] == "123456"
        assert diag["budget_rps"] == pytest.approx(8.0)
        entry = next(g for g in diag["groups"] if g["name"] == "nh_data_rates")
        for key in (
            "name",
            "priority",
            "tier",
            "floor_seconds",
            "interval_seconds",
            "stretch_factor",
            "pinned",
            "cost_per_cycle",
            "demand_rps",
            "last_ran_ago_seconds",
            "enabled",
        ):
            assert key in entry
        assert entry["last_ran_ago_seconds"] is not None
        never_ran = next(g for g in diag["groups"] if g["name"] == "org_firmware")
        assert never_ran["last_ran_ago_seconds"] is None

    def test_diagnostics_before_resolve(self) -> None:
        """Pre-resolve diagnostics report no shape/ts but still list groups."""
        sched = _make_scheduler()
        diag = sched.diagnostics()
        assert diag["org_shape"] is None
        assert diag["last_resolve_ts"] is None
        assert diag["groups"]  # groups listed with pre-resolve intervals

    def test_diagnostics_groups_sorted_by_name(self) -> None:
        """Group entries are sorted by name (deterministic rendering)."""
        sched = _make_scheduler()
        sched.resolve(SMALL_SHAPE)
        names = [g["name"] for g in sched.diagnostics()["groups"]]
        assert names == sorted(names)


class TestOrgShape:
    """OrgShape dataclass properties and solver output sanity."""

    def test_frozen(self) -> None:
        """OrgShape is immutable."""
        with pytest.raises(AttributeError):
            SMALL_SHAPE.device_count = 5  # type: ignore[misc]

    def test_math_isfinite_solver_outputs(self) -> None:
        """All solved intervals/demands are finite numbers."""
        solved = solve_intervals(
            _representative_groups(),
            LARGE_SHAPE,
            8.0,
            0.7,
            TIER_INTERVALS,
            {},
            4.0,
            3600.0,
        )
        for s in solved.values():
            assert math.isfinite(s.interval_seconds)
            assert math.isfinite(s.demand_rps)

    def test_new_phase4b_orgshape_fields_default_zero(self) -> None:
        """Existing keyword constructors omit the 4B fields; they default to 0."""
        assert SMALL_SHAPE.catalyst_ap_count == 0
        assert SMALL_SHAPE.signal_quality_ap_count == 0


class TestEnabledFnGating:
    """#623: enabled_fn disables a group's demand + run-gate without deregistering it."""

    @staticmethod
    def _sensor_group() -> EndpointGroup:
        return EndpointGroup(
            name=EndpointGroupName.MT_SENSOR_READINGS,
            priority=2,
            floor_seconds=60,
            cost_fn=lambda s: 5.0,
            tier=UpdateTier.FAST,
            enabled_fn=lambda s: s.sensor_count > 0,
        )

    def test_disabled_group_zero_cost_and_demand(self) -> None:
        """A disabled group contributes zero cost/demand and stays at base interval."""
        g = self._sensor_group()
        solved = solve_intervals(
            [g], _make_shape(sensors=0), 8.0, 0.7, TIER_INTERVALS, {}, 4.0, 3600.0
        )
        s = solved[g.name]
        assert s.cost_per_cycle == 0.0
        assert s.demand_rps == 0.0
        assert s.interval_seconds == 60.0  # max(floor=60, FAST heartbeat=60)
        assert s.stretch_factor == 1.0

    def test_enabled_group_normal_cost(self) -> None:
        """The same group with sensors present contributes its cost_fn demand."""
        g = self._sensor_group()
        solved = solve_intervals(
            [g], _make_shape(sensors=10), 8.0, 0.7, TIER_INTERVALS, {}, 4.0, 3600.0
        )
        assert solved[g.name].cost_per_cycle == 5.0

    def test_disabled_group_interval_no_flap_under_tight_budget(self) -> None:
        """Even under a starved budget a disabled group never stretches (stays at base)."""
        g_disabled = self._sensor_group()  # enabled_fn False when sensors=0
        g_hungry = EndpointGroup(
            name=EndpointGroupName.MR_CPU_LOAD,
            priority=4,
            floor_seconds=300,
            cost_fn=lambda s: 100.0,
            tier=UpdateTier.MEDIUM,
        )
        solved = solve_intervals(
            [g_disabled, g_hungry],
            _make_shape(sensors=0),
            0.1,
            0.7,
            TIER_INTERVALS,
            {},
            4.0,
            3600.0,
        )
        assert solved[g_disabled.name].interval_seconds == 60.0
        assert solved[g_disabled.name].stretch_factor == 1.0
        # the enabled hungry group DID absorb the stretch pressure
        assert solved[g_hungry.name].stretch_factor > 1.0

    def test_should_run_false_when_disabled(self) -> None:
        """should_run is False for a disabled group post-resolve (never fetched)."""
        sched = _make_scheduler(groups=[self._sensor_group()])
        sched.resolve(_make_shape(sensors=0))
        assert sched.should_run(EndpointGroupName.MT_SENSOR_READINGS) is False

    def test_should_run_true_when_enabled(self) -> None:
        """should_run is True (never-ran) once the group is enabled by shape."""
        sched = _make_scheduler(groups=[self._sensor_group()])
        sched.resolve(_make_shape(sensors=10))
        assert sched.should_run(EndpointGroupName.MT_SENSOR_READINGS) is True

    def test_re_enables_after_resolve_with_new_shape(self) -> None:
        """A later resolve with a re-enabling shape makes the group due immediately."""
        sched = _make_scheduler(groups=[self._sensor_group()])
        sched.resolve(_make_shape(sensors=0))
        assert sched.should_run(EndpointGroupName.MT_SENSOR_READINGS) is False
        sched.resolve(_make_shape(sensors=4))
        assert sched.should_run(EndpointGroupName.MT_SENSOR_READINGS) is True

    def test_fail_open_pre_resolve(self) -> None:
        """No shape yet (never resolved) => enabled_fn is not consulted; group runs."""
        sched = _make_scheduler(groups=[self._sensor_group()])
        assert sched.should_run(EndpointGroupName.MT_SENSOR_READINGS) is True

    def test_diagnostics_enabled_flag_tracks_shape(self) -> None:
        """diagnostics()['groups'][i]['enabled'] reflects enabled_fn vs last shape."""
        sched = _make_scheduler(groups=[self._sensor_group()])
        sched.resolve(_make_shape(sensors=0))
        entry = next(g for g in sched.diagnostics()["groups"] if g["name"] == "mt_sensor_readings")
        assert entry["enabled"] is False
        sched.resolve(_make_shape(sensors=3))
        entry = next(g for g in sched.diagnostics()["groups"] if g["name"] == "mt_sensor_readings")
        assert entry["enabled"] is True

    def test_diagnostics_enabled_true_pre_resolve(self) -> None:
        """Pre-resolve (no shape) the enabled flag is True (fail-open)."""
        sched = _make_scheduler(groups=[self._sensor_group()])
        entry = next(g for g in sched.diagnostics()["groups"] if g["name"] == "mt_sensor_readings")
        assert entry["enabled"] is True

    def test_always_enabled_group_reports_enabled(self) -> None:
        """A group with enabled_fn=None is always enabled."""
        g = EndpointGroup(
            name=EndpointGroupName.NH_DATA_RATES,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda s: 1.0,
            tier=UpdateTier.MEDIUM,
        )
        sched = _make_scheduler(groups=[g])
        sched.resolve(_make_shape(sensors=0))
        entry = next(x for x in sched.diagnostics()["groups"] if x["name"] == "nh_data_rates")
        assert entry["enabled"] is True
        assert sched.should_run(EndpointGroupName.NH_DATA_RATES) is True
