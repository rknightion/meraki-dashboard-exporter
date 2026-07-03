"""Wave-2 scheduler gate tests for ClientsCollector (#617 §2, AC lane).

Covers:
- ``ClientsCollector.endpoint_groups`` declares the three §2 client rows
  (``clients_list`` pri3 floor300; ``clients_app_usage`` pri4 floor600 pinned by
  ``client_app_usage_interval``; ``clients_signal_quality`` pri4 floor600 pinned
  by ``client_signal_quality_interval``), MEDIUM heartbeat.
- ``get_endpoint_groups()`` returns ``()`` when ``clients.enabled`` is False.
- The ``clients_list`` fetch site gates on ``_should_run_group`` and marks the
  group ran only after the network fan-out completes.
- The existing per-network ``app_usage`` / ``signal_quality`` interval gates read
  their interval from ``_group_interval(GROUP)`` (the scheduler), not the raw
  legacy setting.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from meraki_dashboard_exporter.collectors.clients import ClientsCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, OrgShape
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import ClientFactory, NetworkFactory, OrganizationFactory

_EXPECTED_CLIENT_GROUPS = {
    EndpointGroupName.CLIENTS_LIST,
    EndpointGroupName.CLIENTS_APP_USAGE,
    EndpointGroupName.CLIENTS_SIGNAL_QUALITY,
}


def _shape(**overrides: int) -> OrgShape:
    """Build a sample OrgShape, overriding selected counts."""
    base: dict[str, int | str] = {
        "org_id": "org1",
        "network_count": 10,
        "wireless_network_count": 4,
        "switch_network_count": 3,
        "appliance_network_count": 2,
        "sensor_network_count": 1,
        "camera_network_count": 1,
        "cellular_network_count": 1,
        "device_count": 100,
        "ap_count": 40,
        "switch_count": 30,
        "appliance_count": 5,
        "physical_mx_count": 4,
        "camera_count": 6,
        "sensor_count": 8,
        "cellular_count": 2,
    }
    base.update(overrides)
    return OrgShape(**base)  # type: ignore[arg-type]


class TestClientsEndpointGroups:
    """ClientsCollector.endpoint_groups declaration (#617 §2, task A)."""

    def test_covers_the_three_client_rows(self) -> None:
        """Exactly the three client rows are declared."""
        declared = {g.name for g in ClientsCollector.endpoint_groups}
        assert declared == _EXPECTED_CLIENT_GROUPS

    def test_priorities_and_floors(self) -> None:
        """Priorities and floors match the §2 table."""
        by_name = {g.name: g for g in ClientsCollector.endpoint_groups}
        assert by_name[EndpointGroupName.CLIENTS_LIST].priority == 3
        assert by_name[EndpointGroupName.CLIENTS_LIST].floor_seconds == 300
        assert by_name[EndpointGroupName.CLIENTS_APP_USAGE].priority == 4
        assert by_name[EndpointGroupName.CLIENTS_APP_USAGE].floor_seconds == 600
        assert by_name[EndpointGroupName.CLIENTS_SIGNAL_QUALITY].priority == 4
        assert by_name[EndpointGroupName.CLIENTS_SIGNAL_QUALITY].floor_seconds == 600

    def test_setting_pins(self) -> None:
        """app_usage / signal_quality carry their legacy interval setting_pins."""
        pins = {g.name: g.setting_pin for g in ClientsCollector.endpoint_groups if g.setting_pin}
        assert pins == {
            EndpointGroupName.CLIENTS_APP_USAGE: "client_app_usage_interval",
            EndpointGroupName.CLIENTS_SIGNAL_QUALITY: "client_signal_quality_interval",
        }

    def test_cost_formulas(self) -> None:
        """cost_fn evaluates to the §2 formulas for a sample shape."""
        by_name = {g.name: g for g in ClientsCollector.endpoint_groups}
        # clients_list: N x pages(clients, 5000) ~ N.
        assert by_name[EndpointGroupName.CLIENTS_LIST].cost_fn(_shape(network_count=12)) == 12
        # clients_app_usage: N x ceil(clients/1000) ~ N.
        assert by_name[EndpointGroupName.CLIENTS_APP_USAGE].cost_fn(_shape(network_count=12)) == 12
        # clients_signal_quality: wireless nets x per-network cap (200).
        assert (
            by_name[EndpointGroupName.CLIENTS_SIGNAL_QUALITY].cost_fn(
                _shape(wireless_network_count=3)
            )
            == 600
        )


class TestClientsGetEndpointGroups(BaseCollectorTest):
    """get_endpoint_groups() drops all groups when clients are disabled."""

    collector_class = ClientsCollector

    def _make(self, settings, isolated_registry, inventory, *, enabled: bool) -> ClientsCollector:
        """Construct a ClientsCollector with clients enabled/disabled."""
        settings.clients.enabled = enabled
        api = MagicMock()
        inventory.api = api
        return ClientsCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
        )

    def test_groups_present_when_enabled(self, settings, isolated_registry, inventory) -> None:
        """Enabled ⇒ all three groups reported to the solver."""
        collector = self._make(settings, isolated_registry, inventory, enabled=True)
        assert {g.name for g in collector.get_endpoint_groups()} == _EXPECTED_CLIENT_GROUPS

    def test_no_groups_when_disabled(self, settings, isolated_registry, inventory) -> None:
        """Disabled ⇒ no groups enter the solver's demand accounting."""
        collector = self._make(settings, isolated_registry, inventory, enabled=False)
        assert collector.get_endpoint_groups() == ()


class TestClientsListGate(BaseCollectorTest):
    """clients_list fetch-site gate (#617 §2 clients_list)."""

    collector_class = ClientsCollector

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, sched):
        """Build an enabled ClientsCollector with one network + client."""
        settings.clients.enabled = True
        org = OrganizationFactory.create(org_id="123", name="Org")
        net = NetworkFactory.create(network_id="N_123", name="Net", org_id="123")
        clients = [ClientFactory.create(client_id="c1", mac="aa:bb:cc:dd:ee:01")]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([net], org_id="123")
            .with_custom_response("getNetworkClients", clients)
            .build()
        )
        inventory.api = api
        collector = ClientsCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )
        collector.api_helper.api = api
        return collector

    @staticmethod
    def _sched(list_due: bool) -> MagicMock:
        """Return a mock scheduler that toggles the clients_list group."""
        sched = MagicMock()
        sched.should_run.side_effect = lambda g, *a, **k: (
            list_due if g is EndpointGroupName.CLIENTS_LIST else True
        )
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.return_value = 300.0
        return sched

    async def test_skips_client_list_when_not_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=False ⇒ getNetworkClients never called, group not marked."""
        sched = self._sched(list_due=False)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()

        collector.api.networks.getNetworkClients.assert_not_called()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.CLIENTS_LIST not in marked

    async def test_fetches_and_marks_client_list_when_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=True ⇒ getNetworkClients fetched, then clients_list marked."""
        sched = self._sched(list_due=True)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()

        collector.api.networks.getNetworkClients.assert_called_once()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.CLIENTS_LIST in marked


class TestClientsAppUsageIntervalSource(BaseCollectorTest):
    """app_usage per-network gate reads its interval from _group_interval."""

    collector_class = ClientsCollector

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, app_interval):
        """Build an enabled ClientsCollector whose scheduler pins the app-usage interval."""
        settings.clients.enabled = True
        # Legacy raw setting deliberately SHORTER than the scheduler interval so a
        # regression to reading the raw setting would (wrongly) run the fetch.
        settings.api.client_app_usage_interval = 300
        org = OrganizationFactory.create(org_id="123", name="Org")
        net = NetworkFactory.create(network_id="N_123", name="Net", org_id="123")
        clients = [ClientFactory.create(client_id="c1", mac="aa:bb:cc:dd:ee:01")]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([net], org_id="123")
            .with_custom_response("getNetworkClients", clients)
            .with_custom_response("getNetworkClientsApplicationUsage", [])
            .build()
        )
        inventory.api = api

        sched = MagicMock()
        sched.should_run.return_value = True
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.side_effect = lambda g: (
            app_interval if g is EndpointGroupName.CLIENTS_APP_USAGE else 300.0
        )

        collector = ClientsCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )
        collector.api_helper.api = api
        # Seed a run 700s ago: gated if the scheduler interval (1200) is used,
        # but would run if the raw 300s setting were consulted.
        collector._last_app_usage_by_network["N_123"] = time.time() - 700
        return collector

    async def test_app_usage_gated_by_scheduler_interval(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Scheduler interval 1200 > 700 elapsed ⇒ app usage skipped."""
        collector = self._build(
            mock_api_builder, settings, isolated_registry, inventory, app_interval=1200.0
        )
        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()
        collector.api.networks.getNetworkClientsApplicationUsage.assert_not_called()

    async def test_app_usage_runs_when_scheduler_interval_elapsed(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Scheduler interval 500 < 700 elapsed ⇒ app usage runs."""
        collector = self._build(
            mock_api_builder, settings, isolated_registry, inventory, app_interval=500.0
        )
        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()
        collector.api.networks.getNetworkClientsApplicationUsage.assert_called()


class TestClientsSignalQualityIntervalSource(BaseCollectorTest):
    """signal_quality per-network gate reads its interval from _group_interval."""

    collector_class = ClientsCollector

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, sq_interval):
        """Build an enabled ClientsCollector whose scheduler pins the signal-quality interval."""
        settings.clients.enabled = True
        settings.clients.signal_quality_enabled = True
        settings.api.client_signal_quality_interval = 300
        org = OrganizationFactory.create(org_id="123", name="Org")
        net = NetworkFactory.create(network_id="N_123", name="Net", org_id="123")
        clients = [
            ClientFactory.create(
                client_id="c1", mac="aa:bb:cc:dd:ee:01", recentDeviceConnection="Wireless"
            )
        ]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([net], org_id="123")
            .with_custom_response("getNetworkClients", clients)
            .with_custom_response(
                "getNetworkWirelessSignalQualityHistory", [{"rssi": -50, "snr": 40}]
            )
            .build()
        )
        inventory.api = api

        sched = MagicMock()
        sched.should_run.return_value = True
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.side_effect = lambda g: (
            sq_interval if g is EndpointGroupName.CLIENTS_SIGNAL_QUALITY else 300.0
        )

        collector = ClientsCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )
        collector.api_helper.api = api
        collector._last_signal_quality_by_network["N_123"] = time.time() - 700
        return collector

    async def test_signal_quality_gated_by_scheduler_interval(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Scheduler interval 1200 > 700 elapsed ⇒ signal quality skipped."""
        collector = self._build(
            mock_api_builder, settings, isolated_registry, inventory, sq_interval=1200.0
        )
        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()
        collector.api.wireless.getNetworkWirelessSignalQualityHistory.assert_not_called()

    async def test_signal_quality_runs_when_scheduler_interval_elapsed(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Scheduler interval 500 < 700 elapsed ⇒ signal quality runs."""
        collector = self._build(
            mock_api_builder, settings, isolated_registry, inventory, sq_interval=500.0
        )
        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()
        collector.api.wireless.getNetworkWirelessSignalQualityHistory.assert_called()
