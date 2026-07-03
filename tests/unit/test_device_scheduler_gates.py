"""Wave-2 scheduler gate tests for DeviceCollector (#617).

Covers:
- ``DeviceCollector.endpoint_groups`` declares every DeviceCollector-owned §2
  MEDIUM row (exact names, tier, and setting_pins).
- The ``device_availability`` fetch site (device.py) gates on
  ``_should_run_group`` and calls ``_mark_group_ran`` only after a successful
  fetch.
- The ``device_memory`` fetch site (devices/base.py ``collect_memory_metrics``)
  gates the same way.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.mg import MGCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import (
    DeviceFactory,
    DeviceStatusFactory,
    NetworkFactory,
    OrganizationFactory,
)

# The exact set of §2 rows DeviceCollector owns (build spec #617 §2, MEDIUM tier).
_EXPECTED_DEVICE_GROUPS = {
    EndpointGroupName.DEVICE_AVAILABILITY,
    EndpointGroupName.DEVICE_MEMORY,
    EndpointGroupName.MR_WIRELESS_CLIENTS,
    EndpointGroupName.MR_CONNECTION_STATS,
    EndpointGroupName.MR_ETHERNET_STATUS,
    EndpointGroupName.MR_PACKET_LOSS,
    EndpointGroupName.MR_CPU_LOAD,
    EndpointGroupName.MR_SSID_STATUS,
    EndpointGroupName.MR_SSID_USAGE,
    EndpointGroupName.MS_PORT_STATUS,
    EndpointGroupName.MS_PORT_USAGE,
    EndpointGroupName.MS_PACKET_STATS,
    EndpointGroupName.MS_PORT_OVERVIEW,
    EndpointGroupName.MS_POWER,
    EndpointGroupName.MS_STACKS,
    EndpointGroupName.MS_STP,
    EndpointGroupName.MX_UPLINK_STATUS,
    EndpointGroupName.MX_UPLINK_HEALTH,
    EndpointGroupName.MX_UPLINK_USAGE,
    EndpointGroupName.MX_PERFORMANCE,
    EndpointGroupName.MX_HA,
    EndpointGroupName.MX_VPN,
    EndpointGroupName.MX_SECURITY_EVENTS,
    EndpointGroupName.MX_FIREWALL_CONFIG,
    EndpointGroupName.MV_ANALYTICS,
    EndpointGroupName.MG_UPLINK_STATUS,
    # Phase 4 (#285-#306)
    EndpointGroupName.MX_SECURITY_CONFIG,
    EndpointGroupName.MX_DHCP_SUBNETS,
    EndpointGroupName.MX_VPN_CONFIG,
    EndpointGroupName.MX_NAT_CONFIG,
    EndpointGroupName.MX_VLAN_CONFIG,
    EndpointGroupName.MR_SSID_FIREWALL,
    EndpointGroupName.MR_RF_PROFILES,
    EndpointGroupName.MS_DHCP_SECURITY,
    EndpointGroupName.MS_POWER_SUMMARY,
    EndpointGroupName.MS_LINK_AGGREGATIONS,
    EndpointGroupName.MG_CELLULAR_CONFIG,
    EndpointGroupName.MV_SENSE_CONFIG,
    EndpointGroupName.MV_ONBOARDING,
    # Phase 4B (#618)
    EndpointGroupName.MR_SIGNAL_QUALITY,
    EndpointGroupName.MR_POWER_MODE,
    EndpointGroupName.MR_WIRELESS_CONTROLLER,
    EndpointGroupName.MG_ESIMS,
    EndpointGroupName.MG_HA,
    EndpointGroupName.MX_UPLINKS_OVERVIEW,
}


class TestDeviceEndpointGroups:
    """DeviceCollector.endpoint_groups declaration (#617 §2, task A)."""

    def test_covers_every_owned_group(self) -> None:
        """Exactly the DeviceCollector-owned §2 rows are declared, no more/less."""
        declared = {g.name for g in DeviceCollector.endpoint_groups}
        assert declared == _EXPECTED_DEVICE_GROUPS

    def test_no_duplicate_declarations(self) -> None:
        """Each group is declared exactly once (register_groups forbids dups)."""
        names = [g.name for g in DeviceCollector.endpoint_groups]
        assert len(names) == len(set(names)) == len(_EXPECTED_DEVICE_GROUPS)

    def test_all_groups_are_medium_tier(self) -> None:
        """Every DeviceCollector group is serviced by the MEDIUM heartbeat."""
        assert all(g.tier is UpdateTier.MEDIUM for g in DeviceCollector.endpoint_groups)

    def test_setting_pins_match_spec(self) -> None:
        """Only ms_port_usage / ms_packet_stats carry a legacy setting_pin."""
        pins = {g.name: g.setting_pin for g in DeviceCollector.endpoint_groups if g.setting_pin}
        assert pins == {
            EndpointGroupName.MS_PORT_USAGE: "ms_port_usage_interval",
            EndpointGroupName.MS_PACKET_STATS: "ms_packet_stats_interval",
        }

    def test_priorities_from_spec(self) -> None:
        """Spot-check the priority rubric (1=up-ness, 2=sensor/status, 3=perf, 4=config)."""
        pri = {g.name: g.priority for g in DeviceCollector.endpoint_groups}
        assert pri[EndpointGroupName.DEVICE_AVAILABILITY] == 1
        assert pri[EndpointGroupName.MX_UPLINK_STATUS] == 1
        assert pri[EndpointGroupName.MG_UPLINK_STATUS] == 1
        assert pri[EndpointGroupName.DEVICE_MEMORY] == 3
        assert pri[EndpointGroupName.MX_FIREWALL_CONFIG] == 4
        assert pri[EndpointGroupName.MV_ANALYTICS] == 4

    def test_cost_fns_are_callable_and_shape_driven(self) -> None:
        """cost_fn(shape) returns a finite non-negative number for a sample shape."""
        from meraki_dashboard_exporter.core.scheduler import OrgShape

        shape = OrgShape(
            org_id="org1",
            network_count=500,
            wireless_network_count=200,
            switch_network_count=150,
            appliance_network_count=150,
            sensor_network_count=50,
            camera_network_count=30,
            cellular_network_count=10,
            device_count=5000,
            ap_count=2000,
            switch_count=1500,
            appliance_count=200,
            physical_mx_count=180,
            camera_count=300,
            sensor_count=400,
            cellular_count=20,
            catalyst_ap_count=100,
            signal_quality_ap_count=2000,
        )
        for g in DeviceCollector.endpoint_groups:
            cost = g.cost_fn(shape)
            assert cost >= 1  # every declared group costs at least one API call

    def test_cost_formula_examples(self) -> None:
        """A couple of exact cost formulas from §2 evaluate as specified."""
        from meraki_dashboard_exporter.core.scheduler import OrgShape

        shape = OrgShape(
            org_id="org1",
            network_count=10,
            wireless_network_count=4,
            switch_network_count=3,
            appliance_network_count=2,
            sensor_network_count=1,
            camera_network_count=1,
            cellular_network_count=1,
            device_count=1000,
            ap_count=1500,
            switch_count=40,
            appliance_count=5,
            physical_mx_count=4,
            camera_count=6,
            sensor_count=8,
            cellular_count=2,
        )
        by_name = {g.name: g for g in DeviceCollector.endpoint_groups}
        # device_availability: pages(D=1000, 500) = 2
        assert by_name[EndpointGroupName.DEVICE_AVAILABILITY].cost_fn(shape) == 2
        # device_memory: pages(D=1000, 20) = 50
        assert by_name[EndpointGroupName.DEVICE_MEMORY].cost_fn(shape) == 50
        # mr_packet_loss: 2 * pages(MR=1500, 1000) = 2 * 2 = 4
        assert by_name[EndpointGroupName.MR_PACKET_LOSS].cost_fn(shape) == 4
        # mr_connection_stats: W = 4
        assert by_name[EndpointGroupName.MR_CONNECTION_STATS].cost_fn(shape) == 4
        # mx_firewall_config: 2 * A = 4
        assert by_name[EndpointGroupName.MX_FIREWALL_CONFIG].cost_fn(shape) == 4
        # mv_analytics: 3 * MV = 18
        assert by_name[EndpointGroupName.MV_ANALYTICS].cost_fn(shape) == 18


class TestDeviceAvailabilityGate(BaseCollectorTest):
    """device_availability fetch-site gate (device.py, task B)."""

    collector_class = DeviceCollector
    update_tier = UpdateTier.MEDIUM

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, scheduler):
        org = OrganizationFactory.create(org_id="org1")
        devices = DeviceFactory.create_many(2, device_type="MR")
        net = NetworkFactory.create(network_id="N_1", org_id="org1")
        statuses = [
            DeviceStatusFactory.create(serial=d["serial"], status="online") for d in devices
        ]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([net], org_id="org1")
            .with_devices(devices, org_id="org1")
            .with_device_statuses(statuses, org_id="org1")
            .build()
        )
        # Keep the org-wide memory fetch cheap and well-formed if it runs.
        api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval = MagicMock(
            return_value=[]
        )
        inventory.api = api
        collector = DeviceCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=scheduler,
        )
        return collector

    @staticmethod
    def _spy_availabilities(collector):
        calls: list[str] = []
        real = collector._fetch_device_availabilities

        async def _spy(org_id: str):
            calls.append(org_id)
            return await real(org_id)

        collector._fetch_device_availabilities = _spy  # type: ignore[method-assign]
        return calls

    async def test_skips_fetch_and_mark_when_not_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=False ⇒ availabilities never fetched, group never marked ran."""
        sched = MagicMock()
        sched.should_run.return_value = False
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.return_value = 300.0

        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)
        calls = self._spy_availabilities(collector)

        await collector.collect()

        assert calls == []  # fetch gated out
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.DEVICE_AVAILABILITY not in marked

    async def test_fetches_and_marks_when_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=True ⇒ availabilities fetched, then group marked ran."""
        sched = MagicMock()
        sched.should_run.return_value = True
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.return_value = 300.0

        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)
        calls = self._spy_availabilities(collector)

        await collector.collect()

        assert calls == ["org1"]  # fetch happened once
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.DEVICE_AVAILABILITY in marked


class TestDeviceMemoryGate:
    """device_memory fetch-site gate (devices/base.py collect_memory_metrics, task B)."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock API whose memory-history call returns an empty list."""
        api = MagicMock()
        api.organizations = MagicMock()
        api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval = MagicMock(
            return_value=[]
        )
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Mock parent DeviceCollector wiring the API + a gauge factory."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    async def test_skips_fetch_when_not_due(self, mock_parent: MagicMock) -> None:
        """should_run=False ⇒ memory fetch skipped and group never marked ran."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        collector = MGCollector(mock_parent)

        await collector.collect_memory_metrics("org-1", "Org One")

        fetch = (
            mock_parent.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval
        )
        fetch.assert_not_called()
        mock_parent._should_run_group.assert_called_once_with(EndpointGroupName.DEVICE_MEMORY)
        mock_parent._mark_group_ran.assert_not_called()

    async def test_fetches_and_marks_when_due(self, mock_parent: MagicMock) -> None:
        """should_run=True ⇒ memory fetched, then group marked ran with the ttl looked up."""
        mock_parent._should_run_group = MagicMock(return_value=True)
        mock_parent._group_ttl_seconds = MagicMock(return_value=600.0)
        collector = MGCollector(mock_parent)

        await collector.collect_memory_metrics("org-1", "Org One")

        fetch = (
            mock_parent.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval
        )
        fetch.assert_called_once()
        mock_parent._group_ttl_seconds.assert_called_once_with(EndpointGroupName.DEVICE_MEMORY)
        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.DEVICE_MEMORY)
