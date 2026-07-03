"""Wave-2 (#617) fetch-site gating tests for the MISC lane.

Covers the endpoint-group declarations and the scheduler gates added to:
- ``MTSensorCollector`` / ``devices/mt.py`` (``mt_sensor_readings``),
- ``MTSensorAlertsCollector`` / ``mt_alerts.py`` (``mt_sensor_alerts``),
- ``devices/mg.py`` (``mg_uplink_status`` gate; group declared by the DEV lane).

The gate helpers live on ``MetricCollector``; a lightweight fake scheduler
drives ``should_run``/``mark_ran``/``ttl_seconds_for`` deterministically.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mg import MGCollector
from meraki_dashboard_exporter.collectors.mt_alerts import MTSensorAlertsCollector
from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, OrgShape, pages
from tests.helpers.base import BaseCollectorTest


class _FakeScheduler:
    """Minimal scheduler double exposing only the gate surface."""

    def __init__(self, *, due: bool = True, ttl: float = 1234.0) -> None:
        """Store the fixed due-ness and TTL the double will report."""
        self._due = due
        self.ttl = ttl
        self.marked: list[EndpointGroupName] = []

    def should_run(self, group: EndpointGroupName) -> bool:
        """Return the fixed due-ness."""
        return self._due

    def mark_ran(self, group: EndpointGroupName) -> None:
        """Record a mark_ran call."""
        self.marked.append(group)

    def ttl_seconds_for(self, group: EndpointGroupName) -> float:
        """Return the fixed per-series TTL."""
        return self.ttl

    def interval_for(self, group: EndpointGroupName) -> float:
        """Return a fixed interval."""
        return 60.0


def _make_shape(**overrides: int) -> OrgShape:
    """Build an ``OrgShape`` with sensible defaults, overridable per field."""
    base: dict[str, Any] = {
        "org_id": "O1",
        "network_count": 10,
        "wireless_network_count": 4,
        "switch_network_count": 3,
        "appliance_network_count": 2,
        "sensor_network_count": 2,
        "camera_network_count": 1,
        "cellular_network_count": 1,
        "device_count": 100,
        "ap_count": 20,
        "switch_count": 15,
        "appliance_count": 5,
        "physical_mx_count": 5,
        "camera_count": 4,
        "sensor_count": 30,
        "cellular_count": 3,
    }
    base.update(overrides)
    return OrgShape(**base)


# ---------------------------------------------------------------------------
# MTSensorAlertsCollector — mt_sensor_alerts group
# ---------------------------------------------------------------------------


class TestMTSensorAlertsGating(BaseCollectorTest):
    """Gate + declaration for the ``mt_sensor_alerts`` group."""

    collector_class = MTSensorAlertsCollector

    def test_declares_mt_sensor_alerts_group(self) -> None:
        """The collector declares three groups: alerts + #302 profiles + #308 relationships.

        Phase 4 (#618) folded MT_ALERT_PROFILES (#302) and MT_RELATIONSHIPS
        (#308) into this same collector; each is a per-sensor-network fetch that
        gates independently, so all three are declared here.
        """
        groups = MTSensorAlertsCollector.endpoint_groups
        assert len(groups) == 3
        by_name = {g.name: g for g in groups}

        alerts = by_name[EndpointGroupName.MT_SENSOR_ALERTS]
        assert alerts.priority == 2
        assert alerts.floor_seconds == 300
        assert alerts.gated is True
        assert alerts.setting_pin is None
        assert alerts.cost_fn(_make_shape(sensor_network_count=7)) == 7

        profiles = by_name[EndpointGroupName.MT_ALERT_PROFILES]
        assert profiles.priority == 4
        assert profiles.floor_seconds == 900
        assert profiles.cost_fn(_make_shape(sensor_network_count=7)) == 7

        relationships = by_name[EndpointGroupName.MT_RELATIONSHIPS]
        assert relationships.priority == 4
        assert relationships.floor_seconds == 900
        assert relationships.cost_fn(_make_shape(sensor_network_count=7)) == 7

    async def test_gate_skips_fetch_when_not_due(self, collector) -> None:
        """A not-due heartbeat skips the whole per-network fan-out."""
        collector.scheduler = _FakeScheduler(due=False)
        collector.inventory.get_organizations = AsyncMock(
            return_value=[{"id": "O1", "name": "Org1"}]
        )
        collector.inventory.get_networks = AsyncMock(return_value=[])

        await collector._collect_impl()

        collector.inventory.get_organizations.assert_not_awaited()

    async def test_marks_ran_and_threads_ttl_when_due(self, collector) -> None:
        """A due heartbeat fetches, threads TTL, and marks the group ran."""
        fake = _FakeScheduler(due=True, ttl=999.0)
        collector.scheduler = fake
        collector.inventory.get_organizations = AsyncMock(
            return_value=[{"id": "O1", "name": "Org1"}]
        )
        collector.inventory.get_networks = AsyncMock(
            return_value=[{"id": "N1", "name": "Net1", "productTypes": ["sensor"]}]
        )
        collector._fetch_network_alerts_overview = AsyncMock(
            return_value={"supportedMetrics": ["temperature"], "counts": {"temperature": 2}}
        )
        # Phase 4 fold: profiles (#302) and relationships (#308) are also due when
        # the fake scheduler reports every group due, so their per-network fetches
        # run too. Stub them to valid-but-empty responses for determinism (an
        # empty profile list is the documented "0 configured" case).
        collector._fetch_network_alert_profiles = AsyncMock(return_value=[])
        collector._fetch_network_sensor_relationships = AsyncMock(return_value=[])
        collector._set_metric = MagicMock()

        await collector._collect_impl()

        # All three groups are due this heartbeat, so all three are marked ran, in
        # _collect_impl's order (alerts -> profiles -> relationships).
        assert fake.marked == [
            EndpointGroupName.MT_SENSOR_ALERTS,
            EndpointGroupName.MT_ALERT_PROFILES,
            EndpointGroupName.MT_RELATIONSHIPS,
        ]
        assert collector._set_metric.called
        _, kwargs = collector._set_metric.call_args
        assert kwargs["ttl_seconds"] == 999.0


# ---------------------------------------------------------------------------
# MTSensorCollector / MTCollector — mt_sensor_readings group
# ---------------------------------------------------------------------------


class TestMTSensorReadingsGating(BaseCollectorTest):
    """Gate + declaration for the ``mt_sensor_readings`` group."""

    collector_class = MTSensorCollector

    def test_declares_mt_sensor_readings_group(self) -> None:
        """The collector declares one group matching the §2 row."""
        groups = MTSensorCollector.endpoint_groups
        assert len(groups) == 1
        group = groups[0]
        assert group.name == EndpointGroupName.MT_SENSOR_READINGS
        assert group.priority == 2
        assert group.floor_seconds == 60
        shape = _make_shape(sensor_count=250)
        assert group.cost_fn(shape) == 2 + pages(250, 100) - 1

    async def test_sensor_readings_gate_skips_when_not_due(self, collector) -> None:
        """A not-due heartbeat skips the sensor-readings fetch entirely.

        The group gate is now evaluated once in ``collect_sensor_metrics`` and
        threaded down as ``due`` (#631) — ``_should_run_group`` mutates the
        scheduler attempt clock, so it must not be re-called at each fetch site.
        """
        mt = collector.mt_collector
        mt._fetch_sensor_readings = AsyncMock(return_value=[])
        mt._fetch_sensor_devices = AsyncMock(return_value=[])
        collector.inventory = None

        await mt._collect_org_sensors("O1", "Org1", due=False)

        mt._fetch_sensor_readings.assert_not_awaited()
        mt._fetch_sensor_devices.assert_not_awaited()

    async def test_gateway_connections_gate_skips_when_not_due(self, collector) -> None:
        """A not-due heartbeat skips the gateway-connections fetch.

        ``due`` is threaded from ``collect_sensor_metrics`` (#631) rather than
        re-evaluated here.
        """
        mt = collector.mt_collector
        mt._fetch_gateway_connections = AsyncMock(return_value=[])

        await mt._collect_org_gateway_connections("O1", "Org1", due=False)

        mt._fetch_gateway_connections.assert_not_awaited()

    async def test_sensor_readings_threads_ttl_when_due(self, collector) -> None:
        """A due heartbeat threads the group TTL into ``collect_batch``."""
        collector.scheduler = _FakeScheduler(due=True, ttl=777.0)
        collector.inventory = None
        mt = collector.mt_collector
        device = {
            "serial": "Q2MT-1",
            "model": "MT10",
            "networkId": "N1",
            "networkName": "Net1",
        }
        mt._fetch_sensor_devices = AsyncMock(return_value=[device])
        mt._fetch_sensor_readings = AsyncMock(return_value=[])
        mt.collect_batch = MagicMock()

        await mt._collect_org_sensors("O1", "Org1")

        mt._fetch_sensor_readings.assert_awaited_once()
        _, kwargs = mt.collect_batch.call_args
        assert kwargs["ttl_seconds"] == 777.0

    async def test_collect_sensor_metrics_marks_group_on_success(self, collector) -> None:
        """A due, successful cycle marks the readings group ran exactly once."""
        fake = _FakeScheduler(due=True)
        collector.scheduler = fake
        mt = collector.mt_collector
        mt._collect_org_sensors = AsyncMock()
        mt._collect_org_gateway_connections = AsyncMock()

        await mt.collect_sensor_metrics(org_id="O1", org_name="Org1")

        assert fake.marked == [EndpointGroupName.MT_SENSOR_READINGS]

    async def test_collect_sensor_metrics_gates_group_exactly_once(self, collector) -> None:
        """The readings gate is evaluated ONCE per cycle and threaded down (#631).

        Regression guard for the cold-start double-gate bug: ``should_run`` mutates
        the scheduler attempt clock, so ``collect_sensor_metrics`` must call
        ``_should_run_group`` a single time and pass the resulting ``due`` flag into
        the two fetch helpers rather than each re-evaluating the gate.
        """
        collector.scheduler = _FakeScheduler(due=True)
        mt = collector.mt_collector
        spy = MagicMock(wraps=mt.parent._should_run_group)
        mt.parent._should_run_group = spy
        sensors = AsyncMock()
        gateway = AsyncMock()
        mt._collect_org_sensors = sensors
        mt._collect_org_gateway_connections = gateway

        await mt.collect_sensor_metrics(org_id="O1", org_name="Org1")

        assert spy.call_count == 1
        # The single computed ``due`` is threaded into both fetch helpers.
        assert sensors.await_args.kwargs["due"] is True
        assert gateway.await_args.kwargs["due"] is True

    async def test_collect_sensor_metrics_does_not_mark_when_not_due(self, collector) -> None:
        """A not-due cycle never marks the group ran."""
        fake = _FakeScheduler(due=False)
        collector.scheduler = fake
        mt = collector.mt_collector
        mt._fetch_sensor_devices = AsyncMock(return_value=[])
        mt._fetch_sensor_readings = AsyncMock(return_value=[])
        mt._fetch_gateway_connections = AsyncMock(return_value=[])
        collector.inventory = None

        await mt.collect_sensor_metrics(org_id="O1", org_name="Org1")

        assert fake.marked == []


# ---------------------------------------------------------------------------
# MGCollector — mg_uplink_status gate (group declared by DEV lane)
# ---------------------------------------------------------------------------


class TestMGUplinkGating:
    """Fetch-site gate for the ``mg_uplink_status`` group in ``devices/mg.py``."""

    @pytest.fixture
    def mock_parent(self) -> MagicMock:
        """Build a mock DeviceCollector parent with a real gauge factory."""
        parent = MagicMock()
        api = MagicMock()
        api.cellularGateway = MagicMock()
        parent.api = api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None

        def create_gauge(name: Any, description: str, labelnames: list[str]) -> Gauge:
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    @pytest.fixture
    def mg_collector(self, mock_parent: MagicMock) -> MGCollector:
        """Build an MG collector bound to the mock parent."""
        return MGCollector(mock_parent)

    async def test_gate_skips_fetch_when_not_due(
        self, mg_collector: MGCollector, mock_parent: MagicMock
    ) -> None:
        """A not-due heartbeat skips the org-wide uplink fetch and mark_ran."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        spy = MagicMock()
        mock_parent.api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = spy

        await mg_collector.collect_uplink_statuses("O1", "Org1", {})

        spy.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_gate_marks_ran_and_threads_ttl_when_due(
        self, mg_collector: MGCollector, mock_parent: MagicMock
    ) -> None:
        """A due heartbeat fetches, threads TTL into every emission, and marks ran."""
        mock_parent._should_run_group = MagicMock(return_value=True)
        mock_parent._group_ttl_seconds = MagicMock(return_value=555.0)
        row = {
            "serial": "Q2XX-1",
            "networkId": "N1",
            "model": "MG21",
            "uplinks": [
                {
                    "interface": "cellular",
                    "status": "active",
                    "provider": "Verizon",
                    "signalStat": {"rsrp": "-90", "rsrq": "-10"},
                }
            ],
        }
        mock_parent.api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[row]
        )

        await mg_collector.collect_uplink_statuses("O1", "Org1", {})

        # #304 fold: collect_uplink_statuses now dispatches both the uplink-status
        # fetch (MG_UPLINK_STATUS) and the cellular-config fetch
        # (MG_CELLULAR_CONFIG), each with its own gate + mark. When both are due
        # (_should_run_group -> True), _mark_group_ran is called twice, in dispatch
        # order (uplink status first, cellular config second).
        assert mock_parent._mark_group_ran.call_args_list == [
            call(EndpointGroupName.MG_UPLINK_STATUS),
            call(EndpointGroupName.MG_CELLULAR_CONFIG),
        ]
        assert mock_parent._set_metric.called
        for emit_call in mock_parent._set_metric.call_args_list:
            assert emit_call.kwargs["ttl_seconds"] == 555.0
