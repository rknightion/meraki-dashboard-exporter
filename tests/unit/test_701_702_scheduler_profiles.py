"""Scheduler profile and staleness contracts for #701/#702."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY, generate_latest

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.collectors.alerts import AlertsCollector
from meraki_dashboard_exporter.collectors.config import ConfigCollector
from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.collectors.mt_alerts import MTSensorAlertsCollector
from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.error_handling import StartupConfigurationError
from meraki_dashboard_exporter.core.scheduler import (
    EndpointGroup,
    EndpointGroupName,
    EndpointScheduler,
    OrgShape,
    solve_intervals,
)
from tests.fixtures.fleet import FleetPreset, build_fleet


def _shape(*, networks: int, devices: int) -> OrgShape:
    return OrgShape(
        org_id="fixture",
        network_count=networks,
        wireless_network_count=networks,
        switch_network_count=networks,
        appliance_network_count=networks,
        sensor_network_count=0,
        camera_network_count=0,
        cellular_network_count=0,
        device_count=devices,
        ap_count=devices,
        switch_count=devices,
        appliance_count=0,
        physical_mx_count=0,
        camera_count=0,
        sensor_count=0,
        cellular_count=0,
    )


def _settings(
    profile: str | None = None, *, rps: float = 1.0, mode: str = "adaptive"
) -> SimpleNamespace:
    return SimpleNamespace(
        api=SimpleNamespace(rate_limit_requests_per_second=rps, rate_limit_shared_fraction=1.0),
        monitoring=SimpleNamespace(metric_ttl_multiplier=2.0),
        collectors=SimpleNamespace(profile=profile),
        scheduler=SimpleNamespace(
            mode=mode,
            target_utilization=0.7,
            max_stretch_factor=4.0,
            max_interval_seconds=3600,
            resolve_interval_seconds=900,
            aimd_enabled=False,
            aimd_resolve_hysteresis=0.2,
            group_interval_overrides={},
            failure_retry_seconds=300,
        ),
    )


class _Limiter:
    def __init__(self, rps: float = 1.0) -> None:
        self.rps = rps

    def effective_rate_per_second(self) -> float:
        return self.rps


def _fixture_shape(preset: FleetPreset) -> OrgShape:
    """Translate the #707 fixture's real topology counts into scheduler shape."""
    fleet = build_fleet(preset)
    networks = [network for values in fleet.networks_by_org.values() for network in values]
    devices = [device for values in fleet.devices_by_org.values() for device in values]
    family_counts = {
        family: sum(str(device["model"]).startswith(family) for device in devices)
        for family in ("MR", "MS", "MX", "MT", "MV", "MG")
    }
    return OrgShape(
        org_id=str(fleet.organizations[0]["id"]),
        network_count=len(networks),
        wireless_network_count=sum("wireless" in network["productTypes"] for network in networks),
        switch_network_count=sum("switch" in network["productTypes"] for network in networks),
        appliance_network_count=sum("appliance" in network["productTypes"] for network in networks),
        sensor_network_count=sum("sensor" in network["productTypes"] for network in networks),
        camera_network_count=sum("camera" in network["productTypes"] for network in networks),
        cellular_network_count=sum(
            "cellularGateway" in network["productTypes"] for network in networks
        ),
        device_count=len(devices),
        ap_count=family_counts["MR"],
        switch_count=family_counts["MS"],
        appliance_count=family_counts["MX"],
        physical_mx_count=family_counts["MX"],
        camera_count=family_counts["MV"],
        sensor_count=family_counts["MT"],
        cellular_count=family_counts["MG"],
    )


def _fixture_groups() -> list[EndpointGroup]:
    """Return registered default collector groups without inventing a device mix."""
    return [
        group
        for collector in (
            AlertsCollector,
            ConfigCollector,
            DeviceCollector,
            MTSensorAlertsCollector,
            MTSensorCollector,
            NetworkHealthCollector,
            OrganizationCollector,
        )
        for group in collector.endpoint_groups
    ]


def _groups() -> list[EndpointGroup]:
    return [
        EndpointGroup(EndpointGroupName.DEVICE_AVAILABILITY, 1, 60, lambda _: 30.0),
        EndpointGroup(EndpointGroupName.MT_SENSOR_READINGS, 2, 60, lambda _: 30.0),
        EndpointGroup(EndpointGroupName.NH_DATA_RATES, 3, 60, lambda _: 30.0),
        EndpointGroup(EndpointGroupName.CONFIG_ORG, 4, 60, lambda _: 30.0),
    ]


def test_priority_one_and_two_keep_floors_while_lower_priorities_stretch() -> None:
    """Priority 1/2 never pay for pressure caused by lower priorities."""
    solved = solve_intervals(_groups(), _shape(networks=750, devices=4500), 1.0, 0.7, {}, 4.0, 3600)
    assert solved[EndpointGroupName.DEVICE_AVAILABILITY].interval_seconds == 60
    assert solved[EndpointGroupName.MT_SENSOR_READINGS].interval_seconds == 60
    assert solved[EndpointGroupName.NH_DATA_RATES].stretch_factor > 1
    assert solved[EndpointGroupName.CONFIG_ORG].stretch_factor > 1


@pytest.mark.parametrize("preset", [FleetPreset.BRANCH_RETAIL, FleetPreset.CAMPUS])
def test_threshold_is_solved_plan_demand_not_network_count(
    preset: FleetPreset,
) -> None:
    """Named fixtures prove the threshold follows solved demand, not count."""
    # A deliberately shared 0.5 rps budget crosses the solved-plan threshold for
    # both named topologies without inventing a device-family mix.
    scheduler = EndpointScheduler(_settings(rps=0.5), _Limiter(0.5))  # type: ignore[arg-type]
    scheduler.register_groups(_fixture_groups())
    scheduler.resolve(_fixture_shape(preset))
    assert scheduler.requires_explicit_profile() is True
    assert scheduler.diagnostics()["profile"]["threshold_demand_rps"] > 0.35


def test_fixed_mode_never_requires_an_explicit_profile() -> None:
    """D6 is an adaptive-scheduler guard, not a fixed-mode startup gate."""
    scheduler = EndpointScheduler(_settings(rps=0.5, mode="fixed"), _Limiter(0.5))  # type: ignore[arg-type]
    scheduler.register_groups(_fixture_groups())
    scheduler.resolve(_fixture_shape(FleetPreset.BRANCH_RETAIL))

    assert scheduler.diagnostics()["profile"]["threshold_demand_rps"] > 0.35
    assert scheduler.requires_explicit_profile() is False


def test_unset_profile_keeps_full_surface_below_threshold() -> None:
    """An affordable implicit profile preserves every endpoint priority."""
    scheduler = EndpointScheduler(_settings(rps=100.0), _Limiter(100.0))  # type: ignore[arg-type]
    scheduler.register_groups(_groups())
    scheduler.resolve(_shape(networks=1, devices=1))

    assert scheduler.requires_explicit_profile() is False
    assert scheduler.active_profile() == "full"
    assert scheduler.profile_allows(EndpointGroupName.CONFIG_ORG)


def test_implicit_full_plan_gates_when_standard_would_fit() -> None:
    """The threshold measures the plan that an unset profile would actually run."""
    groups = [
        EndpointGroup(EndpointGroupName.DEVICE_AVAILABILITY, 1, 60, lambda _: 12.0),
        EndpointGroup(EndpointGroupName.NH_DATA_RATES, 3, 60, lambda _: 12.0),
        EndpointGroup(EndpointGroupName.CONFIG_ORG, 4, 60, lambda _: 120.0),
    ]
    scheduler = EndpointScheduler(_settings(rps=1.0), _Limiter(1.0))  # type: ignore[arg-type]
    scheduler.register_groups(groups)
    scheduler.resolve(_shape(networks=1, devices=1))

    standard = solve_intervals(groups[:2], _shape(networks=1, devices=1), 1.0, 0.7, {}, 4.0, 3600)
    assert sum(item.demand_rps for item in standard.values()) <= 0.7
    assert scheduler.diagnostics()["profile"]["threshold_demand_rps"] > 0.7
    assert scheduler.requires_explicit_profile() is True


def test_profile_sheds_only_lower_priorities_and_exports_group_lifecycle() -> None:
    """An overloaded chosen profile defers only priorities 3/4 and records state."""
    scheduler = EndpointScheduler(_settings("full"), _Limiter())  # type: ignore[arg-type]
    scheduler.register_groups(_groups())
    scheduler.resolve(_shape(networks=750, devices=4500))

    assert scheduler.is_shed(EndpointGroupName.NH_DATA_RATES)
    assert scheduler.is_shed(EndpointGroupName.CONFIG_ORG)
    assert not scheduler.is_shed(EndpointGroupName.DEVICE_AVAILABILITY)
    assert not scheduler.is_shed(EndpointGroupName.MT_SENSOR_READINGS)
    assert scheduler.should_run(EndpointGroupName.NH_DATA_RATES) is False
    assert scheduler.should_run(EndpointGroupName.DEVICE_AVAILABILITY, now=10) is True
    scheduler.mark_ran(EndpointGroupName.DEVICE_AVAILABILITY, now=11)
    assert scheduler.should_run(EndpointGroupName.MT_SENSOR_READINGS, now=10) is True
    scheduler.mark_failed(EndpointGroupName.MT_SENSOR_READINGS)
    groups = {row["name"]: row for row in scheduler.diagnostics()["groups"]}
    assert groups["device_availability"]["attempts"] == 1
    assert groups["device_availability"]["last_success_timestamp_seconds"] is not None
    exposition = generate_latest(REGISTRY).decode()
    assert "meraki_exporter_scheduler_over_budget 1.0" in exposition
    assert 'meraki_exporter_scheduler_group_shed{group="nh_data_rates"} 1.0' in exposition
    assert "meraki_exporter_scheduler_group_attempts_total" in exposition
    assert (
        'meraki_exporter_scheduler_group_failures_total{group="mt_sensor_readings"} 1.0'
        in exposition
    )
    assert "meraki_exporter_scheduler_group_success_timestamp_seconds" in exposition


@pytest.mark.parametrize(
    ("profile", "allowed", "shed"),
    [
        ("availability", {EndpointGroupName.DEVICE_AVAILABILITY}, set()),
        (
            "standard",
            {
                EndpointGroupName.DEVICE_AVAILABILITY,
                EndpointGroupName.MT_SENSOR_READINGS,
                EndpointGroupName.NH_DATA_RATES,
            },
            {EndpointGroupName.NH_DATA_RATES},
        ),
        (
            "full",
            {
                EndpointGroupName.DEVICE_AVAILABILITY,
                EndpointGroupName.MT_SENSOR_READINGS,
                EndpointGroupName.NH_DATA_RATES,
                EndpointGroupName.CONFIG_ORG,
            },
            {EndpointGroupName.NH_DATA_RATES, EndpointGroupName.CONFIG_ORG},
        ),
    ],
)
def test_explicit_profiles_apply_d6_surface_and_shedding(
    profile: str,
    allowed: set[EndpointGroupName],
    shed: set[EndpointGroupName],
) -> None:
    """An explicit profile selects its surface, then sheds only priority 3/4."""
    scheduler = EndpointScheduler(_settings(profile), _Limiter())  # type: ignore[arg-type]
    scheduler.register_groups(_groups())
    scheduler.resolve(_shape(networks=750, devices=4500))

    assert scheduler.requires_explicit_profile() is False
    for group in (declared.name for declared in _groups()):
        assert scheduler.profile_allows(group) is (group in allowed)
        assert scheduler.is_shed(group) is (group in shed)


def test_shed_skip_counter_records_only_due_execution_opportunities() -> None:
    """Heartbeat consultations before the next due time are not skipped runs."""
    scheduler = EndpointScheduler(_settings("full"), _Limiter())  # type: ignore[arg-type]
    scheduler.register_groups(_groups())
    scheduler.resolve(_shape(networks=750, devices=4500))
    group = EndpointGroupName.NH_DATA_RATES
    scheduler.mark_ran(group, now=100.0)

    counter = MagicMock()
    counter.labels.return_value = counter
    with patch.object(EndpointScheduler, "_group_skips", counter):
        assert scheduler.should_run(group, now=110.0) is False
        assert scheduler.should_run(group, now=120.0) is False
        counter.inc.assert_not_called()

        assert scheduler.should_run(group, now=100.0 + scheduler.interval_for(group)) is False
        counter.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_unset_over_budget_profile_fails_the_startup_preflight() -> None:
    """An ambiguous over-budget plan raises before the server lifespan yields."""
    manager = object.__new__(CollectorManager)
    manager.settings = SimpleNamespace(
        collectors=SimpleNamespace(profile=None, collector_timeout=1.0)
    )
    manager.inventory = SimpleNamespace(warm_cache=AsyncMock())
    manager._resolve_and_log_schedule = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager.scheduler = MagicMock()
    manager.scheduler.requires_explicit_profile.return_value = True
    manager.scheduler.diagnostics.return_value = {
        "profile": {"threshold_demand_rps": 2.5},
        "effective_budget_rps": 1.0,
        "target_utilization": 0.7,
    }

    with pytest.raises(
        StartupConfigurationError,
        match=r"2\.500 rps.*0\.700 rps.*availability.*standard.*full",
    ):
        await manager.validate_profile_selection()

    manager.inventory.warm_cache.assert_awaited_once()
    manager._resolve_and_log_schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_profile_is_solved_before_startup() -> None:
    """Choosing a profile triggers an honest pre-yield solve rather than a no-op return."""
    manager = object.__new__(CollectorManager)
    manager.settings = SimpleNamespace(
        collectors=SimpleNamespace(profile="availability", collector_timeout=1.0)
    )
    manager.inventory = SimpleNamespace(warm_cache=AsyncMock())
    manager._resolve_and_log_schedule = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager.scheduler = MagicMock()
    manager.scheduler.requires_explicit_profile.return_value = False

    await manager.validate_profile_selection()

    manager.inventory.warm_cache.assert_awaited_once()
    manager._resolve_and_log_schedule.assert_awaited_once()
    manager.scheduler.requires_explicit_profile.assert_called_once_with()


@pytest.mark.asyncio
async def test_profile_preflight_has_one_wall_clock_bound() -> None:
    """A stuck inventory warm is cancelled and deferred to normal collection."""
    manager = object.__new__(CollectorManager)
    manager.settings = SimpleNamespace(
        collectors=SimpleNamespace(profile=None, collector_timeout=0.01)
    )

    async def wait_forever() -> None:
        await asyncio.Event().wait()

    manager.inventory = SimpleNamespace(warm_cache=AsyncMock(side_effect=wait_forever))
    manager._resolve_and_log_schedule = AsyncMock(return_value=True)  # type: ignore[method-assign]
    manager.scheduler = MagicMock()

    await manager.validate_profile_selection()

    manager.inventory.warm_cache.assert_awaited_once()
    manager._resolve_and_log_schedule.assert_not_awaited()
    manager.scheduler.requires_explicit_profile.assert_not_called()


@pytest.mark.asyncio
async def test_unset_profile_defers_decision_when_startup_shape_cannot_be_verified() -> None:
    """Transient inventory failure remains startup-tolerant and makes no profile decision."""
    manager = object.__new__(CollectorManager)
    manager.settings = SimpleNamespace(
        collectors=SimpleNamespace(profile=None, collector_timeout=1.0)
    )
    manager.inventory = SimpleNamespace(warm_cache=AsyncMock())
    manager._resolve_and_log_schedule = AsyncMock(return_value=False)  # type: ignore[method-assign]
    manager.scheduler = MagicMock()

    await manager.validate_profile_selection()

    manager.scheduler.requires_explicit_profile.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_uses_the_collector_manager_rate_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#723 startup discovery shares the collector manager's metered limiter."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "0" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__ORG_ID", "123456")
    exporter = ExporterApp(Settings())
    exporter.collector_manager.collect_initial = AsyncMock()  # type: ignore[method-assign]
    exporter._collector_loop = AsyncMock()  # type: ignore[method-assign]
    exporter._scheduler_resolve_loop = AsyncMock()  # type: ignore[method-assign]
    exporter._wait_for_first_collection = AsyncMock()  # type: ignore[method-assign]
    discovery = MagicMock(run_discovery=AsyncMock(return_value={}))

    with patch("meraki_dashboard_exporter.app.DiscoveryService", return_value=discovery) as factory:
        await exporter._startup_collections()

    assert factory.call_args.kwargs["rate_limiter"] is exporter.collector_manager.rate_limiter
