"""Tests for #617 scheduler gating on the MS switch lane.

Covers the fetch-site gates added to the MS sub-collectors (``MSCollector``,
``MSStackCollector``, ``MSPowerCollector``): the group ``should_run`` gate,
``mark_ran`` on a successful fetch, ``ttl_seconds`` threading onto every
``_set_metric`` emission, and the existing per-serial / STP timestamp gates now
sourcing their interval from ``_group_interval`` rather than the raw setting.

The sub-collectors reach the scheduler through ``self.parent._*`` (the
``MetricCollector`` gate helpers on the owning ``DeviceCollector``), so these
tests drive a real ``DeviceCollector`` with a controllable fake scheduler.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest


class _FakeScheduler:
    """Minimal scheduler double: controls gates, intervals, ttl; records marks."""

    def __init__(
        self,
        run_map: dict[EndpointGroupName, bool] | None = None,
        interval_map: dict[EndpointGroupName, float] | None = None,
        ttl: float = 777.0,
    ) -> None:
        """Store the gate/interval maps and the fixed ttl value."""
        self.run_map = run_map or {}
        self.interval_map = interval_map or {}
        self.ttl = ttl
        self.marked: list[EndpointGroupName] = []

    def should_run(self, group: EndpointGroupName, now: float | None = None) -> bool:
        """Return the configured gate decision (default True)."""
        return self.run_map.get(group, True)

    def mark_ran(self, group: EndpointGroupName, now: float | None = None) -> None:
        """Record that a group was marked as having run."""
        self.marked.append(group)

    def interval_for(self, group: EndpointGroupName) -> float:
        """Return the configured interval for a group (default 300s)."""
        return self.interval_map.get(group, 300.0)

    def ttl_seconds_for(self, group: EndpointGroupName) -> float:
        """Return the fixed ttl for any group."""
        return self.ttl

    def register_groups(self, groups: Any) -> None:  # pragma: no cover - unused
        """No-op to satisfy the scheduler protocol."""

    def resolve(self, shape: Any) -> None:  # pragma: no cover - unused
        """No-op to satisfy the scheduler protocol."""


class _MSGatingBase(BaseCollectorTest):
    """Shared helpers for MS lane gating tests driven via a real DeviceCollector."""

    collector_class = DeviceCollector
    update_tier = UpdateTier.MEDIUM

    def _device_collector(
        self, mock_api, settings, isolated_registry, inventory, scheduler
    ) -> DeviceCollector:
        """Build a DeviceCollector wired to the given fake scheduler."""
        return DeviceCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=scheduler,  # type: ignore[arg-type]
        )

    @staticmethod
    def _spy_set_metric(collector: DeviceCollector) -> list[float | None]:
        """Record the ttl_seconds passed to every parent._set_metric call."""
        ttls: list[float | None] = []
        original = collector._set_metric

        def spy(metric, labels, value, metric_name=None, ttl_seconds=None):  # type: ignore[no-untyped-def]
            ttls.append(ttl_seconds)
            return original(metric, labels, value, metric_name, ttl_seconds=ttl_seconds)

        collector._set_metric = spy  # type: ignore[method-assign]
        return ttls


class TestMSPortStatusGate(_MSGatingBase):
    """MS_PORT_STATUS org-endpoint gate behaviour."""

    async def test_org_port_status_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the fetch and returns True (no coordinator fallback)."""
        sched = _FakeScheduler({EndpointGroupName.MS_PORT_STATUS: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        devices = [{"serial": "Q2XX-1", "networkId": "net1", "name": "sw1"}]
        result = await dc.ms_collector.collect_port_statuses_by_switch("org1", "Org", devices)
        assert result is True
        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch.assert_not_called()
        assert EndpointGroupName.MS_PORT_STATUS not in sched.marked

    async def test_org_port_status_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches, marks the group, and threads the group ttl."""
        sched = _FakeScheduler({EndpointGroupName.MS_PORT_STATUS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ttls = self._spy_set_metric(dc)
        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch.return_value = [
            {
                "serial": "Q2XX-1",
                "network": {"id": "net1", "name": "Net 1"},
                "ports": [{"portId": "1", "status": "Connected"}],
            }
        ]
        devices = [{"serial": "Q2XX-1", "networkId": "net1", "name": "sw1"}]
        result = await dc.ms_collector.collect_port_statuses_by_switch("org1", "Org", devices)
        assert result is True
        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch.assert_called_once()
        assert EndpointGroupName.MS_PORT_STATUS in sched.marked
        assert 777.0 in ttls


class TestMSPortUsageGate(_MSGatingBase):
    """MS_PORT_USAGE org-endpoint gate and per-serial interval sourcing."""

    async def test_org_port_usage_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the usage fetch and returns True."""
        sched = _FakeScheduler({EndpointGroupName.MS_PORT_USAGE: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        devices = [{"serial": "Q2XX-1", "networkId": "net1", "name": "sw1"}]
        result = await dc.ms_collector.collect_port_usage_by_switch("org1", "Org", devices)
        assert result is True
        mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval.assert_not_called()
        assert EndpointGroupName.MS_PORT_USAGE not in sched.marked

    async def test_org_port_usage_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches, marks the group, and threads the group ttl."""
        sched = _FakeScheduler({EndpointGroupName.MS_PORT_USAGE: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ttls = self._spy_set_metric(dc)
        mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval.return_value = [
            {
                "serial": "Q2XX-1",
                "network": {"id": "net1", "name": "Net 1"},
                "ports": [
                    {
                        "portId": "1",
                        "intervals": [
                            {"data": {"usage": {"upstream": 1, "downstream": 2, "total": 3}}}
                        ],
                    }
                ],
            }
        ]
        mock_api.switch.getOrganizationSwitchPortsClientsOverviewByDevice.return_value = []
        devices = [{"serial": "Q2XX-1", "networkId": "net1", "name": "sw1"}]
        result = await dc.ms_collector.collect_port_usage_by_switch("org1", "Org", devices)
        assert result is True
        assert EndpointGroupName.MS_PORT_USAGE in sched.marked
        assert 777.0 in ttls

    async def test_should_collect_port_usage_reads_group_interval(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """The per-serial usage gate reads its interval from _group_interval."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_PORT_USAGE: 600.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ms = dc.ms_collector
        ms._last_port_usage["fresh"] = time.time()
        ms._last_port_usage["stale"] = time.time() - 10_000
        assert ms._should_collect_port_usage("fresh") is False
        assert ms._should_collect_port_usage("stale") is True
        assert ms._should_collect_port_usage("never-seen") is True


class TestMSPacketStatsGate(_MSGatingBase):
    """MS_PACKET_STATS per-serial interval sourcing and ttl threading."""

    async def test_should_collect_packet_stats_reads_group_interval(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """The per-serial packet-stats gate reads its interval from _group_interval."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_PACKET_STATS: 600.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ms = dc.ms_collector
        ms._last_packet_stats["fresh"] = time.time()
        ms._last_packet_stats["stale"] = time.time() - 10_000
        assert ms._should_collect_packet_stats("fresh") is False
        assert ms._should_collect_packet_stats("stale") is True

    async def test_packet_stats_threads_ttl(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """Packet-stats emissions carry the MS_PACKET_STATS group ttl."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_PACKET_STATS: 0.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ttls = self._spy_set_metric(dc)
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.return_value = [
            {
                "portId": "1",
                "packets": [
                    {"desc": "Total", "total": 10, "sent": 5, "recv": 5, "ratePerSec": {"total": 1}}
                ],
            }
        ]
        device = {"serial": "Q2XX-1", "orgId": "org1", "orgName": "Org", "networkId": "net1"}
        await dc.ms_collector._collect_packet_statistics(device)
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.assert_called_once()
        assert 777.0 in ttls


class TestMSPortOverviewGate(_MSGatingBase):
    """MS_PORT_OVERVIEW single-call gate behaviour."""

    async def test_port_overview_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the overview fetch and does not mark the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_PORT_OVERVIEW: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        await dc.ms_collector.collect_port_overview("org1", "Org")
        mock_api.switch.getOrganizationSwitchPortsOverview.assert_not_called()
        assert EndpointGroupName.MS_PORT_OVERVIEW not in sched.marked

    async def test_port_overview_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches the overview and marks the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_PORT_OVERVIEW: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getOrganizationSwitchPortsOverview.return_value = {"counts": {}}
        await dc.ms_collector.collect_port_overview("org1", "Org")
        mock_api.switch.getOrganizationSwitchPortsOverview.assert_called_once()
        assert EndpointGroupName.MS_PORT_OVERVIEW in sched.marked


class TestMSStpGate(_MSGatingBase):
    """MS_STP timestamp gate interval sourcing."""

    async def test_should_collect_stp_reads_group_interval(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """The STP timestamp gate reads its interval from _group_interval."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_STP: 900.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ms = dc.ms_collector
        ms._last_stp_collection = time.time()
        assert ms._should_collect_stp_priorities() is False
        ms._last_stp_collection = time.time() - 10_000
        assert ms._should_collect_stp_priorities() is True


class TestMSPowerGate(_MSGatingBase):
    """MS_POWER single-call gate behaviour."""

    async def test_power_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the power-module fetch and does not mark the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_POWER: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        await dc.ms_power_collector.collect_power_modules("org1", "Org", {})
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice.assert_not_called()
        assert EndpointGroupName.MS_POWER not in sched.marked

    async def test_power_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches (even empty) and marks the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_POWER: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice.return_value = []
        await dc.ms_power_collector.collect_power_modules("org1", "Org", {})
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice.assert_called_once()
        assert EndpointGroupName.MS_POWER in sched.marked


class TestMSStacksGate(_MSGatingBase):
    """MS_STACKS fan-out gate (gated once in collect_for_org, before the batch)."""

    async def test_stacks_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the whole per-network stack fan-out."""
        sched = _FakeScheduler({EndpointGroupName.MS_STACKS: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        networks = [{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        await dc.ms_stack_collector.collect_for_org("org1", "Org", networks)
        mock_api.switch.getNetworkSwitchStacks.assert_not_called()
        assert EndpointGroupName.MS_STACKS not in sched.marked

    async def test_stacks_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate runs the fan-out and marks the group after it completes."""
        sched = _FakeScheduler({EndpointGroupName.MS_STACKS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchStacks.return_value = []
        networks = [{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        await dc.ms_stack_collector.collect_for_org("org1", "Org", networks)
        mock_api.switch.getNetworkSwitchStacks.assert_called()
        assert EndpointGroupName.MS_STACKS in sched.marked


class TestMSDhcpSecurityGate(_MSGatingBase):
    """MS_DHCP_SECURITY per-network fan-out gate (#292/#293)."""

    async def test_dhcp_security_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the whole per-network fan-out."""
        sched = _FakeScheduler({EndpointGroupName.MS_DHCP_SECURITY: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        await dc.ms_collector.collect_dhcp_security("org1", "Org")
        mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.assert_not_called()
        assert EndpointGroupName.MS_DHCP_SECURITY not in sched.marked

    async def test_dhcp_security_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches for every switch network and marks the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_DHCP_SECURITY: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ttls = self._spy_set_metric(dc)
        mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.return_value = []
        mock_api.switch.getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice.return_value = []
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        )
        await dc.ms_collector.collect_dhcp_security("org1", "Org")
        mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.assert_called_once()
        assert EndpointGroupName.MS_DHCP_SECURITY in sched.marked
        assert 777.0 in ttls


class TestMSLinkAggregationsGate(_MSGatingBase):
    """MS_LINK_AGGREGATIONS per-network fan-out gate (#295)."""

    async def test_link_aggregations_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the whole per-network fan-out."""
        sched = _FakeScheduler({EndpointGroupName.MS_LINK_AGGREGATIONS: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        await dc.ms_collector.collect_link_aggregations("org1", "Org")
        mock_api.switch.getNetworkSwitchLinkAggregations.assert_not_called()
        assert EndpointGroupName.MS_LINK_AGGREGATIONS not in sched.marked

    async def test_link_aggregations_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches for every switch network and marks the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_LINK_AGGREGATIONS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ttls = self._spy_set_metric(dc)
        mock_api.switch.getNetworkSwitchLinkAggregations.return_value = []
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        )
        await dc.ms_collector.collect_link_aggregations("org1", "Org")
        mock_api.switch.getNetworkSwitchLinkAggregations.assert_called_once()
        assert EndpointGroupName.MS_LINK_AGGREGATIONS in sched.marked
        assert 777.0 in ttls


class TestMSPowerSummaryGate(_MSGatingBase):
    """MS_POWER_SUMMARY single-call gate behaviour (#294)."""

    async def test_power_summary_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due gate skips the org-wide PoE draw fetch."""
        sched = _FakeScheduler({EndpointGroupName.MS_POWER_SUMMARY: False})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        await dc.ms_collector.collect_power_history("org1", "Org")
        mock_api.switch.getOrganizationSummarySwitchPowerHistory.assert_not_called()
        assert EndpointGroupName.MS_POWER_SUMMARY not in sched.marked

    async def test_power_summary_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due gate fetches the org-wide history and marks the group."""
        sched = _FakeScheduler({EndpointGroupName.MS_POWER_SUMMARY: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        ttls = self._spy_set_metric(dc)
        mock_api.switch.getOrganizationSummarySwitchPowerHistory.return_value = [
            {"startTs": "t0", "endTs": "t1", "draw": 55.0}
        ]
        await dc.ms_collector.collect_power_history("org1", "Org")
        mock_api.switch.getOrganizationSummarySwitchPowerHistory.assert_called_once()
        assert EndpointGroupName.MS_POWER_SUMMARY in sched.marked
        assert 777.0 in ttls


@pytest.mark.parametrize(
    "group",
    [
        EndpointGroupName.MS_PORT_STATUS,
        EndpointGroupName.MS_PORT_USAGE,
        EndpointGroupName.MS_PACKET_STATS,
        EndpointGroupName.MS_PORT_OVERVIEW,
        EndpointGroupName.MS_POWER,
        EndpointGroupName.MS_STACKS,
        EndpointGroupName.MS_STP,
        EndpointGroupName.MS_DHCP_SECURITY,
        EndpointGroupName.MS_POWER_SUMMARY,
        EndpointGroupName.MS_LINK_AGGREGATIONS,
    ],
)
def test_ms_groups_declared_on_device_collector(group: EndpointGroupName) -> None:
    """Every MS endpoint group this lane gates is declared on DeviceCollector."""
    names = {g.name for g in DeviceCollector.endpoint_groups}
    assert group in names
