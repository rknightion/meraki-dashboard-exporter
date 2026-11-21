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
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, OrganizationFactory


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

    def _device_collector(
        self, mock_api, settings, isolated_registry, inventory, scheduler
    ) -> DeviceCollector:
        """Build a DeviceCollector wired to the given fake scheduler."""
        return DeviceCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            rate_limiter=SimpleNamespace(
                acquire=AsyncMock(return_value=0.0),
                record_throttle_event=MagicMock(),
            ),
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

    @pytest.mark.parametrize(
        ("first", "second", "per_switch", "expected"),
        [
            ("Connected", "Disconnected", False, 0),
            ("Disconnected", "Connected", False, 1),
            ("Connected", "Disconnected", True, 0),
            ("Connected", "Connected", False, 1),
        ],
        ids=["link_drop", "link_recovery", "per_switch_link_drop", "unchanged_link"],
    )
    async def test_port_status_transition_leaves_one_series(
        self, mock_api, settings, isolated_registry, inventory, first, second, per_switch, expected
    ) -> None:
        """Only the current link state remains in the real registry."""
        dc = self._device_collector(
            mock_api, settings, isolated_registry, inventory, _FakeScheduler()
        )
        inventory.get_allowed_network_ids = AsyncMock(return_value=None)
        device = {"serial": "Q2XX-1", "networkId": "net1", "orgId": "org1", "orgName": "Org"}
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.return_value = []
        expire = MagicMock(wraps=dc._expire_metric_series)
        dc._expire_metric_series = expire
        for status in (first, second):
            port = {
                "portId": "1",
                "status": status,
                "speed": "1 Gbps" if status == "Connected" else "",
                "duplex": "full" if status == "Connected" else "",
            }
            if per_switch:
                mock_api.switch.getDeviceSwitchPortsStatuses.return_value = [port]
                await dc.ms_collector.collect(device)
            else:
                mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch.return_value = [
                    {"serial": "Q2XX-1", "network": {"id": "net1"}, "ports": [port]}
                ]
                await dc.ms_collector.collect_port_statuses_by_switch("org1", "Org", [device])
        samples = [
            sample
            for metric in isolated_registry.collect()
            for sample in metric.samples
            if sample.name == "meraki_ms_port_status"
            and sample.labels["serial"] == "Q2XX-1"
            and sample.labels["port_id"] == "1"
        ]
        assert len(samples) == 1
        assert samples[0].value == expected
        if first == second:
            expire.assert_not_called()

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

    async def test_dense_port_opt_out_skips_fetches_but_keeps_overview(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """Disabling dense port series suppresses their fetches, not the bounded overview."""
        settings.api.ms_port_metrics_enabled = False
        sched = _FakeScheduler()
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        devices = [{"serial": "Q2XX-1", "networkId": "net1", "name": "sw1"}]

        status_result = await dc.ms_collector.collect_port_statuses_by_switch(
            "org1", "Org", devices
        )
        usage_result = await dc.ms_collector.collect_port_usage_by_switch("org1", "Org", devices)
        await dc.ms_collector._collect_packet_statistics(devices[0])
        mock_api.switch.getOrganizationSwitchPortsOverview.return_value = {"counts": {}}
        await dc.ms_collector.collect_port_overview("org1", "Org")

        assert status_result is True
        assert usage_result is True
        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch.assert_not_called()
        mock_api.switch.getOrganizationSwitchPortsUsageHistoryByDeviceByInterval.assert_not_called()
        mock_api.switch.getOrganizationSwitchPortsClientsOverviewByDevice.assert_not_called()
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.assert_not_called()
        mock_api.switch.getOrganizationSwitchPortsOverview.assert_called_once()
        assert set(sched.marked) == {
            EndpointGroupName.MS_PORT_STATUS,
            EndpointGroupName.MS_PORT_USAGE,
            EndpointGroupName.MS_PACKET_STATS,
            EndpointGroupName.MS_PORT_OVERVIEW,
        }


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

    async def test_second_cycle_does_not_refetch_packet_stats(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Two full coordinator cycles fetch each switch once, not once per wake."""
        org = OrganizationFactory.create(org_id="ORG")
        devices = [
            DeviceFactory.create(serial=f"Q2XX-{i}", model="MS120-8", productType="switch")
            for i in (1, 2)
        ]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([], org_id="ORG")
            .with_devices(devices, org_id="ORG")
            .with_device_statuses([], org_id="ORG")
            .build()
        )
        api.switch.getOrganizationSwitchPortsStatusesBySwitch.return_value = []
        api.switch.getDeviceSwitchPortsStatusesPackets.return_value = []
        inventory.api = api
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_PACKET_STATS: 600.0})
        dc = self._device_collector(api, settings, isolated_registry, inventory, sched)
        assert settings.api.ms_port_status_use_org_endpoint is True
        packets = api.switch.getDeviceSwitchPortsStatusesPackets

        await dc._collect_impl()
        assert packets.call_count == 2

        packets.reset_mock()
        await dc._collect_impl()
        assert packets.call_count == 0

    @staticmethod
    def _packet_batch_calls(batch: AsyncMock) -> list[Any]:
        """Return the recorded batch-helper calls made for packet statistics."""
        return [
            call
            for call in batch.call_args_list
            if call.kwargs.get("item_description") == "MS packet stats"
        ]

    def _org_with_switches(
        self, mock_api_builder, settings, isolated_registry, inventory, serials: list[str]
    ) -> DeviceCollector:
        """Build a DeviceCollector over one org holding the given MS switches."""
        org = OrganizationFactory.create(org_id="ORG")
        devices = [
            DeviceFactory.create(serial=serial, model="MS120-8", productType="switch")
            for serial in serials
        ]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([], org_id="ORG")
            .with_devices(devices, org_id="ORG")
            .with_device_statuses([], org_id="ORG")
            .build()
        )
        api.switch.getOrganizationSwitchPortsStatusesBySwitch.return_value = []
        api.switch.getDeviceSwitchPortsStatusesPackets.return_value = []
        inventory.api = api
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_PACKET_STATS: 600.0})
        return self._device_collector(api, settings, isolated_registry, inventory, sched)

    async def test_packet_stats_batch_skipped_when_no_switch_is_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """A wake with every switch inside its interval never reaches the batch helper."""
        dc = self._org_with_switches(
            mock_api_builder, settings, isolated_registry, inventory, ["Q2XX-1", "Q2XX-2"]
        )
        for serial in ("Q2XX-1", "Q2XX-2"):
            dc.ms_collector._last_packet_stats[serial] = time.time()

        batch = AsyncMock(return_value=[])
        with patch(
            "meraki_dashboard_exporter.collectors.device.process_in_batches_with_errors", batch
        ):
            await dc._collect_org_devices("ORG", "Org")

        assert self._packet_batch_calls(batch) == []

    async def test_packet_stats_batch_receives_only_due_switches(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Only the switch outside its interval is passed to the batch helper."""
        dc = self._org_with_switches(
            mock_api_builder, settings, isolated_registry, inventory, ["Q2XX-1", "Q2XX-2"]
        )
        dc.ms_collector._last_packet_stats["Q2XX-1"] = time.time()

        batch = AsyncMock(return_value=[])
        with patch(
            "meraki_dashboard_exporter.collectors.device.process_in_batches_with_errors", batch
        ):
            await dc._collect_org_devices("ORG", "Org")

        calls = self._packet_batch_calls(batch)
        assert len(calls) == 1
        assert [device["serial"] for device in calls[0].args[0]] == ["Q2XX-2"]

    async def test_packet_stats_batch_skips_initial_delay_on_forced_run(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """A forced run (including startup) does not wait for the smoothing offset."""
        dc = self._org_with_switches(
            mock_api_builder, settings, isolated_registry, inventory, ["Q2XX-1"]
        )
        dc._force_run = True
        dc._get_smoothing_offset = MagicMock(return_value=42.0)  # type: ignore[method-assign]

        batch = AsyncMock(return_value=[])
        with patch(
            "meraki_dashboard_exporter.collectors.device.process_in_batches_with_errors", batch
        ):
            await dc._collect_org_devices("ORG", "Org")

        calls = self._packet_batch_calls(batch)
        assert len(calls) == 1
        assert calls[0].kwargs["initial_delay"] == 0.0

    async def test_packet_stats_batch_keeps_initial_delay_on_unforced_run(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """An unforced run still passes the per-org smoothing offset."""
        dc = self._org_with_switches(
            mock_api_builder, settings, isolated_registry, inventory, ["Q2XX-1"]
        )
        dc._get_smoothing_offset = MagicMock(return_value=42.0)  # type: ignore[method-assign]

        batch = AsyncMock(return_value=[])
        with patch(
            "meraki_dashboard_exporter.collectors.device.process_in_batches_with_errors", batch
        ):
            await dc._collect_org_devices("ORG", "Org")

        calls = self._packet_batch_calls(batch)
        assert len(calls) == 1
        assert calls[0].kwargs["initial_delay"] == 42.0


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

    async def test_stp_total_failure_reopens_after_retry_spacing(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """Every STP fetch failing reopens the gate 300s later, not after the interval."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_STP: 900.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchStp.side_effect = Exception("boom")
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"id": "net1", "name": "Net 1", "productTypes": ["switch"]},
                {"id": "net2", "name": "Net 2", "productTypes": ["switch"]},
            ]
        )
        ms = dc.ms_collector
        await ms.collect_stp_priorities("org1", "Org")
        assert mock_api.switch.getNetworkSwitchStp.call_count == 2
        assert ms._should_collect_stp_priorities() is False
        assert time.time() - ms._last_stp_collection == pytest.approx(600.0, abs=5.0)

    async def test_stp_success_closes_gate_for_full_interval(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """An answered STP fetch stamps the gate as now."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_STP: 900.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchStp.return_value = {"rstpEnabled": True}
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        )
        ms = dc.ms_collector
        await ms.collect_stp_priorities("org1", "Org")
        assert time.time() - ms._last_stp_collection < 5.0

    async def test_stp_no_switch_networks_closes_gate(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """With no switch networks nothing is asked and the gate still closes."""
        sched = _FakeScheduler(interval_map={EndpointGroupName.MS_STP: 900.0})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        inventory.get_networks = AsyncMock(return_value=[])  # type: ignore[method-assign]
        ms = dc.ms_collector
        await ms.collect_stp_priorities("org1", "Org")
        mock_api.switch.getNetworkSwitchStp.assert_not_called()
        assert time.time() - ms._last_stp_collection < 5.0


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

    async def test_dhcp_security_total_failure_not_marked(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """Both calls failing for every switch network leaves the group unmarked."""
        sched = _FakeScheduler({EndpointGroupName.MS_DHCP_SECURITY: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.side_effect = Exception("boom")
        mock_api.switch.getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice.side_effect = Exception(
            "boom"
        )
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"id": "net1", "name": "Net 1", "productTypes": ["switch"]},
                {"id": "net2", "name": "Net 2", "productTypes": ["switch"]},
            ]
        )
        await dc.ms_collector.collect_dhcp_security("org1", "Org")
        assert mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.call_count == 2
        assert EndpointGroupName.MS_DHCP_SECURITY not in sched.marked

    async def test_dhcp_security_partial_success_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """One answered call is enough to close the gate."""
        sched = _FakeScheduler({EndpointGroupName.MS_DHCP_SECURITY: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.side_effect = Exception("boom")
        mock_api.switch.getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice.return_value = []
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        )
        await dc.ms_collector.collect_dhcp_security("org1", "Org")
        assert EndpointGroupName.MS_DHCP_SECURITY in sched.marked

    async def test_dhcp_security_404_counts_as_answered(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A 404 means not available here, so it answers the fetch."""
        sched = _FakeScheduler({EndpointGroupName.MS_DHCP_SECURITY: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        not_found = Exception("not available")
        not_found.status = 404  # type: ignore[attr-defined]
        mock_api.switch.getNetworkSwitchDhcpV4ServersSeen.side_effect = not_found
        mock_api.switch.getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice.side_effect = not_found
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        )
        await dc.ms_collector.collect_dhcp_security("org1", "Org")
        assert EndpointGroupName.MS_DHCP_SECURITY in sched.marked

    async def test_dhcp_security_no_switch_networks_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """With no switch networks nothing is asked and the gate still closes."""
        sched = _FakeScheduler({EndpointGroupName.MS_DHCP_SECURITY: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        inventory.get_networks = AsyncMock(return_value=[])  # type: ignore[method-assign]
        await dc.ms_collector.collect_dhcp_security("org1", "Org")
        assert EndpointGroupName.MS_DHCP_SECURITY in sched.marked


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

    async def test_link_aggregations_total_failure_not_marked(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """The call failing for every switch network leaves the group unmarked."""
        sched = _FakeScheduler({EndpointGroupName.MS_LINK_AGGREGATIONS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchLinkAggregations.side_effect = Exception("boom")
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"id": "net1", "name": "Net 1", "productTypes": ["switch"]},
                {"id": "net2", "name": "Net 2", "productTypes": ["switch"]},
            ]
        )
        await dc.ms_collector.collect_link_aggregations("org1", "Org")
        assert mock_api.switch.getNetworkSwitchLinkAggregations.call_count == 2
        assert EndpointGroupName.MS_LINK_AGGREGATIONS not in sched.marked

    async def test_link_aggregations_404_counts_as_answered(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A 404 means not available here, so it answers the fetch."""
        sched = _FakeScheduler({EndpointGroupName.MS_LINK_AGGREGATIONS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        not_found = Exception("not available")
        not_found.status = 404  # type: ignore[attr-defined]
        mock_api.switch.getNetworkSwitchLinkAggregations.side_effect = not_found
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "net1", "name": "Net 1", "productTypes": ["switch"]}]
        )
        await dc.ms_collector.collect_link_aggregations("org1", "Org")
        assert EndpointGroupName.MS_LINK_AGGREGATIONS in sched.marked

    async def test_link_aggregations_partial_success_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """One network answering closes the gate even when another fails."""
        sched = _FakeScheduler({EndpointGroupName.MS_LINK_AGGREGATIONS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getNetworkSwitchLinkAggregations.side_effect = [Exception("boom"), []]
        inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"id": "net1", "name": "Net 1", "productTypes": ["switch"]},
                {"id": "net2", "name": "Net 2", "productTypes": ["switch"]},
            ]
        )
        await dc.ms_collector.collect_link_aggregations("org1", "Org")
        assert EndpointGroupName.MS_LINK_AGGREGATIONS in sched.marked

    async def test_link_aggregations_no_switch_networks_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """With no switch networks nothing is asked and the gate still closes."""
        sched = _FakeScheduler({EndpointGroupName.MS_LINK_AGGREGATIONS: True})
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        inventory.get_networks = AsyncMock(return_value=[])  # type: ignore[method-assign]
        await dc.ms_collector.collect_link_aggregations("org1", "Org")
        assert EndpointGroupName.MS_LINK_AGGREGATIONS in sched.marked


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


class TestMSPortFallback(_MSGatingBase):
    """#997: the per-switch port pass runs only when the org endpoint is absent or opted out."""

    _SWITCHES = ("Q2XX-1", "Q2XX-2")

    def _build(
        self,
        mock_api: Any,
        settings: Any,
        isolated_registry: Any,
        inventory: Any,
        sched: _FakeScheduler,
    ) -> DeviceCollector:
        """Build a collector over two switches with inventory fetches stubbed."""
        settings.api.smoothing_enabled = False
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        switches = [
            {
                "serial": serial,
                "name": serial,
                "model": "MS250-48",
                "productType": "switch",
                "networkId": "net1",
            }
            for serial in self._SWITCHES
        ]
        inventory.get_devices = AsyncMock(return_value=switches)
        inventory.get_device_availabilities = AsyncMock(return_value=[])
        inventory.get_networks = AsyncMock(return_value=[{"id": "net1", "name": "Net 1"}])
        inventory.get_allowed_network_ids = AsyncMock(return_value=None)
        mock_api.switch.getDeviceSwitchPortsStatuses.return_value = []
        mock_api.switch.getDeviceSwitchPortsStatusesPackets.return_value = []
        return dc

    async def test_transient_org_failure_does_not_fan_out(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A failed org-wide call is not answered with one call per switch."""
        sched = _FakeScheduler()
        dc = self._build(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getOrganizationSwitchPortsStatusesBySwitch.side_effect = Exception("boom")

        await dc._collect_org_devices("org1", "Org")

        mock_api.switch.getDeviceSwitchPortsStatuses.assert_not_called()
        assert EndpointGroupName.MS_PORT_STATUS not in sched.marked

    async def test_unsupported_endpoint_falls_back_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """An SDK without the org endpoint takes the per-switch pass and closes both groups."""
        sched = _FakeScheduler()
        dc = self._build(mock_api, settings, isolated_registry, inventory, sched)
        dc.ms_collector._org_port_status_supported = False

        await dc._collect_org_devices("org1", "Org")

        assert mock_api.switch.getDeviceSwitchPortsStatuses.call_count == len(self._SWITCHES)
        assert EndpointGroupName.MS_PORT_STATUS in sched.marked
        assert EndpointGroupName.MS_PORT_USAGE in sched.marked
        assert dc.ms_collector._active_serials == set(self._SWITCHES)

    async def test_flag_off_pass_is_gated_and_marked(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """With the org endpoint opted out, the pass follows the gates and closes both groups."""
        settings.api.ms_port_status_use_org_endpoint = False
        sched = _FakeScheduler()
        dc = self._build(mock_api, settings, isolated_registry, inventory, sched)

        await dc._collect_org_devices("org1", "Org")

        assert mock_api.switch.getDeviceSwitchPortsStatuses.call_count == len(self._SWITCHES)
        assert EndpointGroupName.MS_PORT_STATUS in sched.marked
        assert EndpointGroupName.MS_PORT_USAGE in sched.marked

        mock_api.switch.getDeviceSwitchPortsStatuses.reset_mock()
        sched.marked.clear()
        sched.run_map = {
            EndpointGroupName.MS_PORT_STATUS: False,
            EndpointGroupName.MS_PORT_USAGE: False,
        }

        await dc._collect_org_devices("org1", "Org")

        mock_api.switch.getDeviceSwitchPortsStatuses.assert_not_called()
        assert EndpointGroupName.MS_PORT_STATUS not in sched.marked
        assert EndpointGroupName.MS_PORT_USAGE not in sched.marked

    async def test_flag_off_packet_stats_run_when_port_groups_not_due(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """No per-switch pass this wake: due packet statistics are still collected."""
        settings.api.ms_port_status_use_org_endpoint = False
        sched = _FakeScheduler({
            EndpointGroupName.MS_PORT_STATUS: False,
            EndpointGroupName.MS_PORT_USAGE: False,
        })
        dc = self._build(mock_api, settings, isolated_registry, inventory, sched)
        packet_stats = AsyncMock()
        dc.ms_collector._collect_packet_statistics = packet_stats  # type: ignore[method-assign]

        await dc._collect_org_devices("org1", "Org")

        mock_api.switch.getDeviceSwitchPortsStatuses.assert_not_called()
        assert sorted(call.args[0]["serial"] for call in packet_stats.await_args_list) == sorted(
            self._SWITCHES
        )

    async def test_flag_off_packet_stats_throttle_survives_end_of_cycle_eviction(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """Serials stay registered on a wake with no per-switch pass, so throttles persist."""
        settings.api.ms_port_status_use_org_endpoint = False
        sched = _FakeScheduler({
            EndpointGroupName.MS_PORT_STATUS: False,
            EndpointGroupName.MS_PORT_USAGE: False,
        })
        dc = self._build(mock_api, settings, isolated_registry, inventory, sched)
        packets = mock_api.switch.getDeviceSwitchPortsStatusesPackets

        await dc._collect_org_devices("org1", "Org")
        assert packets.call_count == len(self._SWITCHES)

        # The end-of-cycle step of DeviceCollector._collect_impl.
        dc.ms_collector._evict_stale_serials(dc.ms_collector._active_serials)
        dc.ms_collector._active_serials = set()

        packets.reset_mock()
        await dc._collect_org_devices("org1", "Org")
        packets.assert_not_called()

    async def test_per_switch_pass_total_failure_marks_nothing(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A pass in which every switch fails closes neither group."""
        settings.api.ms_port_status_use_org_endpoint = False
        sched = _FakeScheduler()
        dc = self._build(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.switch.getDeviceSwitchPortsStatuses.side_effect = Exception("boom")

        await dc._collect_org_devices("org1", "Org")

        assert mock_api.switch.getDeviceSwitchPortsStatuses.call_count == len(self._SWITCHES)
        assert EndpointGroupName.MS_PORT_STATUS not in sched.marked
        assert EndpointGroupName.MS_PORT_USAGE not in sched.marked


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
