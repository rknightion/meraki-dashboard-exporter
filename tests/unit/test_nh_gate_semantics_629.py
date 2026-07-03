"""#629: NetworkHealthCollector mark_ran semantics.

Canonical rule (#629): an endpoint group's gate is marked ran iff the cycle
achieved >=1 SUCCESSFUL fetch for that group.

- Partial fan-out success counts (one network 500'ing must NOT re-fetch the
  whole org) -> mark ran.
- Total failure (every network's fetch for that group failed) -> do NOT mark
  ran -> gate stays open -> next cycle retries.
- A SUCCESSFUL fetch returning empty is a successful cycle -> mark ran.

Two fix sites:
1. NH_CHANNEL_UTILIZATION (org-wide, via ``rf_health_collector.collect_org``).
2. The six-per-network bundle groups sharing one ``process_in_batches_with_errors``
   fan-out over ``_collect_network_health_bundle``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory


class _NHGateBase(BaseCollectorTest):
    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    def _make(self, mock_api_builder, settings, isolated_registry, inventory, sched):
        org = OrganizationFactory.create(org_id="org1")
        api = mock_api_builder.with_organizations([org]).build()
        inventory.api = api
        return NetworkHealthCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )

    @staticmethod
    def _wireless(*network_ids: str) -> list[dict]:
        return [
            NetworkFactory.create(
                network_id=nid,
                name=nid,
                product_types=["wireless"],
                org_id="org1",
            )
            for nid in network_ids
        ]

    @staticmethod
    def _marked(sched) -> list[EndpointGroupName]:
        return [c.args[0] for c in sched.mark_ran.call_args_list]


class TestChannelUtilizationGate(_NHGateBase):
    """NH_CHANNEL_UTILIZATION marks ran iff collect_org signalled success."""

    def _sched_only_channel_util(self):
        sched = MagicMock()
        sched.should_run.side_effect = (
            lambda g: g is EndpointGroupName.NH_CHANNEL_UTILIZATION
        )
        return sched

    async def test_total_failure_not_marked(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """collect_org reporting failure (False) leaves the gate open."""
        sched = self._sched_only_channel_util()
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def _fetch(org_id):
            return self._wireless("N_1")

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]

        async def _collect_org(org_id, org_name, networks):
            return False

        collector.rf_health_collector.collect_org = _collect_org  # type: ignore[method-assign]

        await collector._collect_org_network_health("org1", "Org One")

        assert EndpointGroupName.NH_CHANNEL_UTILIZATION not in self._marked(sched)

    async def test_success_marks_ran(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """collect_org reporting success (True, incl. empty) marks the gate ran."""
        sched = self._sched_only_channel_util()
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def _fetch(org_id):
            return self._wireless("N_1")

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]

        async def _collect_org(org_id, org_name, networks):
            return True

        collector.rf_health_collector.collect_org = _collect_org  # type: ignore[method-assign]

        await collector._collect_org_network_health("org1", "Org One")

        assert EndpointGroupName.NH_CHANNEL_UTILIZATION in self._marked(sched)


class TestBundleGroupGate(_NHGateBase):
    """The per-network bundle groups mark ran per-group by union-of-successes."""

    def _sched_bundle(self, due: set[EndpointGroupName]):
        sched = MagicMock()
        sched.should_run.side_effect = lambda g: g in due
        return sched

    async def test_group_total_failure_not_marked(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A group that failed for EVERY network is not marked; a sibling succeeds."""
        due = {
            EndpointGroupName.NH_CONNECTION_STATS,
            EndpointGroupName.NH_DATA_RATES,
        }
        sched = self._sched_bundle(due)
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def _fetch(org_id):
            return self._wireless("N_1", "N_2")

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]

        async def _boom(network):
            raise Exception("500 server error")

        async def _ok(network):
            return None

        collector._collect_network_connection_stats = _boom  # type: ignore[method-assign]
        collector._collect_network_data_rates = _ok  # type: ignore[method-assign]

        await collector._collect_org_network_health("org1", "Org One")

        marked = self._marked(sched)
        assert EndpointGroupName.NH_CONNECTION_STATS not in marked
        assert EndpointGroupName.NH_DATA_RATES in marked

    async def test_group_partial_success_marks_ran(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A group that succeeded on >=1 network (failed on another) is marked."""
        due = {EndpointGroupName.NH_CONNECTION_STATS}
        sched = self._sched_bundle(due)
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def _fetch(org_id):
            return self._wireless("N_1", "N_2")

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]

        async def _partial(network):
            if network["id"] == "N_1":
                raise Exception("500 server error")

        collector._collect_network_connection_stats = _partial  # type: ignore[method-assign]

        await collector._collect_org_network_health("org1", "Org One")

        assert EndpointGroupName.NH_CONNECTION_STATS in self._marked(sched)

    async def test_group_empty_success_marks_ran(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A successful fetch (returning nothing) still marks the group ran."""
        due = {EndpointGroupName.NH_BLUETOOTH}
        sched = self._sched_bundle(due)
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def _fetch(org_id):
            return self._wireless("N_1")

        collector._fetch_networks_for_health = _fetch  # type: ignore[method-assign]

        async def _ok(network):
            return None

        collector._collect_network_bluetooth_clients = _ok  # type: ignore[method-assign]

        await collector._collect_org_network_health("org1", "Org One")

        assert EndpointGroupName.NH_BLUETOOTH in self._marked(sched)
