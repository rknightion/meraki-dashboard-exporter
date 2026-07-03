"""Wave-2 scheduler gate tests for ConfigCollector (#617 §2, AC lane).

Covers:
- ``ConfigCollector.endpoint_groups`` declares exactly the single ``config_org``
  row (pri4 floor900, SLOW heartbeat, no setting_pin).
- The whole SLOW config cycle gates on ``_should_run_group(CONFIG_ORG)`` and
  calls ``_mark_group_ran`` only after a successful cycle.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.config import ConfigCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, OrgShape
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import OrganizationFactory


def _shape() -> OrgShape:
    """Build a sample OrgShape for cost-formula checks."""
    return OrgShape(
        org_id="org1",
        network_count=10,
        wireless_network_count=4,
        switch_network_count=3,
        appliance_network_count=2,
        sensor_network_count=1,
        camera_network_count=1,
        cellular_network_count=1,
        device_count=100,
        ap_count=40,
        switch_count=30,
        appliance_count=5,
        physical_mx_count=4,
        camera_count=6,
        sensor_count=8,
        cellular_count=2,
    )


class TestConfigEndpointGroups:
    """ConfigCollector.endpoint_groups declaration (#617 §2, task A)."""

    def test_single_config_org_group(self) -> None:
        """Exactly the config_org group is declared."""
        declared = {g.name for g in ConfigCollector.endpoint_groups}
        assert declared == {EndpointGroupName.CONFIG_ORG}

    def test_tier_priority_floor(self) -> None:
        """The config_org group is SLOW-tier, pri4, floor 900, no pin."""
        g = ConfigCollector.endpoint_groups[0]
        assert g.tier is UpdateTier.SLOW
        assert g.priority == 4
        assert g.floor_seconds == 900
        assert g.setting_pin is None

    def test_cost_is_four_calls(self) -> None:
        """cost_fn is a flat 4 API calls per cycle."""
        # login security + admins + config changes + SAML posture (#301) = ~4
        # API calls per cycle (+1 more when SAML is enabled, not modelled).
        assert ConfigCollector.endpoint_groups[0].cost_fn(_shape()) == 4


class TestConfigOrgGate(BaseCollectorTest):
    """config_org cycle gate (#617 §2 config_org)."""

    collector_class = ConfigCollector
    update_tier = UpdateTier.SLOW

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, sched):
        """Build a ConfigCollector with empty config responses and a mock scheduler."""
        org = OrganizationFactory.create(org_id="123", name="Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices([], org_id="123")
            .with_custom_response("getOrganizationLoginSecurity", {})
            .with_custom_response("getOrganizationAdmins", [])
            .with_custom_response("getOrganizationConfigurationChanges", [])
            .build()
        )
        inventory.api = api
        return ConfigCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=sched,
        )

    @staticmethod
    def _sched(due: bool) -> MagicMock:
        """Return a mock scheduler whose should_run answers ``due``."""
        sched = MagicMock()
        sched.should_run.return_value = due
        sched.ttl_seconds_for.return_value = 1800.0
        sched.interval_for.return_value = 900.0
        return sched

    async def test_skips_cycle_when_not_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=False ⇒ no config API calls, group never marked ran."""
        sched = self._sched(due=False)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        await collector.collect()

        collector.api.organizations.getOrganizationLoginSecurity.assert_not_called()
        collector.api.organizations.getOrganizationAdmins.assert_not_called()
        sched.mark_ran.assert_not_called()

    async def test_runs_and_marks_cycle_when_due(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """should_run=True ⇒ config fetched, then config_org marked ran once."""
        sched = self._sched(due=True)
        collector = self._build(mock_api_builder, settings, isolated_registry, inventory, sched)

        await collector.collect()

        collector.api.organizations.getOrganizationLoginSecurity.assert_called_once()
        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert marked == [EndpointGroupName.CONFIG_ORG]
