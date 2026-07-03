"""Gate-semantics tests for #629 (mark ran only on >=1 successful sub-fetch).

Mark a scheduler group "ran" only when at least one sub-fetch of a multi-fetch
fan-out actually succeeded.

Covers two fan-out sites that previously marked their group ran unconditionally
even when every ``@with_error_handling(continue_on_error=True)`` sub-fetch was
swallowed to ``None``:

- ``MVCollector.collect`` — the ``mv_analytics`` three-call fan-out (and the
  single-call ``mv_sense_config`` site).
- ``ClientsCollector._collect_impl`` — the per-network ``getNetworkClients``
  fan-out for the ``clients_list`` group.

Contract: partial success still marks (>=1 successful sub-fetch); a successful
empty response still marks; total failure (every sub-fetch failed) must NOT mark
so the gate stays open and the next cycle retries.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.clients import ClientsCollector
from meraki_dashboard_exporter.collectors.devices.mv import MVCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import (
    ClientFactory,
    NetworkFactory,
    OrganizationFactory,
)

# ======================================================================
# MV: mv_analytics + mv_sense_config fan-out mark semantics
# ======================================================================


class TestMVGateSemantics:
    """MVCollector marks its groups ran only on >=1 successful sub-fetch."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock Meraki API client with a camera controller."""
        api = MagicMock()
        api.camera = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Mock parent DeviceCollector with scheduler-gate helpers stubbed."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None
        parent._group_interval = MagicMock(return_value=900.0)
        parent._group_ttl_seconds = MagicMock(return_value=1800.0)
        parent._should_run_group = MagicMock(return_value=True)
        parent._mark_group_ran = MagicMock()

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def mv_collector(self, mock_parent: MagicMock) -> MVCollector:
        """MV collector under test."""
        return MVCollector(mock_parent)

    @pytest.fixture
    def device(self) -> dict[str, Any]:
        """A standard MV camera device dict."""
        return {
            "serial": "Q2CC-1234-5678",
            "name": "Lobby Camera",
            "model": "MV12",
            "networkId": "N_111",
            "networkName": "HQ Network",
            "orgId": "org1",
            "orgName": "Test Org",
        }

    @staticmethod
    def _marked_groups(mock_parent: MagicMock) -> list[EndpointGroupName]:
        return [call.args[0] for call in mock_parent._mark_group_ran.call_args_list]

    # ---- mv_analytics --------------------------------------------------

    async def test_analytics_not_marked_when_all_subfetches_fail(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict[str, Any],
    ) -> None:
        """Every analytics sub-fetch fails ⇒ mv_analytics gate stays open."""
        boom = MagicMock(side_effect=Exception("API connection failed"))
        mock_api.camera.getDeviceCameraSense = boom
        mock_api.camera.getDeviceCameraAnalyticsZones = boom
        mock_api.camera.getDeviceCameraAnalyticsRecent = boom
        mock_api.camera.getDeviceCameraQualityAndRetention = boom

        await mv_collector.collect(device)

        assert EndpointGroupName.MV_ANALYTICS not in self._marked_groups(mock_parent)

    async def test_analytics_marked_when_one_subfetch_succeeds(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict[str, Any],
    ) -> None:
        """Only zones succeeds (recent + quality fail) ⇒ mv_analytics marked."""
        mock_api.camera.getDeviceCameraSense = MagicMock(
            side_effect=Exception("sense boom")
        )
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[{"id": "0", "label": "Entrance", "type": ["person"]}]
        )
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(
            side_effect=Exception("recent boom")
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            side_effect=Exception("quality boom")
        )

        await mv_collector.collect(device)

        assert EndpointGroupName.MV_ANALYTICS in self._marked_groups(mock_parent)

    async def test_analytics_marked_on_successful_empty(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict[str, Any],
    ) -> None:
        """A successful-but-empty analytics cycle still marks the group ran."""
        mock_api.camera.getDeviceCameraSense = MagicMock(
            return_value={"senseEnabled": False, "mqttBrokerId": None}
        )
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": False,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

        await mv_collector.collect(device)

        assert EndpointGroupName.MV_ANALYTICS in self._marked_groups(mock_parent)

    # ---- mv_sense_config (single fetch) --------------------------------

    async def test_sense_not_marked_when_fetch_fails(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict[str, Any],
    ) -> None:
        """A failed sense fetch must not mark mv_sense_config ran."""
        mock_api.camera.getDeviceCameraSense = MagicMock(
            side_effect=Exception("sense boom")
        )
        # Analytics succeed so only the sense-mark decision is under test.
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={"quality": "Standard"}
        )

        await mv_collector.collect(device)

        assert EndpointGroupName.MV_SENSE_CONFIG not in self._marked_groups(mock_parent)

    async def test_sense_marked_when_fetch_succeeds(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict[str, Any],
    ) -> None:
        """A successful sense fetch marks mv_sense_config ran."""
        mock_api.camera.getDeviceCameraSense = MagicMock(
            return_value={"senseEnabled": True, "mqttBrokerId": "12345"}
        )
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={"quality": "Standard"}
        )

        await mv_collector.collect(device)

        assert EndpointGroupName.MV_SENSE_CONFIG in self._marked_groups(mock_parent)


# ======================================================================
# CLIENTS: clients_list per-network fan-out mark semantics
# ======================================================================


class TestClientsListGateSemantics(BaseCollectorTest):
    """clients_list is marked ran only when >=1 network fetch succeeds."""

    collector_class = ClientsCollector

    @staticmethod
    def _sched() -> MagicMock:
        sched = MagicMock()
        sched.should_run.return_value = True
        sched.ttl_seconds_for.return_value = 600.0
        sched.interval_for.return_value = 300.0
        return sched

    def _build(self, mock_api_builder, settings, isolated_registry, inventory, sched, *, fail):
        settings.clients.enabled = True
        org = OrganizationFactory.create(org_id="123", name="Org")
        net = NetworkFactory.create(network_id="N_123", name="Net", org_id="123")
        builder = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([net], org_id="123")
        )
        if fail:
            builder = builder.with_error("getNetworkClients", Exception("Connection error"))
        else:
            clients = [ClientFactory.create(client_id="c1", mac="aa:bb:cc:dd:ee:01")]
            builder = builder.with_custom_response("getNetworkClients", clients)
        api = builder.build()
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

    async def test_not_marked_when_all_networks_fail(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """Every network's getNetworkClients fails ⇒ clients_list not marked."""
        sched = self._sched()
        collector = self._build(
            mock_api_builder, settings, isolated_registry, inventory, sched, fail=True
        )

        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()

        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.CLIENTS_LIST not in marked

    async def test_marked_when_one_network_succeeds(
        self, mock_api_builder, settings, isolated_registry, inventory
    ) -> None:
        """A single successful network fetch marks clients_list ran."""
        sched = self._sched()
        collector = self._build(
            mock_api_builder, settings, isolated_registry, inventory, sched, fail=False
        )

        with patch.object(collector.dns_resolver, "resolve_multiple", return_value={}):
            await collector.collect()

        marked = [c.args[0] for c in sched.mark_ran.call_args_list]
        assert EndpointGroupName.CLIENTS_LIST in marked
