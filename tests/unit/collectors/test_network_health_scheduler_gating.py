"""Tests for NetworkHealthCollector scheduler gating + endpoint-group declarations (#617).

Covers the Wave-2 fetch-site gating for the network-health lane: the eight
``nh_*`` endpoint groups declared on ``NetworkHealthCollector`` (seven
original + ``NH_MESH`` added by #307/#618), the per-group
``_should_run_group``/``_mark_group_ran`` gates threaded through
``_collect_org_network_health`` (org-wide channel-util) and
``_collect_network_health_bundle`` (the seven per-network groups), and the
``ttl_seconds`` threading into sub-collector metric writes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, OrgShape
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory

_ALL_NH_GROUPS = {
    EndpointGroupName.NH_CHANNEL_UTILIZATION,
    EndpointGroupName.NH_CONNECTION_STATS,
    EndpointGroupName.NH_DATA_RATES,
    EndpointGroupName.NH_BLUETOOTH,
    EndpointGroupName.NH_FAILED_CONNECTIONS,
    EndpointGroupName.NH_LATENCY_STATS,
    EndpointGroupName.NH_AIR_MARSHAL,
    EndpointGroupName.NH_MESH,
}

_BUNDLE_GROUPS = _ALL_NH_GROUPS - {EndpointGroupName.NH_CHANNEL_UTILIZATION}


def _sample_shape() -> OrgShape:
    """Build a representative OrgShape for cost-function assertions."""
    return OrgShape(
        org_id="O1",
        network_count=10,
        wireless_network_count=8,
        switch_network_count=3,
        appliance_network_count=2,
        sensor_network_count=1,
        camera_network_count=0,
        cellular_network_count=0,
        device_count=100,
        ap_count=40,
        switch_count=30,
        appliance_count=10,
        physical_mx_count=8,
        camera_count=5,
        sensor_count=5,
        cellular_count=0,
    )


class FakeScheduler:
    """Minimal scheduler double: controls should_run and records mark_ran."""

    def __init__(self, due: set[EndpointGroupName] | None = None, ttl: float = 1234.0) -> None:
        """Store the due-group set (None => all due) and the TTL to return."""
        self._due = due
        self._ttl = ttl
        self.marked: list[EndpointGroupName] = []

    def should_run(self, group: EndpointGroupName, now: float | None = None) -> bool:
        """Return whether the group is due (True for all when due is None)."""
        if self._due is None:
            return True
        return group in self._due

    def mark_ran(self, group: EndpointGroupName, now: float | None = None) -> None:
        """Record a mark_ran call for later assertion."""
        self.marked.append(group)

    def ttl_seconds_for(self, group: EndpointGroupName) -> float:
        """Return the fixed TTL."""
        return self._ttl

    def interval_for(self, group: EndpointGroupName) -> float:
        """Return a fixed interval."""
        return 300.0


class TestEndpointGroupDeclarations:
    """The eight nh_* groups are declared on NetworkHealthCollector with #541/#307 floors."""

    def test_all_eight_groups_declared(self) -> None:
        """All eight network-health endpoint groups are declared."""
        groups = {g.name: g for g in NetworkHealthCollector.endpoint_groups}
        assert set(groups) == _ALL_NH_GROUPS

    def test_floors_and_priorities(self) -> None:
        """Floors fold #541 windows; every NH group is priority 3, MEDIUM, unpinned."""
        groups = {g.name: g for g in NetworkHealthCollector.endpoint_groups}
        expected_floor = {
            EndpointGroupName.NH_CHANNEL_UTILIZATION: 300,
            EndpointGroupName.NH_CONNECTION_STATS: 1800,
            EndpointGroupName.NH_DATA_RATES: 300,
            EndpointGroupName.NH_BLUETOOTH: 300,
            EndpointGroupName.NH_FAILED_CONNECTIONS: 3600,
            EndpointGroupName.NH_LATENCY_STATS: 3600,
            EndpointGroupName.NH_AIR_MARSHAL: 3600,
            EndpointGroupName.NH_MESH: 3600,
        }
        for name, floor in expected_floor.items():
            assert groups[name].floor_seconds == floor, name
            assert groups[name].priority == 3, name
            assert groups[name].tier is UpdateTier.MEDIUM, name
            assert groups[name].setting_pin is None, name

    def test_cost_functions(self) -> None:
        """Cost functions match the §2 table formulas over OrgShape."""
        groups = {g.name: g for g in NetworkHealthCollector.endpoint_groups}
        shape = _sample_shape()
        w = shape.wireless_network_count  # 8
        # channel-util post-#271: 2 org-wide calls paginated by AP count (perPage 1000)
        assert groups[EndpointGroupName.NH_CHANNEL_UTILIZATION].cost_fn(shape) == 2
        assert groups[EndpointGroupName.NH_CONNECTION_STATS].cost_fn(shape) == w
        assert groups[EndpointGroupName.NH_DATA_RATES].cost_fn(shape) == w
        assert groups[EndpointGroupName.NH_BLUETOOTH].cost_fn(shape) == w
        assert groups[EndpointGroupName.NH_FAILED_CONNECTIONS].cost_fn(shape) == w
        assert groups[EndpointGroupName.NH_LATENCY_STATS].cost_fn(shape) == 2 * w
        assert groups[EndpointGroupName.NH_AIR_MARSHAL].cost_fn(shape) == w
        assert groups[EndpointGroupName.NH_MESH].cost_fn(shape) == w


class TestNetworkHealthGating(BaseCollectorTest):
    """Per-group gating in the org collection path."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    def _build(self, settings, isolated_registry, inventory, mock_api_builder, scheduler):
        """Construct a NetworkHealthCollector wired to the fake scheduler."""
        org = OrganizationFactory.create(org_id="O1", name="Org")
        api = mock_api_builder.with_organizations([org]).build()
        inventory.api = api
        return NetworkHealthCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=scheduler,
        )

    def _instrument(self, collector) -> dict[str, list[Any]]:
        """Replace every sub-collector entry point with a call recorder."""
        calls: dict[str, list[Any]] = {
            name: [] for name in ("rf", "conn", "data", "bt", "ssid", "lat", "air", "mesh")
        }

        async def _rf(org_id, org_name, networks):
            calls["rf"].append(org_id)
            # collect_org now returns True on a successful org-wide fetch (#629);
            # the coordinator marks NH_CHANNEL_UTILIZATION ran only on True.
            return True

        async def _conn(network):
            calls["conn"].append(network["id"])

        async def _data(network):
            calls["data"].append(network["id"])

        async def _bt(network):
            calls["bt"].append(network["id"])

        async def _ssid(network):
            calls["ssid"].append(network["id"])

        async def _lat(network):
            calls["lat"].append(network["id"])

        async def _air(network):
            calls["air"].append(network["id"])

        async def _mesh(network):
            calls["mesh"].append(network["id"])

        collector.rf_health_collector.collect_org = _rf  # type: ignore[method-assign]
        collector.connection_stats_collector.collect = _conn  # type: ignore[method-assign]
        collector.data_rates_collector.collect = _data  # type: ignore[method-assign]
        collector.bluetooth_collector.collect = _bt  # type: ignore[method-assign]
        collector.ssid_performance_collector.collect = _ssid  # type: ignore[method-assign]
        collector.latency_stats_collector.collect = _lat  # type: ignore[method-assign]
        collector.air_marshal_collector.collect = _air  # type: ignore[method-assign]
        collector.mesh_collector.collect = _mesh  # type: ignore[method-assign]
        return calls

    @staticmethod
    def _wireless_net() -> dict[str, Any]:
        """Return one wireless network dict in org O1."""
        return dict(NetworkFactory.create(network_id="N1", product_types=["wireless"], org_id="O1"))

    async def test_all_due_runs_everything_and_marks(
        self, settings, isolated_registry, inventory, mock_api_builder
    ):
        """Every group due => every sub-collector runs and every group is marked ran."""
        scheduler = FakeScheduler(due=None)
        collector = self._build(settings, isolated_registry, inventory, mock_api_builder, scheduler)
        calls = self._instrument(collector)

        async def _fetch(org_id):
            return [self._wireless_net()]

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]
        await collector._collect_org_network_health("O1", "Org")

        assert calls["rf"] == ["O1"]
        for key in ("conn", "data", "bt", "ssid", "lat", "air", "mesh"):
            assert calls[key] == ["N1"], key
        assert set(scheduler.marked) == _ALL_NH_GROUPS

    async def test_only_due_groups_run(
        self, settings, isolated_registry, inventory, mock_api_builder
    ):
        """Only the due groups' sub-collectors run and only they are marked ran."""
        due = {EndpointGroupName.NH_CHANNEL_UTILIZATION, EndpointGroupName.NH_CONNECTION_STATS}
        scheduler = FakeScheduler(due=due)
        collector = self._build(settings, isolated_registry, inventory, mock_api_builder, scheduler)
        calls = self._instrument(collector)

        async def _fetch(org_id):
            return [self._wireless_net()]

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]
        await collector._collect_org_network_health("O1", "Org")

        assert calls["rf"] == ["O1"]
        assert calls["conn"] == ["N1"]
        for key in ("data", "bt", "ssid", "lat", "air", "mesh"):
            assert calls[key] == [], key
        assert set(scheduler.marked) == due

    async def test_channel_util_not_due_skips_org_fetch(
        self, settings, isolated_registry, inventory, mock_api_builder
    ):
        """Channel-util not due => org-wide fetch skipped, other seven still run."""
        scheduler = FakeScheduler(due=_BUNDLE_GROUPS)
        collector = self._build(settings, isolated_registry, inventory, mock_api_builder, scheduler)
        calls = self._instrument(collector)

        async def _fetch(org_id):
            return [self._wireless_net()]

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]
        await collector._collect_org_network_health("O1", "Org")

        assert calls["rf"] == []
        assert EndpointGroupName.NH_CHANNEL_UTILIZATION not in scheduler.marked
        for key in ("conn", "data", "bt", "ssid", "lat", "air", "mesh"):
            assert calls[key] == ["N1"], key

    async def test_nothing_due_marks_nothing(
        self, settings, isolated_registry, inventory, mock_api_builder
    ):
        """No group due => nothing runs and nothing is marked ran."""
        scheduler = FakeScheduler(due=set())
        collector = self._build(settings, isolated_registry, inventory, mock_api_builder, scheduler)
        calls = self._instrument(collector)

        async def _fetch(org_id):
            return [self._wireless_net()]

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]
        await collector._collect_org_network_health("O1", "Org")

        for key, seen in calls.items():
            assert seen == [], key
        assert scheduler.marked == []


class TestTtlThreading(BaseCollectorTest):
    """ttl_seconds from the group is forwarded to _set_metric on every write."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    async def test_bundle_subcollectors_thread_ttl(
        self, settings, isolated_registry, inventory, mock_api_builder
    ):
        """Bluetooth writes forward the scheduler-provided TTL to _set_metric."""
        scheduler = FakeScheduler(due=None, ttl=999.0)
        org = OrganizationFactory.create(org_id="O1", name="Org")
        api = mock_api_builder.with_organizations([org]).build()
        inventory.api = api
        collector = NetworkHealthCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=scheduler,
        )

        seen_ttls: list[float | None] = []
        real_set_metric = collector._set_metric

        def _spy(metric, labels, value, metric_name=None, ttl_seconds=None):
            seen_ttls.append(ttl_seconds)
            return real_set_metric(metric, labels, value, metric_name, ttl_seconds=ttl_seconds)

        collector._set_metric = _spy  # type: ignore[method-assign]

        network = {"id": "N1", "orgId": "O1", "orgName": "Org", "name": "Net"}
        collector.bluetooth_collector.api = api
        api.networks.getNetworkBluetoothClients = MagicMock(return_value=[])
        await collector.bluetooth_collector.collect(network)

        assert seen_ttls, "expected at least one metric write"
        assert all(ttl == 999.0 for ttl in seen_ttls)
