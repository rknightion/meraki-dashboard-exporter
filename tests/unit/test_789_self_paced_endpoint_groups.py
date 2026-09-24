"""Regression coverage for per-key-throttled groups spinning the collector loop (GitHub #789).

Several DeviceCollector and ClientsCollector groups pace their fetches with
per-serial or per-network timestamps and never call ``should_run``. Their
scheduler clock therefore stays "never ran", so ``seconds_until_due`` returned 0
and the outer collector loop re-ran every second.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from meraki_dashboard_exporter.collectors.clients import ClientsCollector
from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.scheduler import (
    EndpointGroup,
    EndpointGroupName,
    EndpointScheduler,
    OrgShape,
)

# Groups whose cadence is owned by a per-key timestamp throttle in the sub-collector.
_DEVICE_SELF_PACED = {
    EndpointGroupName.MX_PERFORMANCE,
    EndpointGroupName.MX_DHCP_SUBNETS,
    EndpointGroupName.MX_FIREWALL_CONFIG,
    EndpointGroupName.MX_SECURITY_CONFIG,
    EndpointGroupName.MX_NAT_CONFIG,
    EndpointGroupName.MX_VLAN_CONFIG,
    EndpointGroupName.MS_PACKET_STATS,
    EndpointGroupName.MS_STP,
    EndpointGroupName.MV_ANALYTICS,
    EndpointGroupName.MV_SENSE_CONFIG,
}
_CLIENTS_SELF_PACED = {
    EndpointGroupName.CLIENTS_APP_USAGE,
    EndpointGroupName.CLIENTS_SIGNAL_QUALITY,
}


class _Limiter:
    """Fixed budget double for scheduler-only tests."""

    def effective_rate_per_second(self) -> float:
        """Return an ample rate so every group sits at its floor."""
        return math.inf


def _settings() -> SimpleNamespace:
    """Minimal settings surface used by the scheduler."""
    return SimpleNamespace(
        api=SimpleNamespace(
            rate_limit_requests_per_second=10.0,
            rate_limit_shared_fraction=1.0,
            model_fields_set=set(),
        ),
        collectors=SimpleNamespace(profile="full"),
        monitoring=SimpleNamespace(metric_ttl_multiplier=2.0),
        scheduler=SimpleNamespace(
            mode="fixed",
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


def _shape() -> OrgShape:
    """One org with a single physical MX, as in the #789 report, plus an MS and an MV."""
    return OrgShape(
        org_id="789",
        network_count=1,
        wireless_network_count=0,
        switch_network_count=1,
        appliance_network_count=1,
        sensor_network_count=0,
        camera_network_count=1,
        cellular_network_count=0,
        device_count=3,
        ap_count=0,
        switch_count=1,
        appliance_count=1,
        physical_mx_count=1,
        camera_count=1,
        sensor_count=0,
        cellular_count=0,
    )


def test_789_device_loop_sleeps_after_every_scheduler_owned_group_ran() -> None:
    """Groups paced per key must not hold the DeviceCollector loop at "due now"."""
    scheduler = EndpointScheduler(_settings(), _Limiter())  # type: ignore[arg-type]
    groups = DeviceCollector.endpoint_groups
    scheduler.register_groups(groups)
    scheduler.resolve(_shape())

    # Every group the scheduler gates through should_run has just succeeded.
    for group in groups:
        if group.name not in _DEVICE_SELF_PACED:
            scheduler.mark_ran(group.name, now=100.0)

    due_in = scheduler.seconds_until_due([g.name for g in groups], now=100.0)

    # DEVICE_AVAILABILITY (floor 120s) is the earliest sibling: 120 x 0.9.
    assert due_in == pytest.approx(108.0)


def test_789_per_key_groups_are_declared_self_paced() -> None:
    """Every per-key-throttled group opts out of the loop clock, and nothing else does."""
    device = {g.name for g in DeviceCollector.endpoint_groups if g.self_paced}
    clients = {g.name for g in ClientsCollector.endpoint_groups if g.self_paced}

    assert device == _DEVICE_SELF_PACED
    assert clients == _CLIENTS_SELF_PACED


def test_789_self_paced_group_is_solved_but_skipped_by_the_loop_clock() -> None:
    """A self-paced group keeps its solved interval but never sets the wake time."""
    scheduler = EndpointScheduler(_settings(), _Limiter())  # type: ignore[arg-type]
    paced = EndpointGroup(
        name=EndpointGroupName.MX_PERFORMANCE,
        priority=3,
        floor_seconds=1800,
        cost_fn=lambda s: 1.0,
        self_paced=True,
    )
    sibling = EndpointGroup(
        name=EndpointGroupName.MX_UPLINK_STATUS,
        priority=1,
        floor_seconds=300,
        cost_fn=lambda s: 1.0,
    )
    scheduler.register_groups((paced, sibling))
    scheduler.resolve(_shape())
    scheduler.mark_ran(EndpointGroupName.MX_UPLINK_STATUS, now=100.0)

    assert scheduler.interval_for(EndpointGroupName.MX_PERFORMANCE) == pytest.approx(1800.0)
    assert scheduler.seconds_until_due(
        [EndpointGroupName.MX_PERFORMANCE, EndpointGroupName.MX_UPLINK_STATUS], now=100.0
    ) == pytest.approx(270.0)
    # Alone, a self-paced group gives the loop nothing to wake on.
    assert scheduler.seconds_until_due([EndpointGroupName.MX_PERFORMANCE], now=100.0) is None
