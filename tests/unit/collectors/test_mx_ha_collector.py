"""Tests for MX high-availability (warm spare) redundancy collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx_ha import MXHACollector

if TYPE_CHECKING:
    pass


class TestMXHACollector:
    """Test MX HA redundancy collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.appliance = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collectors emit all rows.
        parent.inventory = None

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def collector(
        self,
        mock_parent: MagicMock,
    ) -> MXHACollector:
        """Create MX HA collector instance."""
        return MXHACollector(mock_parent)

    def test_initialization(
        self,
        collector: MXHACollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test collector initialization sets up parent/api/settings and gauges."""
        assert collector.parent == mock_parent
        assert collector.api == mock_parent.api
        assert collector.settings == mock_parent.settings

    def test_gauges_created(
        self,
        collector: MXHACollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that all three HA gauges are created on init."""
        assert mock_parent._create_gauge.call_count == 3
        assert collector._mx_ha_enabled is not None
        assert collector._mx_ha_mode is not None
        assert collector._mx_ha_role is not None

    async def test_active_active_pair_basic_emission(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test enabled/mode/role emission for a two-designation warm-spare pair."""
        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_111",
                    "name": "Office Network",
                    "enabled": True,
                    "mode": "active-active",
                    "designations": [
                        {"serial": "Q2AB-0001", "priority": 1},
                        {"serial": "Q2AB-0002", "priority": 2},
                    ],
                }
            ]
        )

        await collector.collect_redundancy("org1", "Test Org", {})

        # 1 enabled + 1 mode + 2 role = 4 emissions
        assert mock_parent._set_metric.call_count == 4

        gauge_0, labels_0, value_0, name_0 = mock_parent._set_metric.call_args_list[0][0]
        assert gauge_0 is collector._mx_ha_enabled
        assert labels_0["network_id"] == "N_111"
        assert labels_0["network_name"] == "Office Network"
        assert value_0 == 1.0
        assert name_0 == "meraki_mx_ha_enabled"

        gauge_1, labels_1, value_1, name_1 = mock_parent._set_metric.call_args_list[1][0]
        assert gauge_1 is collector._mx_ha_mode
        assert labels_1["mode"] == "active-active"
        assert value_1 == 1
        assert name_1 == "meraki_mx_ha_mode"

        gauge_2, labels_2, value_2, name_2 = mock_parent._set_metric.call_args_list[2][0]
        assert gauge_2 is collector._mx_ha_role
        assert labels_2["serial"] == "Q2AB-0001"
        assert value_2 == 1.0
        assert name_2 == "meraki_mx_ha_role"

        gauge_3, labels_3, value_3, _ = mock_parent._set_metric.call_args_list[3][0]
        assert labels_3["serial"] == "Q2AB-0002"
        assert value_3 == 2.0

    async def test_disabled_mode_row(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test a network with HA disabled still emits enabled=0 and mode=disabled."""
        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_222",
                    "name": "Branch Network",
                    "enabled": False,
                    "mode": "disabled",
                    "designations": [],
                }
            ]
        )

        await collector.collect_redundancy("org1", "Test Org", {})

        # 1 enabled + 1 mode + 0 role = 2 emissions
        assert mock_parent._set_metric.call_count == 2

        gauge_0, labels_0, value_0, _ = mock_parent._set_metric.call_args_list[0][0]
        assert gauge_0 is collector._mx_ha_enabled
        assert value_0 == 0.0

        gauge_1, labels_1, value_1, _ = mock_parent._set_metric.call_args_list[1][0]
        assert gauge_1 is collector._mx_ha_mode
        assert labels_1["mode"] == "disabled"
        assert value_1 == 1

    async def test_clears_stale_mode_and_role_labels(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that stale mode/role label series are cleared on each collection.

        mode and serial are labels that can churn (mode transitions, warm
        spare re-designation) so the old label series must not persist.
        """
        mode_gauge = collector._mx_ha_mode
        role_gauge = collector._mx_ha_role

        mode_gauge.labels(
            org_id="org1",
            org_name="Test Org",
            network_id="N_111",
            network_name="Office Network",
            mode="active-passive",
        ).set(1)
        role_gauge.labels(
            org_id="org1",
            org_name="Test Org",
            network_id="N_111",
            network_name="Office Network",
            serial="Q2AB-STALE",
        ).set(1)

        assert len(mode_gauge._metrics) == 1
        assert len(role_gauge._metrics) == 1

        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_111",
                    "name": "Office Network",
                    "enabled": True,
                    "mode": "active-active",
                    "designations": [{"serial": "Q2AB-0001", "priority": 1}],
                }
            ]
        )

        await collector.collect_redundancy("org1", "Test Org", {})

        # parent._set_metric is mocked so no new entries land in the real
        # Gauge, but the pre-collection clear must have removed the stale ones.
        assert len(mode_gauge._metrics) == 0
        assert len(role_gauge._metrics) == 0

    async def test_designation_missing_priority_skipped(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test a designation with no priority does not emit a role metric."""
        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_111",
                    "name": "Office Network",
                    "enabled": True,
                    "mode": "active-active",
                    "designations": [{"serial": "Q2AB-0001", "priority": None}],
                }
            ]
        )

        await collector.collect_redundancy("org1", "Test Org", {})

        # 1 enabled + 1 mode + 0 role (priority missing) = 2 emissions
        assert mock_parent._set_metric.call_count == 2

    async def test_empty_response(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            return_value=[]
        )

        await collector.collect_redundancy("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_network_filter_exclusion(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Networks excluded by the filter must not emit HA metrics."""
        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "name": "Included",
                    "enabled": True,
                    "mode": "active-active",
                    "designations": [{"serial": "Q-IN", "priority": 1}],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "name": "Excluded",
                    "enabled": True,
                    "mode": "active-active",
                    "designations": [{"serial": "Q-OUT", "priority": 1}],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await collector.collect_redundancy("org1", "Test Org", {})

        # Only the included network's rows emit: enabled + mode + role = 3
        assert mock_parent._set_metric.call_count == 3
        for call in mock_parent._set_metric.call_args_list:
            assert call[0][1]["network_id"] == "N_INCLUDED"

    async def test_api_error_handled_gracefully(
        self,
        collector: MXHACollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.appliance.getOrganizationApplianceDevicesRedundancyByNetwork = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await collector.collect_redundancy("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()
