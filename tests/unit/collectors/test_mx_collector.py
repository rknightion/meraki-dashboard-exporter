"""Tests for MX (Security Appliance) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx import MXCollector
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

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
        # #617 scheduler gate helpers (real numbers so the per-serial
        # mx_performance throttle's numeric comparison works). Default: gate open,
        # 900s interval, no explicit TTL override.
        parent._should_run_group = MagicMock(return_value=True)
        parent._mark_group_ran = MagicMock()
        parent._group_interval = MagicMock(return_value=900)
        parent._group_ttl_seconds = MagicMock(return_value=None)
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
        assert labels_0["interface"] == "wan1"
        assert labels_0["status"] == "active"
        assert labels_0["network_id"] == "N_111"
        assert "name" not in labels_0
        assert "network_name" not in labels_0
        assert "org_name" not in labels_0
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
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert labels["model"] == "MX100"
        assert "name" not in labels

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
            network_id="N_222",
            serial="Q2ZZ-OTHER",
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
        assert labels["network_id"] == "N_111"
        assert "org_name" not in labels
        assert "network_name" not in labels
        assert "name" not in labels
        assert value == 87.0
        assert metric_name == "meraki_mx_performance_score"

        # An explicit timespan must be passed so the score is deterministic
        # across runs rather than relying on the API's undocumented default.
        mock_api.appliance.getDeviceAppliancePerformance.assert_called_once_with(
            "Q2AB-1234-5678", timespan=1800
        )

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

    async def test_collect_performance_score_missing_org_name_still_emits(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that the metric is still emitted when orgName is absent from the device.

        Numeric series are ID-only (issue #534) so a missing display name has no
        effect on label output; this only verifies the code path that used to fall
        back org_name to org_id does not error and the metric still emits by org_id.
        """
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
        assert labels["org_id"] == "org1"
        assert "org_name" not in labels

    async def test_collect_performance_score_none_response_skips_gracefully(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A None response (#642, e.g. DevNet's MX100) must not raise DataValidationError.

        Some MX models/states have no performance score available at all and the
        SDK returns None rather than a dict -- that must be treated as "no score
        available" (no metric, no error), and the serial must still be marked
        collected so it isn't retry-hammered every cycle.
        """
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value=None)

        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=3_000.0
        ):
            # Should not raise - the None-guard must trigger before
            # validate_response_format would otherwise raise DataValidationError.
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 1
        mock_parent._set_metric.assert_not_called()

        # Immediate second cycle, well inside the 900s group interval: the
        # serial was marked collected on the None response, so the call is
        # throttled out rather than repeated every cycle.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time",
            return_value=3_000.0 + 1,
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 1

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

    # ------------------------------------------------------------------
    # #617 scheduler gates
    # ------------------------------------------------------------------

    async def test_mx_performance_gate_throttles_per_mx_call_to_900s(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The NEW mx_performance gate throttles the per-MX perf call to its 900s group.

        getDeviceAppliancePerformance is a per-physical-MX call fanned out every
        MEDIUM (300s) cycle. With the mx_performance group interval at its 900s
        floor, a given appliance must be fetched at most once per 900s: a second
        dispatch inside the window is skipped, and the call resumes once the
        interval has elapsed.
        """
        mock_parent._group_interval = MagicMock(return_value=900)
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 87})

        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=1_000.0
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 1

        # Next MEDIUM-tier dispatch, well inside the 900s group interval: skipped.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=1_000.0 + 300
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 1

        # Past the 900s interval: the per-MX perf call resumes.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=1_000.0 + 901
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 2

    async def test_mx_performance_gate_is_per_serial_no_within_cycle_blocking(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Every physical MX is collected within one cycle (gate is per-serial).

        A group-global run gate would mark after the first appliance and skip the
        rest for the whole cycle; the per-serial throttle must not do that.
        """
        mock_parent._group_interval = MagicMock(return_value=900)
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 50})

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=2_000.0
        ):
            await mx_collector.collect({"serial": "Q2AB-0001", "model": "MX68", "orgId": "org1"})
            await mx_collector.collect({"serial": "Q2AB-0002", "model": "MX250", "orgId": "org1"})

        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 2
        fetched_serials = {
            c.args[0] for c in mock_api.appliance.getDeviceAppliancePerformance.call_args_list
        }
        assert fetched_serials == {"Q2AB-0001", "Q2AB-0002"}

    async def test_mx_performance_disabled_when_interval_non_positive(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A non-positive solved interval disables the throttle (always collect)."""
        mock_parent._group_interval = MagicMock(return_value=0)
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 42})

        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=5_000.0
        ):
            await mx_collector.collect(device)
            await mx_collector.collect(device)

        assert mock_api.appliance.getDeviceAppliancePerformance.call_count == 2

    async def test_mx_performance_threads_group_ttl(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The perf-score _set_metric carries the mx_performance group's TTL."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=1800.0)
        mock_api.appliance.getDeviceAppliancePerformance = MagicMock(return_value={"perfScore": 87})

        await mx_collector.collect({"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"})

        _, kwargs = mock_parent._set_metric.call_args
        assert kwargs["ttl_seconds"] == 1800.0
        mock_parent._group_ttl_seconds.assert_called_with(EndpointGroupName.MX_PERFORMANCE)

    async def test_uplink_statuses_gate_closed_skips_fetch(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When the mx_uplink_status gate is closed, no API call or emission occurs."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(return_value=[])

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_api.appliance.getOrganizationApplianceUplinkStatuses.assert_not_called()
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_uplink_statuses_marks_group_ran_after_success(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A successful uplink-status fetch marks the mx_uplink_status group as run."""
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2AB-1234-5678",
                    "networkId": "N_111",
                    "model": "MX68",
                    "uplinks": [{"interface": "wan1", "status": "active"}],
                }
            ]
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MX_UPLINK_STATUS)
        # TTL for the emitted uplink series comes from the group.
        _, kwargs = mock_parent._set_metric.call_args
        assert "ttl_seconds" in kwargs

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

    # ------------------------------------------------------------------
    # #286: per-MX-device DHCP subnet utilization
    # ------------------------------------------------------------------

    def test_dhcp_subnet_gauges_created(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test that the DHCP subnet gauge metrics are created on init."""
        assert mx_collector._dhcp_subnet_used_ips is not None
        assert mx_collector._dhcp_subnet_free_ips is not None

    async def test_collect_dhcp_subnets_basic(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that DHCP subnet usage/free counts are emitted per subnet."""
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(
            return_value=[
                {"subnet": "10.0.0.0/24", "vlanId": 10, "usedCount": 42, "freeCount": 212},
                {"subnet": "10.0.1.0/24", "vlanId": 20, "usedCount": 5, "freeCount": 249},
            ]
        )

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

        used_calls = {
            c[0][1]["vlan"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mx_collector._dhcp_subnet_used_ips
        }
        free_calls = {
            c[0][1]["vlan"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mx_collector._dhcp_subnet_free_ips
        }
        assert used_calls == {"10": 42.0, "20": 5.0}
        assert free_calls == {"10": 212.0, "20": 249.0}

        # Labels must carry subnet/vlan plus ID-only device labels.
        used_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mx_collector._dhcp_subnet_used_ips and c[0][1]["vlan"] == "10"
        )
        _, labels, _ = used_call[0]
        assert labels["subnet"] == "10.0.0.0/24"
        assert labels["serial"] == "Q2AB-1234-5678"
        assert labels["org_id"] == "org1"
        assert labels["network_id"] == "N_111"
        assert "org_name" not in labels
        assert "network_name" not in labels

    async def test_collect_dhcp_subnets_empty_list_is_normal(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty list (no DHCP-serving VLANs) must not set any metric or raise."""
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(return_value=[])

        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        await mx_collector.collect(device)

        mock_parent._set_metric.assert_not_called()

    async def test_collect_dhcp_subnets_skips_z_series(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Z-series teleworker gateways must not trigger the DHCP subnets call."""
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(
            return_value=[{"subnet": "10.0.0.0/24", "vlanId": 1, "usedCount": 1, "freeCount": 1}]
        )

        device = {"serial": "Q2ZZ-0001", "model": "Z3", "orgId": "org1"}

        await mx_collector.collect(device)

        mock_api.appliance.getDeviceApplianceDhcpSubnets.assert_not_called()

    async def test_collect_dhcp_subnets_api_error_handled_gracefully(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API exception must not propagate."""
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(
            side_effect=Exception("API connection failed")
        )

        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        # Should not raise.
        await mx_collector.collect(device)

        mock_parent._set_metric.assert_not_called()

    async def test_dhcp_subnets_gate_throttles_per_mx_call_to_900s(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The mx_dhcp_subnets gate throttles the per-MX call to its 900s group."""
        mock_parent._group_interval = MagicMock(return_value=900)
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(
            return_value=[{"subnet": "10.0.0.0/24", "vlanId": 1, "usedCount": 1, "freeCount": 1}]
        )

        device = {"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"}

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=1_000.0
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceApplianceDhcpSubnets.call_count == 1

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=1_000.0 + 300
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceApplianceDhcpSubnets.call_count == 1

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=1_000.0 + 901
        ):
            await mx_collector.collect(device)
        assert mock_api.appliance.getDeviceApplianceDhcpSubnets.call_count == 2

    async def test_dhcp_subnets_gate_is_per_serial(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Every physical MX must get its own DHCP subnets throttle state."""
        mock_parent._group_interval = MagicMock(return_value=900)
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(return_value=[])

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.time.time", return_value=2_000.0
        ):
            await mx_collector.collect({"serial": "Q2AB-0001", "model": "MX68", "orgId": "org1"})
            await mx_collector.collect({"serial": "Q2AB-0002", "model": "MX250", "orgId": "org1"})

        assert mock_api.appliance.getDeviceApplianceDhcpSubnets.call_count == 2

    async def test_dhcp_subnets_threads_group_ttl(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The DHCP subnet _set_metric calls carry the mx_dhcp_subnets group's TTL."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=1234.0)
        mock_api.appliance.getDeviceApplianceDhcpSubnets = MagicMock(
            return_value=[{"subnet": "10.0.0.0/24", "vlanId": 1, "usedCount": 1, "freeCount": 1}]
        )

        await mx_collector.collect({"serial": "Q2AB-1234-5678", "model": "MX68", "orgId": "org1"})

        dhcp_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] in {mx_collector._dhcp_subnet_used_ips, mx_collector._dhcp_subnet_free_ips}
        ]
        assert dhcp_calls
        for call in dhcp_calls:
            assert call.kwargs["ttl_seconds"] == 1234.0

    def test_dhcp_subnet_row_validates_via_domain_model(self) -> None:
        """The DHCP subnets response is parsed via a typed Pydantic domain model."""
        from meraki_dashboard_exporter.core.domain_models import ApplianceDhcpSubnet

        parsed = ApplianceDhcpSubnet.model_validate({
            "subnet": "10.0.0.0/24",
            "vlanId": 10,
            "usedCount": 5,
            "freeCount": 250,
        })
        assert parsed.subnet == "10.0.0.0/24"
        assert parsed.vlanId == 10
        assert parsed.usedCount == 5
        assert parsed.freeCount == 250

    # ------------------------------------------------------------------
    # #330: org-wide uplink-status overview aggregate
    # ------------------------------------------------------------------

    def test_mx_uplinks_by_status_gauge_created(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test that the uplinks-by-status gauge metric is created on init."""
        assert mx_collector._mx_uplinks_by_status is not None

    async def test_collect_uplink_status_overview_emits_all_five_statuses(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """All five API status keys must be emitted every cycle, 0 when absent."""
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={
                "counts": {
                    "byStatus": {
                        "active": 12,
                        "ready": 3,
                        "failed": 1,
                        # "connecting" and "notConnected" deliberately absent.
                    }
                }
            }
        )

        await mx_collector.collect_uplink_status_overview("org1", "Test Org")

        assert mock_parent._set_metric.call_count == 5
        by_status = {c[0][1]["status"]: c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert by_status == {
            "active": 12.0,
            "ready": 3.0,
            "failed": 1.0,
            "connecting": 0.0,
            "notConnected": 0.0,
        }
        for call in mock_parent._set_metric.call_args_list:
            labels = call[0][1]
            assert labels["org_id"] == "org1"
            gauge = call[0][0]
            assert gauge is mx_collector._mx_uplinks_by_status

    async def test_collect_uplink_status_overview_gate_closed_skips_fetch(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When the mx_uplinks_overview gate is closed, no API call or emission occurs."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={"counts": {"byStatus": {}}}
        )

        await mx_collector.collect_uplink_status_overview("org1", "Test Org")

        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview.assert_not_called()
        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_status_overview_marks_group_ran_after_success(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A successful fetch marks the mx_uplinks_overview group as run."""
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={"counts": {"byStatus": {"active": 1}}}
        )

        await mx_collector.collect_uplink_status_overview("org1", "Test Org")

        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MX_UPLINKS_OVERVIEW)

    async def test_collect_uplink_status_overview_threads_group_ttl(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The overview _set_metric calls carry the mx_uplinks_overview group's TTL."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=1800.0)
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={"counts": {"byStatus": {"active": 1}}}
        )

        await mx_collector.collect_uplink_status_overview("org1", "Test Org")

        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs["ttl_seconds"] == 1800.0
        mock_parent._group_ttl_seconds.assert_called_with(EndpointGroupName.MX_UPLINKS_OVERVIEW)

    async def test_collect_uplink_status_overview_missing_counts_emits_zeros(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A response missing the counts/byStatus structure still emits five zeros."""
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={}
        )

        await mx_collector.collect_uplink_status_overview("org1", "Test Org")

        assert mock_parent._set_metric.call_count == 5
        values = {c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert values == {0.0}

    async def test_collect_uplink_status_overview_api_error_handled_gracefully(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """API errors must not propagate and must not mark the group as run."""
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await mx_collector.collect_uplink_status_overview("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_collect_uplink_statuses_also_collects_overview(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Verify the overview collection is wired via the existing pass.

        collect_uplink_statuses (the existing device.py-invoked pass) also
        triggers the overview collection, so no device.py call-site edit is
        needed to wire up #330.
        """
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(return_value=[])
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={"counts": {"byStatus": {"active": 1}}}
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview.assert_called_once_with(
            "org1"
        )
        mock_parent._mark_group_ran.assert_any_call(EndpointGroupName.MX_UPLINKS_OVERVIEW)

    async def test_collect_uplink_statuses_overview_runs_even_when_uplink_status_gate_closed(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """MX_UPLINKS_OVERVIEW has its own independent gate from MX_UPLINK_STATUS.

        If the mx_uplink_status gate is closed (e.g. a tighter 300s floor still
        mid-interval) the overview aggregate -- on its own, looser 900s floor --
        must still be collected when its own gate is open.
        """

        def should_run(group: EndpointGroupName) -> bool:
            return group != EndpointGroupName.MX_UPLINK_STATUS

        mock_parent._should_run_group = MagicMock(side_effect=should_run)
        mock_api.appliance.getOrganizationApplianceUplinkStatuses = MagicMock(return_value=[])
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview = MagicMock(
            return_value={"counts": {"byStatus": {"active": 1}}}
        )

        await mx_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_api.appliance.getOrganizationApplianceUplinkStatuses.assert_not_called()
        mock_api.appliance.getOrganizationApplianceUplinksStatusesOverview.assert_called_once()
