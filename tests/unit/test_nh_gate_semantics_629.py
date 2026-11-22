"""Network-health groups report success when at least one fetch succeeds (#629).

Channel utilization uses this to close its org-wide gate. The self-paced
bundle groups still report partial and empty successes, but independently
retry failed networks instead of closing the whole group's gate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory


class _NHGateBase(BaseCollectorTest):
    collector_class = NetworkHealthCollector

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
        sched.should_run.side_effect = lambda g: g is EndpointGroupName.NH_CHANNEL_UTILIZATION
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
        sched.should_run.return_value = False  # org-wide channel utilization is not due
        sched.is_enabled.side_effect = lambda g: g in due
        return sched

    async def test_real_subcollector_total_failure_not_marked(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """Real connection fetch failures leave the group open."""
        sched = self._sched_bundle({EndpointGroupName.NH_CONNECTION_STATS})
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def fetch_networks(org_id):
            return self._wireless("N_1", "N_2")

        collector._fetch_networks_for_health = fetch_networks
        collector.api.wireless.getNetworkWirelessConnectionStats = MagicMock(
            side_effect=Exception("500 server error")
        )
        collector._track_error = MagicMock()
        collector._set_metric = MagicMock()
        await collector._collect_org_network_health("org1", "Org One")
        assert EndpointGroupName.NH_CONNECTION_STATS not in self._marked(sched)
        collector._track_error.assert_called()
        collector._set_metric.assert_not_called()

    async def test_real_subcollector_partial_failure_marks_ran(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """One answered connection fetch reports success for the group."""
        sched = self._sched_bundle({EndpointGroupName.NH_CONNECTION_STATS})
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def fetch_networks(org_id):
            return self._wireless("N_1", "N_2")

        def fetch(network_id, **kwargs):
            if network_id == "N_1":
                raise Exception("500 server error")
            return {"connectionStats": {}}

        collector._fetch_networks_for_health = fetch_networks
        collector.api.wireless.getNetworkWirelessConnectionStats = MagicMock(side_effect=fetch)
        await collector._collect_org_network_health("org1", "Org One")
        assert EndpointGroupName.NH_CONNECTION_STATS in self._marked(sched)

    @pytest.mark.parametrize(
        "message", ["400 Bad Request", "404 Not Found", "rate limit", "500 server error"]
    )
    @pytest.mark.parametrize(
        ("group", "namespace", "method"),
        [
            (
                EndpointGroupName.NH_CONNECTION_STATS,
                "wireless",
                "getNetworkWirelessConnectionStats",
            ),
            (EndpointGroupName.NH_DATA_RATES, "wireless", "getNetworkWirelessDataRateHistory"),
            (EndpointGroupName.NH_BLUETOOTH, "networks", "getNetworkBluetoothClients"),
            (
                EndpointGroupName.NH_FAILED_CONNECTIONS,
                "wireless",
                "getNetworkWirelessFailedConnections",
            ),
            (EndpointGroupName.NH_MESH, "wireless", "getNetworkWirelessMeshStatuses"),
        ],
    )
    async def test_real_subcollector_unavailable_and_rate_limit(
        self,
        mock_api_builder,
        settings,
        isolated_registry,
        inventory,
        message,
        group,
        namespace,
        method,
    ):
        """Unavailable endpoints count as successful skips; real failures do not."""
        sched = self._sched_bundle({group})
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def fetch_networks(org_id):
            return self._wireless("N_1")

        collector._fetch_networks_for_health = fetch_networks
        setattr(
            getattr(collector.api, namespace), method, MagicMock(side_effect=Exception(message))
        )
        collector._set_metric = MagicMock()
        await collector._collect_org_network_health("org1", "Org One")
        assert (group in self._marked(sched)) == ("400" in message or "404" in message)
        collector._set_metric.assert_not_called()

    async def test_real_latency_total_failure_not_marked(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A failed latency fetch leaves the group open."""
        sched = self._sched_bundle({EndpointGroupName.NH_LATENCY_STATS})
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def fetch_networks(org_id):
            return self._wireless("N_1", "N_2")

        collector._fetch_networks_for_health = fetch_networks
        collector.api.wireless.getNetworkWirelessDevicesLatencyStats = MagicMock(
            side_effect=Exception("500 server error")
        )
        collector.api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(return_value=[])
        collector._track_error = MagicMock()
        collector._set_metric = MagicMock()
        await collector._collect_org_network_health("org1", "Org One")
        assert EndpointGroupName.NH_LATENCY_STATS not in self._marked(sched)
        collector._track_error.assert_called()
        collector._set_metric.assert_not_called()

    @pytest.mark.parametrize("message", ["402 unavailable", "404 unavailable", "500 server error"])
    @pytest.mark.parametrize(
        ("group", "method"),
        [
            (EndpointGroupName.NH_LATENCY_STATS, "getNetworkWirelessDevicesLatencyStats"),
            (EndpointGroupName.NH_AIR_MARSHAL, "getNetworkWirelessAirMarshal"),
        ],
    )
    async def test_decorated_subcollector_unavailable_or_failure(
        self, mock_api_builder, settings, isolated_registry, inventory, group, method, message
    ):
        """Decorated fetchers distinguish unavailable endpoints from failures."""
        sched = self._sched_bundle({group})
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def fetch_networks(org_id):
            return self._wireless("N_1")

        collector._fetch_networks_for_health = fetch_networks
        setattr(collector.api.wireless, method, MagicMock(side_effect=Exception(message)))
        collector.api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(return_value=[])
        collector._set_metric = MagicMock()
        await collector._collect_org_network_health("org1", "Org One")
        assert (group in self._marked(sched)) == ("500" not in message)
        collector._set_metric.assert_not_called()

    @pytest.mark.parametrize(
        ("group", "method"),
        [
            (EndpointGroupName.NH_LATENCY_STATS, "getNetworkWirelessDevicesLatencyStats"),
            (EndpointGroupName.NH_AIR_MARSHAL, "getNetworkWirelessAirMarshal"),
        ],
    )
    async def test_decorated_subcollector_exhausted_rate_limit(
        self, mock_api_builder, settings, isolated_registry, inventory, monkeypatch, group, method
    ):
        """Exhausted decorator retries leave the group open and emit nothing."""
        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.error_handling.asyncio.sleep", AsyncMock()
        )
        sched = self._sched_bundle({group})
        collector = self._make(mock_api_builder, settings, isolated_registry, inventory, sched)

        async def fetch_networks(org_id):
            return self._wireless("N_1")

        collector._fetch_networks_for_health = fetch_networks
        setattr(
            collector.api.wireless,
            method,
            MagicMock(side_effect=Exception("rate limit exceeded")),
        )
        collector.api.wireless.getNetworkWirelessClientsLatencyStats = MagicMock(return_value=[])
        collector._set_metric = MagicMock()
        await collector._collect_org_network_health("org1", "Org One")
        assert group not in self._marked(sched)
        collector._set_metric.assert_not_called()

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
