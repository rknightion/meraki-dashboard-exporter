"""Tests for #617 scheduler gating on the OrganizationCollector lane.

Covers the fourteen org endpoint-group declarations (names/priority/floor/
cost) and the fetch-site gates on the coordinator-direct methods and the five org
sub-collectors (should_run gate, mark_ran on success, ttl_seconds threading).
"""

from __future__ import annotations

from typing import Any

from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.scheduler import (
    EndpointGroupName,
    OrgShape,
    pages,
)
from tests.helpers.base import BaseCollectorTest

# --- expected declarations (mirror of the #617 §2 org rows) ------------------

_EXPECTED = {
    EndpointGroupName.ORG_AVAILABILITIES: (1, 120.0),
    EndpointGroupName.ORG_AVAILABILITY_HISTORY: (2, 300.0),
    EndpointGroupName.ORG_API_USAGE: (3, 300.0),
    EndpointGroupName.ORG_CLIENT_OVERVIEW: (3, 300.0),
    EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW: (4, 900.0),
    EndpointGroupName.ORG_PACKET_CAPTURES: (4, 900.0),
    EndpointGroupName.ORG_APP_USAGE: (4, 900.0),
    EndpointGroupName.ORG_FIRMWARE: (4, 900.0),
    EndpointGroupName.ORG_LICENSES: (4, 1800.0),
    # Phase 4 (#618) additions: #297/#298/#299/#300/#611.
    EndpointGroupName.ORG_CONFIG_TEMPLATES: (4, 900.0),
    EndpointGroupName.ORG_ADAPTIVE_POLICY: (4, 900.0),
    EndpointGroupName.ORG_TOP_USAGE: (4, 900.0),
    EndpointGroupName.ORG_WEBHOOK_LOGS: (4, 300.0),
    EndpointGroupName.ORG_FIRMWARE_COMPLIANCE: (4, 900.0),
}


def _shape(device_count: int = 1200) -> OrgShape:
    """Build a representative OrgShape for cost_fn assertions."""
    return OrgShape(
        org_id="org-1",
        network_count=50,
        wireless_network_count=40,
        switch_network_count=30,
        appliance_network_count=20,
        sensor_network_count=10,
        camera_network_count=5,
        cellular_network_count=2,
        device_count=device_count,
        ap_count=200,
        switch_count=150,
        appliance_count=25,
        physical_mx_count=20,
        camera_count=30,
        sensor_count=40,
        cellular_count=2,
    )


class _FakeScheduler:
    """Minimal scheduler double: controls gate decisions, records mark_ran."""

    def __init__(self, run_map: dict[EndpointGroupName, bool] | None = None) -> None:
        """Store the per-group run decisions (default True when unlisted)."""
        self.run_map = run_map or {}
        self.marked: list[EndpointGroupName] = []
        self.interval = 300.0
        self.ttl = 654.0

    def should_run(self, group: EndpointGroupName, now: float | None = None) -> bool:
        """Return the configured run decision for a group."""
        return self.run_map.get(group, True)

    def mark_ran(self, group: EndpointGroupName, now: float | None = None) -> None:
        """Record that a group's fetch was marked successful."""
        self.marked.append(group)

    def interval_for(self, group: EndpointGroupName) -> float:
        """Return a fixed interval for any group."""
        return self.interval

    def ttl_seconds_for(self, group: EndpointGroupName) -> float:
        """Return a fixed TTL for any group."""
        return self.ttl

    def register_groups(self, groups: Any) -> None:  # pragma: no cover - unused
        """No-op registration hook."""

    def resolve(self, shape: Any) -> None:  # pragma: no cover - unused
        """No-op resolve hook."""


class TestOrgEndpointGroupDeclarations:
    """Validate the fourteen declared org endpoint groups."""

    def test_all_fourteen_groups_declared(self) -> None:
        """All fourteen org rows are declared, no more, no less."""
        groups = {g.name: g for g in OrganizationCollector.endpoint_groups}
        assert set(groups) == set(_EXPECTED)

    def test_priority_floor_and_gating(self) -> None:
        """Each group carries the expected priority, floor, gated flag."""
        groups = {g.name: g for g in OrganizationCollector.endpoint_groups}
        for name, (priority, floor) in _EXPECTED.items():
            assert groups[name].priority == priority, name
            assert groups[name].floor_seconds == floor, name
            assert groups[name].gated is True, name
            assert groups[name].setting_pin is None, name

    def test_cost_functions(self) -> None:
        """cost_fn returns the #617 §2 estimated calls-per-execution."""
        groups = {g.name: g for g in OrganizationCollector.endpoint_groups}
        shape = _shape(device_count=1200)
        assert groups[EndpointGroupName.ORG_AVAILABILITIES].cost_fn(shape) == pages(1200, 500)
        assert groups[EndpointGroupName.ORG_AVAILABILITY_HISTORY].cost_fn(shape) == 1
        assert groups[EndpointGroupName.ORG_API_USAGE].cost_fn(shape) == 2
        assert groups[EndpointGroupName.ORG_CLIENT_OVERVIEW].cost_fn(shape) == 1
        assert groups[EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW].cost_fn(shape) == 1
        assert groups[EndpointGroupName.ORG_PACKET_CAPTURES].cost_fn(shape) == 1
        assert groups[EndpointGroupName.ORG_APP_USAGE].cost_fn(shape) == 1
        assert groups[EndpointGroupName.ORG_FIRMWARE].cost_fn(shape) == 1
        assert groups[EndpointGroupName.ORG_LICENSES].cost_fn(shape) == 2


class TestOrgCoordinatorGates(BaseCollectorTest):
    """Gate behaviour for coordinator-direct org fetch sites."""

    collector_class = OrganizationCollector

    def _collector(self, mock_api, settings, isolated_registry, inventory, scheduler):
        """Construct an OrganizationCollector wired to a fake scheduler."""
        return OrganizationCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=scheduler,  # type: ignore[arg-type]
        )

    def test_get_endpoint_groups_returns_declarations(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """The instance hook returns the class-level declarations."""
        collector = OrganizationCollector(
            api=mock_api, settings=settings, registry=isolated_registry, inventory=inventory
        )
        assert {g.name for g in collector.get_endpoint_groups()} == set(_EXPECTED)

    async def test_device_model_overview_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due device-model-overview group skips its API call."""
        sched = _FakeScheduler({EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        await collector._collect_device_counts_by_model("org-1", "Org")
        collector.api.organizations.getOrganizationDevicesOverviewByModel.assert_not_called()
        assert EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW not in sched.marked

    async def test_device_model_overview_runs_and_marks(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due device-model-overview group fetches and marks ran."""
        sched = _FakeScheduler({EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW: True})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        collector.api.organizations.getOrganizationDevicesOverviewByModel.return_value = {
            "counts": [{"model": "MR36", "total": 4}]
        }
        await collector._collect_device_counts_by_model("org-1", "Org")
        collector.api.organizations.getOrganizationDevicesOverviewByModel.assert_called()
        assert EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW in sched.marked

    async def test_packet_captures_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due packet-captures group skips its API call."""
        sched = _FakeScheduler({EndpointGroupName.ORG_PACKET_CAPTURES: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        await collector._collect_packet_capture_metrics("org-1", "Org")
        collector.api.organizations.getOrganizationDevicesPacketCaptureCaptures.assert_not_called()
        assert EndpointGroupName.ORG_PACKET_CAPTURES not in sched.marked

    async def test_application_usage_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due application-usage group skips its API call."""
        sched = _FakeScheduler({EndpointGroupName.ORG_APP_USAGE: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        await collector._collect_application_usage_metrics("org-1", "Org")
        collector.api.organizations.getOrganizationSummaryTopApplicationsCategoriesByUsage.assert_not_called()
        assert EndpointGroupName.ORG_APP_USAGE not in sched.marked

    async def test_device_availability_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due availabilities group skips the inventory read."""
        sched = _FakeScheduler({EndpointGroupName.ORG_AVAILABILITIES: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)

        called = False

        async def _avail(_org_id: str):
            nonlocal called
            called = True
            return []

        collector.inventory.get_device_availabilities = _avail  # type: ignore[method-assign]
        await collector._collect_device_availability_metrics("org-1", "Org")
        assert called is False
        assert EndpointGroupName.ORG_AVAILABILITIES not in sched.marked


class TestOrgSubCollectorGates(BaseCollectorTest):
    """Gate behaviour for the five org sub-collectors via the coordinator."""

    collector_class = OrganizationCollector

    def _collector(self, mock_api, settings, isolated_registry, inventory, scheduler):
        """Construct an OrganizationCollector wired to a fake scheduler."""
        return OrganizationCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            scheduler=scheduler,  # type: ignore[arg-type]
        )

    async def test_api_usage_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due api-usage group skips its API call and returns success."""
        sched = _FakeScheduler({EndpointGroupName.ORG_API_USAGE: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        result = await collector.api_usage_collector.collect("org-1", "Org")
        assert result is True
        collector.api.organizations.getOrganizationApiRequestsOverview.assert_not_called()
        assert EndpointGroupName.ORG_API_USAGE not in sched.marked

    async def test_client_overview_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due client-overview group skips its API call."""
        sched = _FakeScheduler({EndpointGroupName.ORG_CLIENT_OVERVIEW: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        result = await collector.client_overview_collector.collect("org-1", "Org")
        assert result is True
        collector.api.organizations.getOrganizationClientsOverview.assert_not_called()
        assert EndpointGroupName.ORG_CLIENT_OVERVIEW not in sched.marked

    async def test_firmware_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due firmware group skips its API call."""
        sched = _FakeScheduler({EndpointGroupName.ORG_FIRMWARE: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        result = await collector.firmware_collector.collect("org-1", "Org")
        assert result is True
        collector.api.organizations.getOrganizationFirmwareUpgrades.assert_not_called()
        assert EndpointGroupName.ORG_FIRMWARE not in sched.marked

    async def test_license_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due licenses group skips license collection."""
        sched = _FakeScheduler({EndpointGroupName.ORG_LICENSES: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        result = await collector.license_collector.collect("org-1", "Org")
        assert result is True
        assert EndpointGroupName.ORG_LICENSES not in sched.marked

    async def test_availability_history_gate_skips_fetch(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A not-due availability-history group skips its API call."""
        sched = _FakeScheduler({EndpointGroupName.ORG_AVAILABILITY_HISTORY: False})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        result = await collector.device_availability_history_collector.collect("org-1", "Org")
        assert result is True
        collector.api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory.assert_not_called()
        assert EndpointGroupName.ORG_AVAILABILITY_HISTORY not in sched.marked

    async def test_firmware_runs_and_marks_when_due(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A due firmware group fetches and marks ran."""
        sched = _FakeScheduler({EndpointGroupName.ORG_FIRMWARE: True})
        collector = self._collector(mock_api, settings, isolated_registry, inventory, sched)
        collector.api.organizations.getOrganizationFirmwareUpgrades.return_value = []
        result = await collector.firmware_collector.collect("org-1", "Org")
        assert result is True
        assert EndpointGroupName.ORG_FIRMWARE in sched.marked
