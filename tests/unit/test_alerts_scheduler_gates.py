"""Wave-2 scheduler gate tests for AlertsCollector (#617 §2, AC lane).

Covers:
- ``AlertsCollector.endpoint_groups`` declares exactly the two §2 alerts rows
  (``alerts_assurance`` pri1 floor300, ``alerts_sensor_overview`` pri2 floor300)
  with the MEDIUM heartbeat and no setting_pins.
- The assurance fetch site gates on ``_should_run_group(ALERTS_ASSURANCE)`` and
  calls ``_mark_group_ran`` only after a successful fetch.
- The sensor-overview fetch site gates the same way on
  ``ALERTS_SENSOR_OVERVIEW``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.alerts import AlertsCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, OrgShape
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, NetworkFactory, OrganizationFactory

_EXPECTED_ALERTS_GROUPS = {
    EndpointGroupName.ALERTS_ASSURANCE,
    EndpointGroupName.ALERTS_SENSOR_OVERVIEW,
}


def _shape(**overrides: int) -> OrgShape:
    """Build a sample OrgShape, overriding selected counts."""
    base: dict[str, int | str] = {
        "org_id": "org1",
        "network_count": 10,
        "wireless_network_count": 4,
        "switch_network_count": 3,
        "appliance_network_count": 2,
        "sensor_network_count": 5,
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


class TestAlertsEndpointGroups:
    """AlertsCollector.endpoint_groups declaration (#617 §2, task A)."""

    def test_covers_exactly_the_two_alerts_rows(self) -> None:
        """Exactly the two alerts rows are declared."""
        declared = {g.name for g in AlertsCollector.endpoint_groups}
        assert declared == _EXPECTED_ALERTS_GROUPS

    def test_priorities_and_floors(self) -> None:
        """Priorities and volatility floors match the spec table."""
        by_name = {g.name: g for g in AlertsCollector.endpoint_groups}
        assert by_name[EndpointGroupName.ALERTS_ASSURANCE].priority == 1
        assert by_name[EndpointGroupName.ALERTS_ASSURANCE].floor_seconds == 300
        assert by_name[EndpointGroupName.ALERTS_SENSOR_OVERVIEW].priority == 2
        assert by_name[EndpointGroupName.ALERTS_SENSOR_OVERVIEW].floor_seconds == 300

    def test_no_setting_pins(self) -> None:
        """Neither alerts group carries a legacy setting_pin."""
        assert all(g.setting_pin is None for g in AlertsCollector.endpoint_groups)

    def test_cost_formulas(self) -> None:
        """cost_fn evaluates to the §2 formulas for a sample shape."""
        by_name = {g.name: g for g in AlertsCollector.endpoint_groups}
        # alerts_assurance: ~1 page of org-wide assurance alerts.
        assert by_name[EndpointGroupName.ALERTS_ASSURANCE].cost_fn(_shape()) == 1
        # alerts_sensor_overview: one call per sensor network (Sn).
        assert (
            by_name[EndpointGroupName.ALERTS_SENSOR_OVERVIEW].cost_fn(
                _shape(sensor_network_count=7)
            )
            == 7
        )


class TestAlertsAssuranceGate(BaseCollectorTest):
    """assurance fetch-site gate (#617 §2 alerts_assurance)."""

    collector_class = AlertsCollector

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, sched):
        """Build an AlertsCollector with a mocked scheduler and empty assurance data."""
        org = OrganizationFactory.create(org_id="123", name="Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices([], org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .build()
        )
        inventory.api = api
        return AlertsCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )

    @staticmethod
    def _sched(assurance_due: bool, sensor_due: bool) -> MagicMock:
        """Return a mock scheduler with per-group due answers."""
        due = {
            EndpointGroupName.ALERTS_ASSURANCE: assurance_due,
            EndpointGroupName.ALERTS_SENSOR_OVERVIEW: sensor_due,
        }
        sched = MagicMock()
        sched.should_run.side_effect = lambda g, *a, **k: due[g]
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.return_value = 300.0
        return sched

    async def test_skips_assurance_when_not_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=False ⇒ assurance never fetched, group never marked ran."""
        sched = self._sched(assurance_due=False, sensor_due=False)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        await collector.collect()

        collector.api.organizations.getOrganizationAssuranceAlerts.assert_not_called()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.ALERTS_ASSURANCE not in marked

    async def test_fetches_and_marks_assurance_when_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=True ⇒ assurance fetched, then group marked ran."""
        sched = self._sched(assurance_due=True, sensor_due=False)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        await collector.collect()

        collector.api.organizations.getOrganizationAssuranceAlerts.assert_called_once()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.ALERTS_ASSURANCE in marked


class TestAlertsSensorGate(BaseCollectorTest):
    """sensor-overview fetch-site gate (#617 §2 alerts_sensor_overview)."""

    collector_class = AlertsCollector

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, sched):
        """Build an AlertsCollector wired with a sensor network and mocked scheduler."""
        org = OrganizationFactory.create(org_id="123", name="Org")
        net = NetworkFactory.create(network_id="N_123", name="Net", org_id="123")
        sensor_devices = [
            DeviceFactory.create_mt(
                network_id="N_123", productType="sensor", serial="Q2MT-XXXX-0001"
            )
        ]
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([net], org_id="123")
            .with_devices(sensor_devices, org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getNetworkSensorAlertsOverviewByMetric", [])
            .build()
        )
        inventory.api = api
        return AlertsCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )

    @staticmethod
    def _sched(sensor_due: bool) -> MagicMock:
        """Return a mock scheduler with assurance always due and sensor toggled."""
        due = {
            EndpointGroupName.ALERTS_ASSURANCE: True,
            EndpointGroupName.ALERTS_SENSOR_OVERVIEW: sensor_due,
        }
        sched = MagicMock()
        sched.should_run.side_effect = lambda g, *a, **k: due[g]
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.return_value = 300.0
        return sched

    async def test_skips_sensor_when_not_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=False ⇒ sensor overview never fetched, group never marked."""
        sched = self._sched(sensor_due=False)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        await collector.collect()

        collector.api.sensor.getNetworkSensorAlertsOverviewByMetric.assert_not_called()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.ALERTS_SENSOR_OVERVIEW not in marked

    async def test_fetches_and_marks_sensor_when_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=True ⇒ sensor overview fetched, then group marked ran."""
        sched = self._sched(sensor_due=True)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        await collector.collect()

        collector.api.sensor.getNetworkSensorAlertsOverviewByMetric.assert_called_once()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.ALERTS_SENSOR_OVERVIEW in marked
