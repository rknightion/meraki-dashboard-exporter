"""Tests for MS switch stack collector."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Gauge

from meraki_dashboard_exporter.collectors.devices.ms_stack import MSStackCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MSMetricName


def _get_samples(registry: CollectorRegistry, metric_name: str) -> list[Any]:
    """Return all samples for a named metric from the registry."""
    for metric_family in registry.collect():
        if metric_family.name == metric_name:
            return list(metric_family.samples)
    return []


class TestMSStackCollector:
    """Test MSStackCollector functionality."""

    @pytest.fixture
    def registry(self) -> CollectorRegistry:
        """Isolated Prometheus registry for each test."""
        return CollectorRegistry()

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock Meraki API client."""
        api = MagicMock()
        api.switch = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock, registry: CollectorRegistry) -> MagicMock:
        """Create a mock parent collector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.settings.api.concurrency_limit = 5
        # Ensure rate_limiter is None so @log_api_call does not try to await it
        parent.rate_limiter = None

        def create_gauge(name: MSMetricName, description: str, labelnames: list[Any]) -> Gauge:
            return Gauge(name.value, description, labelnames, registry=registry)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    @pytest.fixture
    def stack_collector(self, mock_parent: MagicMock) -> MSStackCollector:
        """Create MSStackCollector instance."""
        return MSStackCollector(mock_parent)

    # -----------------------------------------------------------------------
    # collect_for_network
    # -----------------------------------------------------------------------

    async def test_collect_for_network_sets_member_count(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """Stack member total is set correctly for a two-member stack."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(
            return_value=[
                {
                    "id": "stack-1",
                    "serials": ["QAAA-0001-0001", "QAAA-0001-0002"],
                }
            ]
        )

        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        samples = _get_samples(registry, MSMetricName.MS_STACK_MEMBERS_TOTAL)
        assert len(samples) == 1
        assert samples[0].labels["stack_id"] == "stack-1"
        assert samples[0].value == 2.0

    async def test_collect_for_network_sets_member_status(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """Each stack member gets a status metric of 1."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(
            return_value=[
                {
                    "id": "stack-1",
                    "serials": ["QAAA-0001-0001", "QAAA-0001-0002"],
                }
            ]
        )

        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        samples = _get_samples(registry, MSMetricName.MS_STACK_MEMBER_STATUS)
        assert len(samples) == 2
        for sample in samples:
            assert sample.value == 1.0

    async def test_collect_for_network_first_member_is_primary(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """First serial in list gets role=primary, others get role=member."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(
            return_value=[
                {
                    "id": "stack-1",
                    "serials": ["QAAA-PRIMARY", "QAAA-MEMBER1", "QAAA-MEMBER2"],
                }
            ]
        )

        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        role_by_serial: dict[str, str] = {
            s.labels["serial"]: s.labels["role"]
            for s in _get_samples(registry, MSMetricName.MS_STACK_MEMBER_STATUS)
        }
        assert role_by_serial["QAAA-PRIMARY"] == "primary"
        assert role_by_serial["QAAA-MEMBER1"] == "member"
        assert role_by_serial["QAAA-MEMBER2"] == "member"

    async def test_collect_for_network_empty_stacks(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """No metrics are set when there are no stacks in the network."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(return_value=[])

        # Should not raise
        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        assert _get_samples(registry, MSMetricName.MS_STACK_MEMBERS_TOTAL) == []

    async def test_collect_for_network_single_member_stack(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """Single-member stack gets count=1 and role=primary."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(
            return_value=[{"id": "stack-solo", "serials": ["QAAA-ONLY"]}]
        )

        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        total_samples = _get_samples(registry, MSMetricName.MS_STACK_MEMBERS_TOTAL)
        assert len(total_samples) == 1
        assert total_samples[0].value == 1.0

        status_samples = _get_samples(registry, MSMetricName.MS_STACK_MEMBER_STATUS)
        assert len(status_samples) == 1
        assert status_samples[0].labels["role"] == "primary"
        assert status_samples[0].labels["serial"] == "QAAA-ONLY"

    async def test_collect_for_network_api_error_continues(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
    ) -> None:
        """API errors are handled gracefully; no exception propagates."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(side_effect=Exception("API Error"))

        # Should not raise due to @with_error_handling(continue_on_error=True)
        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

    async def test_collect_for_network_skips_stack_with_missing_id(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """Stacks without an 'id' field are skipped without error."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(
            return_value=[
                {"serials": ["QAAA-0001-0001"]},  # no "id"
                {"id": "stack-valid", "serials": ["QAAA-0002-0001"]},
            ]
        )

        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        total_samples = _get_samples(registry, MSMetricName.MS_STACK_MEMBERS_TOTAL)
        # Only the valid stack should produce a metric
        assert len(total_samples) == 1
        assert total_samples[0].labels["stack_id"] == "stack-valid"

    async def test_collect_for_network_unexpected_response_type(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """Non-list API response is handled without error."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(return_value=None)

        # Should not raise
        await stack_collector.collect_for_network(
            org_id="org1",
            org_name="Org One",
            network_id="net1",
            network_name="Net One",
        )

        assert _get_samples(registry, MSMetricName.MS_STACK_MEMBERS_TOTAL) == []

    # -----------------------------------------------------------------------
    # collect_for_org
    # -----------------------------------------------------------------------

    async def test_collect_for_org_filters_to_switch_networks(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
    ) -> None:
        """Only networks with 'switch' in productTypes are queried."""
        mock_api.switch.getNetworkSwitchStacks = MagicMock(return_value=[])

        networks = [
            {"id": "net-switch", "name": "Switch Net", "productTypes": ["switch"]},
            {"id": "net-wireless", "name": "Wireless Net", "productTypes": ["wireless"]},
            {"id": "net-mixed", "name": "Mixed Net", "productTypes": ["switch", "wireless"]},
        ]

        await stack_collector.collect_for_org("org1", "Org One", networks)

        call_args = [call.args[0] for call in mock_api.switch.getNetworkSwitchStacks.call_args_list]
        assert "net-switch" in call_args
        assert "net-mixed" in call_args
        assert "net-wireless" not in call_args

    async def test_collect_for_org_empty_network_list(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
    ) -> None:
        """No API calls are made when the network list is empty."""
        await stack_collector.collect_for_org("org1", "Org One", [])

        mock_api.switch.getNetworkSwitchStacks.assert_not_called()

    async def test_collect_for_org_multiple_stacks_across_networks(
        self,
        stack_collector: MSStackCollector,
        mock_api: MagicMock,
        registry: CollectorRegistry,
    ) -> None:
        """Stacks from multiple networks all produce metrics."""

        def stacks_for_network(network_id: str) -> list[dict[str, Any]]:
            if network_id == "net-a":
                return [{"id": "stack-a", "serials": ["QAAA-A001", "QAAA-A002"]}]
            if network_id == "net-b":
                return [{"id": "stack-b", "serials": ["QAAB-B001"]}]
            return []

        mock_api.switch.getNetworkSwitchStacks = MagicMock(side_effect=stacks_for_network)

        networks = [
            {"id": "net-a", "name": "Net A", "productTypes": ["switch"]},
            {"id": "net-b", "name": "Net B", "productTypes": ["switch"]},
        ]

        await stack_collector.collect_for_org("org1", "Org One", networks)

        stack_ids = {
            s.labels["stack_id"]
            for s in _get_samples(registry, MSMetricName.MS_STACK_MEMBERS_TOTAL)
        }
        assert stack_ids == {"stack-a", "stack-b"}
