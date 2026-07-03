"""Gate-semantics tests for #629 on the MS/MX device lanes.

Covers three fixes:

* MS_PORT_OVERVIEW (Gap 2): the org-wide port-overview block emits via the
  standard ``parent._set_metric`` path threading the solved MS_PORT_OVERVIEW
  group TTL, so the (floor-3600s) series are expiration-tracked instead of
  lingering forever via a raw ``gauge.labels(...).set(...)`` call.
* MX_UPLINK_STATUS (Gap 3): a SUCCESSFUL fetch that returns an empty list
  (org with no MX uplinks) marks the group ran, so the gate closes and the org
  stops re-fetching every cycle. Only a real failure leaves the gate open.

Both lanes reach the scheduler through ``self.parent._*`` on the owning
``DeviceCollector``, so these tests drive a real ``DeviceCollector`` with a
controllable fake scheduler (mirrors ``test_ms_scheduler_gating``).
"""

from __future__ import annotations

from typing import Any

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.constants import MSMetricName
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


class _MSMXGateBase(BaseCollectorTest):
    """Shared helpers for MS/MX gate tests driven via a real DeviceCollector."""

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
            scheduler=scheduler,  # type: ignore[arg-type]
        )

    @staticmethod
    def _spy_set_metric(collector: DeviceCollector) -> list[tuple[str | None, float | None]]:
        """Record ``(metric_name, ttl_seconds)`` for every parent._set_metric call."""
        records: list[tuple[str | None, float | None]] = []
        original = collector._set_metric

        def spy(metric, labels, value, metric_name=None, ttl_seconds=None):  # type: ignore[no-untyped-def]
            records.append((metric_name, ttl_seconds))
            return original(metric, labels, value, metric_name, ttl_seconds=ttl_seconds)

        collector._set_metric = spy  # type: ignore[method-assign]
        return records

    @staticmethod
    def _spy_group_ttl(collector: DeviceCollector) -> list[EndpointGroupName]:
        """Record every group whose TTL was resolved via _group_ttl_seconds."""
        seen: list[EndpointGroupName] = []
        original = collector._group_ttl_seconds

        def spy(group: EndpointGroupName):  # type: ignore[no-untyped-def]
            seen.append(group)
            return original(group)

        collector._group_ttl_seconds = spy  # type: ignore[method-assign]
        return seen


_OVERVIEW_NAMES = {
    MSMetricName.MS_PORTS_ACTIVE.value,
    MSMetricName.MS_PORTS_INACTIVE.value,
    MSMetricName.MS_PORTS_BY_MEDIA.value,
    MSMetricName.MS_PORTS_BY_LINK_SPEED.value,
}


class TestMSPortOverviewTtl(_MSMXGateBase):
    """MS_PORT_OVERVIEW emits via _set_metric threading the group TTL (Gap 2)."""

    async def test_overview_emits_via_set_metric_with_group_ttl(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """Every port-overview series is emitted through _set_metric with the group TTL."""
        # MS_POWER_SUMMARY gated off so collect_power_history contributes no
        # _set_metric calls, isolating the port-overview emissions.
        sched = _FakeScheduler(
            {
                EndpointGroupName.MS_PORT_OVERVIEW: True,
                EndpointGroupName.MS_POWER_SUMMARY: False,
            },
            ttl=777.0,
        )
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        records = self._spy_set_metric(dc)
        ttl_groups = self._spy_group_ttl(dc)

        mock_api.switch.getOrganizationSwitchPortsOverview.return_value = {
            "counts": {
                "byStatus": {
                    "active": {
                        "total": 5,
                        "byMediaAndLinkSpeed": {
                            "rj45": {"total": 5, "1000": 3, "100": 2},
                        },
                    },
                    "inactive": {
                        "total": 2,
                        "byMedia": {"rj45": {"total": 2}},
                    },
                }
            }
        }

        await dc.ms_collector.collect_port_overview("org1", "Org")

        mock_api.switch.getOrganizationSwitchPortsOverview.assert_called_once()
        # The overview block resolved the solved MS_PORT_OVERVIEW group TTL.
        assert EndpointGroupName.MS_PORT_OVERVIEW in ttl_groups
        # Every overview metric was emitted via _set_metric (not raw .labels().set()).
        emitted = {name for (name, _ttl) in records if name in _OVERVIEW_NAMES}
        assert emitted == _OVERVIEW_NAMES
        # And every overview emission carried the group TTL (777.0).
        assert all(
            ttl == 777.0 for (name, ttl) in records if name in _OVERVIEW_NAMES
        )
        assert EndpointGroupName.MS_PORT_OVERVIEW in sched.marked


class TestMXUplinkStatusEmptySuccess(_MSMXGateBase):
    """MX_UPLINK_STATUS marks ran on successful-empty; not on failure (Gap 3)."""

    def _mx_collector(self, mock_api, settings, isolated_registry, inventory, sched):
        dc = self._device_collector(mock_api, settings, isolated_registry, inventory, sched)
        # The overview aggregate rides the same method; gate it off so these
        # tests exercise only the MX_UPLINK_STATUS path.
        return dc

    async def test_empty_success_marks_ran(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A successful fetch returning [] marks the group ran (gate closes)."""
        sched = _FakeScheduler(
            {
                EndpointGroupName.MX_UPLINK_STATUS: True,
                EndpointGroupName.MX_UPLINKS_OVERVIEW: False,
            }
        )
        dc = self._mx_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.appliance.getOrganizationApplianceUplinkStatuses.return_value = []

        await dc.mx_collector.collect_uplink_statuses("org1", "Org", {})

        mock_api.appliance.getOrganizationApplianceUplinkStatuses.assert_called_once()
        assert EndpointGroupName.MX_UPLINK_STATUS in sched.marked

    async def test_nonempty_success_marks_ran(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A successful fetch with data also marks the group ran (regression guard)."""
        sched = _FakeScheduler(
            {
                EndpointGroupName.MX_UPLINK_STATUS: True,
                EndpointGroupName.MX_UPLINKS_OVERVIEW: False,
            }
        )
        dc = self._mx_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.appliance.getOrganizationApplianceUplinkStatuses.return_value = [
            {
                "serial": "Q2XX-1",
                "networkId": "net1",
                "model": "MX",
                "uplinks": [{"interface": "wan1", "status": "active"}],
            }
        ]

        await dc.mx_collector.collect_uplink_statuses("org1", "Org", {})

        assert EndpointGroupName.MX_UPLINK_STATUS in sched.marked

    async def test_total_failure_does_not_mark_ran(
        self, mock_api, settings, isolated_registry, inventory
    ) -> None:
        """A real fetch failure (returns None) leaves the gate open (not marked)."""
        sched = _FakeScheduler(
            {
                EndpointGroupName.MX_UPLINK_STATUS: True,
                EndpointGroupName.MX_UPLINKS_OVERVIEW: False,
            }
        )
        dc = self._mx_collector(mock_api, settings, isolated_registry, inventory, sched)
        mock_api.appliance.getOrganizationApplianceUplinkStatuses.side_effect = Exception(
            "Connection error"
        )

        await dc.mx_collector.collect_uplink_statuses("org1", "Org", {})

        assert EndpointGroupName.MX_UPLINK_STATUS not in sched.marked
