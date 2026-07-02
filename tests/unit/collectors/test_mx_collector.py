"""Tests for MX (Security Appliance) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx import MXCollector

if TYPE_CHECKING:
    pass


class TestMXCollector:
    """Test MX collector functionality."""

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
        return parent

    @pytest.fixture
    def mx_collector(
        self,
        mock_parent: MagicMock,
    ) -> MXCollector:
        """Create MX collector instance."""
        return MXCollector(mock_parent)

    async def test_collect_does_not_set_common_metrics(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test that MX collector does not redundantly set common metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before collect() is called.
        """
        device = {
            "serial": "Q123",
            "name": "Test MX",
            "model": "MX100",
            "network_id": "net1",
            "organization_id": "123",
        }

        await mx_collector.collect(device)
        mx_collector.parent._device_up.labels.assert_not_called()

    def test_mx_collector_initialization(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MX collector initialization."""
        assert mx_collector.parent == mock_parent
        assert mx_collector.api == mock_parent.api
        assert mx_collector.settings == mock_parent.settings

    def test_mx_uplink_info_metric_created(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that the MX uplink info gauge metric is created on init.

        MXCollector now delegates gauge creation to DeviceCollector for its own
        metrics and also instantiates sub-collectors (VPN, Firewall) that each
        create their own gauges via the same delegation path, so _create_gauge
        is called multiple times on initialisation.
        """
        # At least the uplink info gauge must be created
        mock_parent._create_gauge.assert_called()
        assert mx_collector._mx_uplink_info is not None

    async def test_collect_uplink_statuses_basic(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test basic uplink status collection with a single appliance."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-1234-5678",
                    "networkId": "N_111",
                    "model": "MX68",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                        {"interface": "wan2", "status": "not connected"},
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2AB-1234-5678": {
                "name": "Office MX",
                "model": "MX68",
                "network_id": "N_111",
                "network_name": "Office Network",
                "device_type": "MX",
            }
        }

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 2

        # Verify the first call (wan1 active)
        _, labels_0, value_0 = mock_parent._set_metric.call_args_list[0][0]
        assert labels_0["serial"] == "Q2AB-1234-5678"
        assert labels_0["name"] == "Office MX"
        assert labels_0["interface"] == "wan1"
        assert labels_0["status"] == "active"
        assert labels_0["network_name"] == "Office Network"
        assert value_0 == 1

        # Verify the second call (wan2 not connected)
        _, labels_1, value_1 = mock_parent._set_metric.call_args_list[1][0]
        assert labels_1["interface"] == "wan2"
        assert labels_1["status"] == "not connected"
        assert value_1 == 1

    async def test_collect_uplink_statuses_empty_response(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(return_value=[])

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_unknown_serial(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection when serial is not in the device lookup."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-UNKNOWN",
                    "networkId": "N_999",
                    "model": "MX100",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                    ],
                }
            ]
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 1
        _, labels, _ = mock_parent._set_metric.call_args_list[0][0]
        # Falls back to serial as name when not in device_lookup
        assert labels["name"] == "Q2XX-UNKNOWN"
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert labels["model"] == "MX100"

    async def test_collect_uplink_statuses_multiple_appliances(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection across multiple MX appliances."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "networkId": "N_1",
                    "model": "MX68",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                    ],
                },
                {
                    "serial": "Q2AB-0002",
                    "networkId": "N_2",
                    "model": "MX250",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                        {"interface": "wan2", "status": "ready"},
                        {"interface": "cellular", "status": "not connected"},
                    ],
                },
            ]
        )

        device_lookup = {
            "Q2AB-0001": {
                "name": "Branch MX",
                "model": "MX68",
                "network_id": "N_1",
                "network_name": "Branch",
                "device_type": "MX",
            },
            "Q2AB-0002": {
                "name": "HQ MX",
                "model": "MX250",
                "network_id": "N_2",
                "network_name": "HQ",
                "device_type": "MX",
            },
        }

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        # 1 uplink from first appliance + 3 from second = 4 total
        assert mock_parent._set_metric.call_count == 4

    async def test_collect_uplink_statuses_no_uplinks(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test appliance with no uplinks in response."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-0001",
                    "networkId": "N_1",
                    "model": "MX68",
                    "uplinks": [],
                }
            ]
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_device_type_from_model(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that device_type is derived from model via create_device_labels."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-Z3",
                    "networkId": "N_1",
                    "model": "Z3",
                    "uplinks": [
                        {"interface": "wan1", "status": "active"},
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2AB-Z3": {
                "name": "Teleworker Gateway",
                "model": "Z3",
                "network_id": "N_1",
                "network_name": "Remote",
                "device_type": "Z3",
            },
        }

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        _, labels, _ = mock_parent._set_metric.call_args_list[0][0]
        # create_device_labels derives device_type from model[:2]
        assert labels["device_type"] == "Z3"

    async def test_collect_uplink_statuses_does_not_wipe_other_orgs(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """collect_uplink_statuses must NOT clear the whole gauge.

        The gauge instance is shared across concurrently-collected orgs, so a
        global _metrics.clear() would wipe every other org's series mid-cycle
        (the F-001 multi-org wipe bug). Stale status-label churn is delegated to
        the metric expiration manager instead. Seed a series for a *different* org
        and confirm org1's collection leaves it intact.
        """
        gauge = mx_collector._mx_uplink_info

        # Series belonging to another org (would be wiped by a global clear()).
        gauge.labels(
            org_id="org2",
            org_name="Other Org",
            network_id="N_222",
            network_name="Other Network",
            serial="Q2ZZ-OTHER",
            name="Other MX",
            model="MX68",
            device_type="MX",
            interface="wan1",
            status="active",
        ).set(1)

        assert len(gauge._metrics) == 1

        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-1234-5678",
                    "networkId": "N_111",
                    "model": "MX68",
                    "uplinks": [
                        {"interface": "wan1", "status": "failed"},
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2AB-1234-5678": {
                "name": "Office MX",
                "model": "MX68",
                "network_id": "N_111",
                "network_name": "Office Network",
                "device_type": "MX",
            }
        }

        await mx_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        # org2's series must survive — org1's collection must not wipe the shared gauge.
        assert len(gauge._metrics) == 1

    async def test_collect_uplink_statuses_api_error(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    def test_mx_performance_score_metric_created(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that the MX performance score gauge metric is created on init."""
        assert mx_collector._mx_performance_score is not None

    async def test_collect_performance_score_basic(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that a device's performance score is emitted."""
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 87})

        device = {
            "serial": "Q2AB-1234-5678",
            "name": "Office MX",
            "model": "MX68",
            "networkId": "N_111",
            "networkName": "Office Network",
            "orgId": "org1",
            "orgName": "Test Org",
        }

        await mx_collector.collect(device)

        assert mock_parent._set_metric.call_count == 1
        gauge, labels, value, metric_name = mock_parent._set_metric.call_args_list[0][0]
        assert gauge is mx_collector._mx_performance_score
        assert labels["serial"] == "Q2AB-1234-5678"
        assert labels["org_id"] == "org1"
        assert labels["org_name"] == "Test Org"
        assert labels["network_id"] == "N_111"
        assert value == 87.0
        assert metric_name == "meraki_mx_performance_score"

    async def test_collect_performance_score_missing_perf_score_skips_emission(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that a missing perfScore field results in no metric emission."""
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={})

        device = {
            "serial": "Q2AB-1234-5678",
            "name": "Office MX",
            "model": "MX68",
            "networkId": "N_111",
            "networkName": "Office Network",
            "orgId": "org1",
            "orgName": "Test Org",
        }

        await mx_collector.collect(device)

        mock_parent._set_metric.assert_not_called()

    async def test_collect_performance_score_org_name_falls_back_to_org_id(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that org_name falls back to org_id when not present on the device."""
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 50})

        device = {
            "serial": "Q2AB-1234-5678",
            "name": "Office MX",
            "model": "MX68",
            "networkId": "N_111",
            "networkName": "Office Network",
            "orgId": "org1",
        }

        await mx_collector.collect(device)

        _, labels, _, _ = mock_parent._set_metric.call_args_list[0][0]
        assert labels["org_name"] == "org1"

    async def test_collect_skips_performance_score_for_z_series_teleworker_gateway(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Z-series teleworker gateways must not trigger getDeviceAppliancePerformance.

        Meraki documents the appliance performance-score endpoint as unavailable
        on Z-series teleworker gateways (and vMX); calling it anyway wastes API
        budget and logs an error every cycle (F-066).
        """
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 87})

        device = {
            "serial": "Q2ZZ-0001",
            "name": "Home Teleworker Gateway",
            "model": "Z3",
            "networkId": "N_111",
            "networkName": "Remote",
            "orgId": "org1",
            "orgName": "Test Org",
        }

        await mx_collector.collect(device)

        mock_api.appliance.getDeviceAppliancePerformance.assert_not_called()
        mock_parent._set_metric.assert_not_called()

    async def test_collect_skips_performance_score_for_vmx(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Virtual MX (vMX) devices must not trigger getDeviceAppliancePerformance."""
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 87})

        device = {
            "serial": "Q2VV-0001",
            "name": "Cloud vMX",
            "model": "vMX100",
            "networkId": "N_111",
            "networkName": "Cloud",
            "orgId": "org1",
            "orgName": "Test Org",
        }

        await mx_collector.collect(device)

        mock_api.appliance.getDeviceAppliancePerformance.assert_not_called()
        mock_parent._set_metric.assert_not_called()

    async def test_collect_performance_score_api_error_handled_gracefully(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # model must indicate physical MX hardware so the perf call is actually
        # attempted (and thus actually exercises the error-handling decorator).
        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await mx_collector.collect(device)

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_respects_network_filter(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit uplink metrics."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "networkId": "N_INCLUDED",
                    "model": "MX68",
                    "uplinks": [{"interface": "wan1", "status": "active"}],
                },
                {
                    "serial": "Q-OUT",
                    "networkId": "N_EXCLUDED",
                    "model": "MX68",
                    "uplinks": [{"interface": "wan1", "status": "active"}],
                },
            ]
        )
        # Wire an inventory that allows only N_INCLUDED.
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        # Only the included network's uplink should produce a metric.
        assert mock_parent._set_metric.call_count == 1
        _, labels, _ = mock_parent._set_metric.call_args_list[0][0]
        assert labels["network_id"] == "N_INCLUDED"
        assert labels["serial"] == "Q-IN"
