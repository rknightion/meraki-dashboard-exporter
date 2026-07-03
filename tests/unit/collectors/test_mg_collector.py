"""Tests for MG (Cellular Gateway) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mg import (
    MGCellularBandsDevice,
    MGCellularTowersDevice,
    MGCollector,
    MGEsimInventoryRow,
    MGUplinkStatusRow,
)
from meraki_dashboard_exporter.core.domain_models import CellularGatewayUplinkStatus
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    pass


class TestMGCollector:
    """Test MG collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.cellularGateway = MagicMock()
        api.organizations = MagicMock()
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
        parent._should_run_group = MagicMock(return_value=True)
        parent._mark_group_ran = MagicMock()
        parent._group_ttl_seconds = MagicMock(return_value=None)

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    @pytest.fixture
    def mg_collector(
        self,
        mock_parent: MagicMock,
    ) -> MGCollector:
        """Create MG collector instance."""
        return MGCollector(mock_parent)

    async def test_collect_does_not_set_common_metrics(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """Test that MG collector does not redundantly set common metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before collect() is called.
        MG's per-device collect() remains a no-op — uplink metrics are
        collected org-wide via collect_uplink_statuses().
        """
        device = {
            "serial": "Q123",
            "name": "Test MG",
            "model": "MG21",
            "network_id": "net1",
            "organization_id": "123",
        }

        await mg_collector.collect(device)
        mg_collector.parent._device_up.labels.assert_not_called()

    def test_mg_collector_initialization(
        self,
        mg_collector: MGCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MG collector initialization."""
        assert mg_collector.parent == mock_parent
        assert mg_collector.api == mock_parent.api
        assert mg_collector.settings == mock_parent.settings

    def test_mg_gauges_created_on_init(
        self,
        mg_collector: MGCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that all MG gauges are created on init."""
        mock_parent._create_gauge.assert_called()
        assert mg_collector._mg_uplink_status_info is not None
        assert mg_collector._mg_uplink_signal_rsrp is not None
        assert mg_collector._mg_uplink_signal_rsrq is not None
        assert mg_collector._mg_uplink_roaming is not None

    async def test_collect_uplink_statuses_basic(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test basic uplink status collection with a single gateway."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "ip": "10.0.0.1",
                            "provider": "Verizon",
                            "connectionType": "lte",
                            "signalType": "4G",
                            "apn": "vzwinternet",
                            "signalStat": {"rsrp": "-90", "rsrq": "-10"},
                            "roaming": {"status": "home"},
                        }
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2XX-1": {
                "name": "Gateway 1",
                "model": "MG21",
                "network_id": "N_1",
                "network_name": "Main Network",
                "device_type": "MG",
            }
        }

        await mg_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        # 1 info + 1 rsrp + 1 rsrq + 1 roaming = 4 _set_metric calls
        assert mock_parent._set_metric.call_count == 4

        calls = mock_parent._set_metric.call_args_list

        info_call = calls[0]
        info_metric, info_labels, info_value, *_ = info_call[0]
        assert info_metric is mg_collector._mg_uplink_status_info
        assert info_labels["serial"] == "Q2XX-1"
        # Name-family labels are dropped from numeric series (issue #534) - the
        # device display name joins via meraki_device_status_info on serial.
        assert "name" not in info_labels
        assert "org_name" not in info_labels
        assert "network_name" not in info_labels
        assert info_labels["interface"] == "cellular"
        assert info_labels["status"] == "active"
        assert info_labels["provider"] == "Verizon"
        assert info_labels["connection_type"] == "lte"
        assert info_labels["signal_type"] == "4G"
        assert info_labels["roaming_status"] == "home"
        assert info_labels["apn"] == "vzwinternet"
        assert info_labels["ip"] == "10.0.0.1"
        assert info_value == 1

        rsrp_call = calls[1]
        rsrp_metric, rsrp_labels, rsrp_value, *_ = rsrp_call[0]
        assert rsrp_metric is mg_collector._mg_uplink_signal_rsrp
        assert rsrp_labels["interface"] == "cellular"
        assert rsrp_value == -90.0

        rsrq_call = calls[2]
        rsrq_metric, rsrq_labels, rsrq_value, *_ = rsrq_call[0]
        assert rsrq_metric is mg_collector._mg_uplink_signal_rsrq
        assert rsrq_value == -10.0

        roaming_call = calls[3]
        roaming_metric, roaming_labels, roaming_value, *_ = roaming_call[0]
        assert roaming_metric is mg_collector._mg_uplink_roaming
        assert roaming_value == 0.0  # status is "home", not "roaming"

    async def test_collect_uplink_statuses_roaming_true(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that roaming status of 'roaming' emits value 1.0."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "roaming": {"status": "roaming"},
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        roaming_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_roaming
        ]
        assert len(roaming_calls) == 1
        assert roaming_calls[0][0][2] == 1.0

    async def test_collect_uplink_statuses_no_roaming_object_skips_roaming_metric(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that no roaming object in uplink means no roaming metric is emitted."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        roaming_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_roaming
        ]
        assert len(roaming_calls) == 0

    async def test_collect_uplink_statuses_signal_string_parsing(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test rsrp/rsrq string->float parsing, including empty/non-numeric skipped."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "signalStat": {"rsrp": "", "rsrq": "not-a-number"},
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        rsrp_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_signal_rsrp
        ]
        rsrq_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_signal_rsrq
        ]
        assert len(rsrp_calls) == 0
        assert len(rsrq_calls) == 0

    async def test_collect_uplink_statuses_empty_response(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_unknown_serial(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection when serial is not in the device lookup."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_999",
                    "serial": "Q2XX-UNKNOWN",
                    "model": "MG21",
                    "uplinks": [
                        {"interface": "cellular", "status": "active"},
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_status_info
        ]
        assert len(info_calls) == 1
        _, labels, _, *_rest = info_calls[0][0]
        # Name-family labels are dropped from numeric series (issue #534).
        assert "name" not in labels
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert labels["model"] == "MG21"

    async def test_collect_uplink_statuses_respects_network_filter(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit uplink metrics."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "serial": "Q-IN",
                    "model": "MG21",
                    "uplinks": [{"interface": "cellular", "status": "active"}],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "serial": "Q-OUT",
                    "model": "MG21",
                    "uplinks": [{"interface": "cellular", "status": "active"}],
                },
            ]
        )
        # Wire an inventory that allows only N_INCLUDED.
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_status_info
        ]
        assert len(info_calls) == 1
        _, labels, _, *_rest = info_calls[0][0]
        assert labels["network_id"] == "N_INCLUDED"
        assert labels["serial"] == "Q-IN"

    async def test_collect_uplink_statuses_api_error(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_exhausted_retry_error_shape_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be handled, not raised.

        getOrganizationCellularGatewayUplinkStatuses is validated via
        validate_response_format (expected_type=list); a {"errors": [...]}
        response must raise internally and be absorbed by @with_error_handling,
        not propagate or emit a metric.
        """
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        # Should not raise - validate_response_format raises internally, and
        # @with_error_handling absorbs it.
        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_uplink_statuses_does_not_wipe_other_orgs(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """collect_uplink_statuses must NOT clear the whole gauge.

        The gauge instances are shared across concurrently-collected orgs, so a
        global _metrics.clear() would wipe every other org's series mid-cycle
        (the F-001 multi-org wipe bug). Stale status/roaming label churn is
        delegated to the metric expiration manager instead. Seed series for a
        *different* org and confirm org1's collection leaves them intact.
        """
        info_gauge = mg_collector._mg_uplink_status_info
        roaming_gauge = mg_collector._mg_uplink_roaming

        # Series belonging to another org (would be wiped by a global clear()).
        # ID-only label set (issue #534) - no org_name/network_name/name.
        info_gauge.labels(
            org_id="org2",
            network_id="N_2",
            serial="Q2ZZ-OTHER",
            model="MG21",
            device_type="MG",
            interface="cellular",
            status="active",
            provider="Verizon",
            connection_type="lte",
            signal_type="4G",
            roaming_status="home",
            apn="vzwinternet",
            ip="10.0.0.9",
        ).set(1)
        roaming_gauge.labels(
            org_id="org2",
            network_id="N_2",
            serial="Q2ZZ-OTHER",
            model="MG21",
            device_type="MG",
            interface="cellular",
        ).set(0)

        assert len(info_gauge._metrics) == 1
        assert len(roaming_gauge._metrics) == 1

        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [
                        {"interface": "cellular", "status": "failed"},
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        # org2's series must survive — org1's collection must not wipe the shared gauges.
        assert len(info_gauge._metrics) == 1
        assert len(roaming_gauge._metrics) == 1

    # ------------------------------------------------------------------
    # Pydantic domain-model validation (F-029)
    # ------------------------------------------------------------------

    async def test_collect_uplink_statuses_validates_rows_via_domain_model(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Each raw row must be validated via CellularGatewayUplinkStatus.model_validate."""
        row = {
            "networkId": "N_1",
            "serial": "Q2XX-1",
            "model": "MG21",
            "uplinks": [{"interface": "cellular", "status": "active"}],
        }
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[row]
        )

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mg.CellularGatewayUplinkStatus"
            ".model_validate",
            wraps=CellularGatewayUplinkStatus.model_validate,
        ) as spy:
            await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        spy.assert_called_once_with(row)

    async def test_collect_uplink_statuses_tolerates_missing_and_extra_fields(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Missing optional fields and unexpected extra fields must not raise.

        Mirrors the tolerance raw `.get()` chains previously had: a row missing
        `model` still falls back to the device lookup, and a row/uplink carrying
        unrecognized extra API fields (schema drift) is still processed.
        """
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    # "model" intentionally omitted
                    "someBrandNewField": {"nested": True},
                    "uplinks": [
                        {
                            "interface": "cellular",
                            "status": "active",
                            "aFutureApiField": "unexpected",
                        }
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2XX-1": {
                "name": "Gateway 1",
                "model": "MG21-FROM-LOOKUP",
                "network_id": "N_1",
                "network_name": "Main Network",
            }
        }

        await mg_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_uplink_status_info
        ]
        assert len(info_calls) == 1
        _, labels, value, *_ = info_calls[0][0]
        assert value == 1
        assert labels["model"] == "MG21-FROM-LOOKUP"
        assert labels["serial"] == "Q2XX-1"

    # ------------------------------------------------------------------
    # #304 — Cellular band config + serving cell (Phase 4, spec-only)
    # ------------------------------------------------------------------

    def test_mg_cellular_gauges_created_on_init(
        self,
        mg_collector: MGCollector,
        mock_parent: MagicMock,
    ) -> None:
        """New #304 gauges must be created alongside the existing MG gauges."""
        assert mg_collector._mg_cellular_bands is not None
        assert mg_collector._mg_serving_cell_info is not None

    async def test_collect_uplink_statuses_also_triggers_cellular_config(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The entrypoint device.py already invokes must also fetch #304 data.

        collect_uplink_statuses must also gate + fetch the #304
        cellular-config groups, since device.py is not being modified to add
        a second call site.
        """
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._should_run_group.assert_any_call(EndpointGroupName.MG_UPLINK_STATUS)
        mock_parent._should_run_group.assert_any_call(EndpointGroupName.MG_CELLULAR_CONFIG)
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice.assert_called_once()
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice.assert_called_once()
        mock_parent._mark_group_ran.assert_any_call(EndpointGroupName.MG_CELLULAR_CONFIG)

    async def test_cellular_config_gated_by_scheduler_skips_both_fetches(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When MG_CELLULAR_CONFIG is not due, neither fetch should run."""
        mock_parent._should_run_group = MagicMock(
            side_effect=lambda group: group != EndpointGroupName.MG_CELLULAR_CONFIG
        )
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice.assert_not_called()
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice.assert_not_called()
        assert (
            mock_parent._mark_group_ran.call_args_list.count((
                (EndpointGroupName.MG_CELLULAR_CONFIG,),
                {},
            ))
            == 0
        )

    async def test_collect_cellular_bands_nested_rat_shape(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Nested {slot: {rat: {status: [bands]}}} shape is counted correctly."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "network": {"id": "N_1"},
                    "bands": {
                        "sim1": {
                            "lte": {"enabled": ["B2", "B4"], "masked": ["B66"]},
                            "5gNsa": {"enabled": ["n41"]},
                        }
                    },
                }
            ]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        by_key = {
            (c[0][1]["slot"], c[0][1]["connection_type"], c[0][1]["status"]): c[0][2]
            for c in band_calls
        }
        assert by_key[("sim1", "lte", "enabled")] == 2
        assert by_key[("sim1", "lte", "masked")] == 1
        assert by_key[("sim1", "5gNsa", "enabled")] == 1
        # ID-only labels: serial/model present, no name-family labels.
        assert band_calls[0][0][1]["serial"] == "Q2XX-1"
        assert band_calls[0][0][1]["network_id"] == "N_1"

    async def test_collect_cellular_bands_flat_list_shape(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Fallback flat-list-of-entries shape is also handled defensively."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "networkId": "N_1",
                    "bands": {
                        "sim1": [
                            {"connectionType": "lte", "status": "enabled", "band": "B2"},
                            {"connectionType": "lte", "status": "enabled", "band": "B4"},
                            {"type": "unknownRat", "status": "supported", "band": "X"},
                        ]
                    },
                }
            ]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        by_key = {
            (c[0][1]["slot"], c[0][1]["connection_type"], c[0][1]["status"]): c[0][2]
            for c in band_calls
        }
        assert by_key[("sim1", "lte", "enabled")] == 2
        # Unrecognized RAT strings collapse to the bounded "other" bucket.
        assert by_key[("sim1", "other", "supported")] == 1

    async def test_collect_cellular_bands_unknown_slot_and_status_dropped(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Unknown slot keys and unbounded status strings must never be emitted."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "networkId": "N_1",
                    "bands": {
                        "simX": {"lte": {"enabled": ["B2"]}},
                        "sim1": {"lte": {"weird-unbounded-status": ["B2"]}},
                    },
                }
            ]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        assert band_calls == []

    async def test_collect_cellular_bands_respects_network_filter(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit band-count metrics."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "networkId": "N_INCLUDED",
                    "bands": {"sim1": {"lte": {"enabled": ["B2"]}}},
                },
                {
                    "serial": "Q-OUT",
                    "networkId": "N_EXCLUDED",
                    "bands": {"sim1": {"lte": {"enabled": ["B2"]}}},
                },
            ]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        assert len(band_calls) == 1
        assert band_calls[0][0][1]["serial"] == "Q-IN"

    async def test_collect_cellular_bands_empty_response(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Empty bands response must not raise or emit metrics."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        assert band_calls == []

    async def test_collect_cellular_bands_api_error_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API error on the bands call must not raise.

        It also must not block the independent towers fetch.
        """
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            side_effect=Exception("API connection failed")
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[
                {"serial": "Q2XX-1", "networkId": "N_1", "towers": [{"cellId": "1", "tac": "2"}]}
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        serving_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_serving_cell_info
        ]
        assert band_calls == []
        assert len(serving_calls) == 1

    async def test_collect_cellular_bands_exhausted_retry_error_shape_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape must be absorbed, not raised."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value={"errors": ["internal server error"]}
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        assert band_calls == []

    async def test_collect_cellular_bands_validates_rows_via_domain_model(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Each raw row must be validated via MGCellularBandsDevice.model_validate."""
        row = {
            "serial": "Q2XX-1",
            "networkId": "N_1",
            "bands": {"sim1": {"lte": {"enabled": ["B2"]}}},
        }
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[row]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mg.MGCellularBandsDevice.model_validate",
            wraps=MGCellularBandsDevice.model_validate,
        ) as spy:
            await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        spy.assert_called_once_with(row)

    async def test_collect_cellular_bands_tolerates_missing_and_extra_fields(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Missing optional fields and unexpected extra fields must not raise."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    # "model" and "network"/"networkId" intentionally omitted
                    "someBrandNewField": {"nested": True},
                    "bands": {"sim1": {"lte": {"enabled": ["B2"]}}},
                }
            ]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        device_lookup = {
            "Q2XX-1": {"model": "MG21-FROM-LOOKUP", "network_id": "N_1"},
        }

        await mg_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        band_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_cellular_bands
        ]
        assert len(band_calls) == 1
        assert band_calls[0][0][1]["model"] == "MG21-FROM-LOOKUP"
        assert band_calls[0][0][1]["network_id"] == "N_1"

    async def test_collect_cellular_bands_does_not_wipe_other_orgs(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The shared gauge must not be cleared globally (multi-org safety)."""
        bands_gauge = mg_collector._mg_cellular_bands
        bands_gauge.labels(
            org_id="org2",
            network_id="N_2",
            serial="Q2ZZ-OTHER",
            model="MG21",
            device_type="MG",
            slot="sim1",
            connection_type="lte",
            status="enabled",
        ).set(3)
        assert len(bands_gauge._metrics) == 1

        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "networkId": "N_1",
                    "bands": {"sim1": {"lte": {"enabled": ["B2"]}}},
                }
            ]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        # _set_metric is mocked (as in the sibling uplink-status test above),
        # so it never touches the real gauge here - the assertion that
        # matters is that org2's pre-seeded series is untouched, i.e. nothing
        # in the collection path calls a global bands_gauge.clear()/wipe.
        assert len(bands_gauge._metrics) == 1

    # ------------------------------------------------------------------
    # #304 — serving cell info
    # ------------------------------------------------------------------

    async def test_collect_serving_cell_basic(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A single tower entry emits one serving-cell info series."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "network": {"id": "N_1"},
                    "towers": [{"cellId": "12345", "tac": "6789"}],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        serving_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_serving_cell_info
        ]
        assert len(serving_calls) == 1
        _, labels, value, *_ = serving_calls[0][0]
        assert value == 1
        assert labels["cell_id"] == "12345"
        assert labels["tac"] == "6789"
        assert labels["serial"] == "Q2XX-1"
        assert labels["network_id"] == "N_1"

    async def test_collect_serving_cell_prefers_serving_flagged_entry(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When multiple tower entries exist, prefer one flagged as serving."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "networkId": "N_1",
                    "towers": [
                        {"cellId": "111", "tac": "1"},
                        {"cellId": "222", "tac": "2", "serving": True},
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        serving_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_serving_cell_info
        ]
        assert len(serving_calls) == 1
        assert serving_calls[0][0][1]["cell_id"] == "222"
        assert serving_calls[0][0][1]["tac"] == "2"

    async def test_collect_serving_cell_no_usable_id_skips_emission(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A towers list with no usable cell-id field emits no metric."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[{"serial": "Q2XX-1", "networkId": "N_1", "towers": [{"foo": "bar"}]}]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        serving_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_serving_cell_info
        ]
        assert serving_calls == []

    async def test_collect_serving_cell_empty_towers_list_skips_emission(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty towers list for a device emits no metric (no crash)."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[{"serial": "Q2XX-1", "networkId": "N_1", "towers": []}]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        serving_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_serving_cell_info
        ]
        assert serving_calls == []

    async def test_collect_serving_cell_respects_network_filter(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit serving-cell metrics."""
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "networkId": "N_INCLUDED",
                    "towers": [{"cellId": "1", "tac": "2"}],
                },
                {
                    "serial": "Q-OUT",
                    "networkId": "N_EXCLUDED",
                    "towers": [{"cellId": "3", "tac": "4"}],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        serving_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_serving_cell_info
        ]
        assert len(serving_calls) == 1
        assert serving_calls[0][0][1]["serial"] == "Q-IN"

    async def test_collect_serving_cell_validates_rows_via_domain_model(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Each raw towers row must be validated via MGCellularTowersDevice.model_validate."""
        row = {
            "serial": "Q2XX-1",
            "networkId": "N_1",
            "towers": [{"cellId": "1", "tac": "2"}],
        }
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[row]
        )

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mg.MGCellularTowersDevice.model_validate",
            wraps=MGCellularTowersDevice.model_validate,
        ) as spy:
            await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        spy.assert_called_once_with(row)

    # ------------------------------------------------------------------
    # #327 — eSIM inventory (Phase 4B, spec-only)
    # ------------------------------------------------------------------

    def _empty_esims(self, mock_api: MagicMock) -> None:
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[]
        )

    def _empty_ha(self, mock_api: MagicMock) -> None:
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(return_value=[])

    def test_mg_esim_gauges_created_on_init(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """New #327 gauges must be created alongside the existing MG gauges."""
        assert mg_collector._mg_esims is not None
        assert mg_collector._mg_esim_info is not None
        assert mg_collector._mg_esim_active is not None

    async def test_collect_uplink_statuses_also_triggers_esim_and_ha(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The entrypoint device.py already invokes must also fetch #327/#328 data."""
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice = MagicMock(
            return_value=[]
        )
        mock_api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice = MagicMock(
            return_value=[]
        )
        self._empty_esims(mock_api)
        self._empty_ha(mock_api)

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_parent._should_run_group.assert_any_call(EndpointGroupName.MG_ESIMS)
        mock_parent._should_run_group.assert_any_call(EndpointGroupName.MG_HA)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory.assert_called_once_with(
            "org1"
        )
        mock_api.organizations.getOrganizationUplinksStatuses.assert_called_once_with(
            "org1", total_pages="all", perPage=1000
        )
        mock_parent._mark_group_ran.assert_any_call(EndpointGroupName.MG_ESIMS)
        mock_parent._mark_group_ran.assert_any_call(EndpointGroupName.MG_HA)

    async def test_esim_inventory_gated_by_scheduler_skips_fetch(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When MG_ESIMS is not due, the fetch must not run."""
        mock_parent._should_run_group = MagicMock(
            side_effect=lambda group: group != EndpointGroupName.MG_ESIMS
        )
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )
        self._empty_ha(mock_api)

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory.assert_not_called()

    async def test_ha_status_gated_by_scheduler_skips_fetch(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When MG_HA is not due, the fetch must not run."""
        mock_parent._should_run_group = MagicMock(
            side_effect=lambda group: group != EndpointGroupName.MG_HA
        )
        mock_api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses = MagicMock(
            return_value=[]
        )
        self._empty_esims(mock_api)

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        mock_api.organizations.getOrganizationUplinksStatuses.assert_not_called()

    async def test_collect_esim_inventory_basic(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A basic eSIM inventory row emits count + info + active metrics."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "89049...001",
                    "active": True,
                    "device": {"serial": "Q2XX-1", "model": "MG21"},
                    "network": {"id": "N_1"},
                    "profiles": [
                        {
                            "iccid": "12345",
                            "status": "active",
                            "serviceProvider": {"name": "Verizon"},
                        },
                        {
                            "iccid": "67890",
                            "status": "inactive",
                            "serviceProvider": {"name": "AT&T"},
                        },
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        count_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_esims
        ]
        assert len(count_calls) == 1
        assert count_calls[0][0][2] == 1
        assert count_calls[0][0][1]["org_id"] == "org1"

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert len(info_calls) == 1
        _, info_labels, info_value, *_ = info_calls[0][0]
        assert info_value == 1
        assert info_labels["eid"] == "89049...001"
        assert info_labels["serial"] == "Q2XX-1"
        assert info_labels["network_id"] == "N_1"
        # Only the "active" profile's provider is used.
        assert info_labels["provider"] == "Verizon"

        active_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_active
        ]
        assert len(active_calls) == 1
        _, active_labels, active_value, *_ = active_calls[0][0]
        assert active_value == 1.0
        assert active_labels["eid"] == "89049...001"
        assert active_labels["serial"] == "Q2XX-1"
        assert "network_id" not in active_labels

    async def test_collect_esim_inventory_no_active_profile_empty_provider(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When no profile has status 'active', provider must be empty string."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "EID1",
                    "active": False,
                    "device": {"serial": "Q2XX-1"},
                    "network": {"id": "N_1"},
                    "profiles": [
                        {"iccid": "1", "status": "inactive", "serviceProvider": {"name": "X"}}
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert len(info_calls) == 1
        assert not info_calls[0][0][1]["provider"]

        active_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_active
        ]
        assert active_calls[0][0][2] == 0.0

    async def test_collect_esim_inventory_no_profiles_empty_provider(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An eSIM with no profiles at all must not raise and yields empty provider."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "EID1",
                    "active": True,
                    "device": {"serial": "Q2XX-1"},
                    "network": {"id": "N_1"},
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert len(info_calls) == 1
        assert not info_calls[0][0][1]["provider"]

    async def test_collect_esim_inventory_does_not_emit_plan_names(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Plan names are multi-valued and must never be emitted as labels (v1 scope)."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "EID1",
                    "active": True,
                    "device": {"serial": "Q2XX-1"},
                    "network": {"id": "N_1"},
                    "profiles": [
                        {
                            "status": "active",
                            "serviceProvider": {
                                "name": "Verizon",
                                "plans": [{"name": "Unlimited", "type": "data"}],
                            },
                        }
                    ],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        for call in info_calls:
            labels = call[0][1]
            assert "plans" not in labels
            assert "plan" not in labels

    async def test_collect_esim_inventory_respects_network_filter(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """eSIMs on excluded networks must not emit info/active metrics."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "EID-IN",
                    "active": True,
                    "device": {"serial": "Q-IN"},
                    "network": {"id": "N_INCLUDED"},
                    "profiles": [],
                },
                {
                    "eid": "EID-OUT",
                    "active": True,
                    "device": {"serial": "Q-OUT"},
                    "network": {"id": "N_EXCLUDED"},
                    "profiles": [],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert len(info_calls) == 1
        assert info_calls[0][0][1]["serial"] == "Q-IN"

        # The org-wide count snapshot is NOT filtered - it reflects total inventory.
        count_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_esims
        ]
        assert count_calls[0][0][2] == 2

    async def test_collect_esim_inventory_empty_response(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty eSIM inventory still emits a zero-count snapshot, no crash."""
        self._empty_ha(mock_api)
        self._empty_esims(mock_api)

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        count_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_esims
        ]
        assert len(count_calls) == 1
        assert count_calls[0][0][2] == 0

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert info_calls == []

    async def test_collect_esim_inventory_api_error_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API error on the eSIM fetch must not raise and must not block HA."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert info_calls == []
        mock_api.organizations.getOrganizationUplinksStatuses.assert_called_once()

    async def test_collect_esim_inventory_exhausted_retry_error_shape_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape must be absorbed, not raised."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        count_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_esims
        ]
        assert count_calls == []

    async def test_collect_esim_inventory_validates_rows_via_domain_model(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Each raw row must be validated via MGEsimInventoryRow.model_validate."""
        self._empty_ha(mock_api)
        row = {
            "eid": "EID1",
            "active": True,
            "device": {"serial": "Q2XX-1"},
            "network": {"id": "N_1"},
            "profiles": [],
        }
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[row]
        )

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mg.MGEsimInventoryRow.model_validate",
            wraps=MGEsimInventoryRow.model_validate,
        ) as spy:
            await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        spy.assert_called_once_with(row)

    async def test_collect_esim_inventory_tolerates_missing_and_extra_fields(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Missing optional fields and unexpected extra fields must not raise."""
        self._empty_ha(mock_api)
        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "EID1",
                    "someBrandNewField": {"nested": True},
                    # "device"/"network"/"active"/"profiles" all omitted
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        info_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_esim_info
        ]
        assert len(info_calls) == 1
        assert not info_calls[0][0][1]["serial"]
        assert not info_calls[0][0][1]["network_id"]
        assert not info_calls[0][0][1]["provider"]

    async def test_collect_esim_inventory_does_not_wipe_other_orgs(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The shared gauges must not be cleared globally (multi-org safety)."""
        self._empty_ha(mock_api)
        info_gauge = mg_collector._mg_esim_info
        info_gauge.labels(
            org_id="org2", eid="EID-OTHER", serial="Q2ZZ-OTHER", network_id="N_2", provider="X"
        ).set(1)
        assert len(info_gauge._metrics) == 1

        mock_api.cellularGateway.getOrganizationCellularGatewayEsimsInventory = MagicMock(
            return_value=[
                {
                    "eid": "EID1",
                    "active": True,
                    "device": {"serial": "Q2XX-1"},
                    "network": {"id": "N_1"},
                    "profiles": [],
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        assert len(info_gauge._metrics) == 1

    # ------------------------------------------------------------------
    # #328 — MG HA role (Phase 4B, spec-only)
    # ------------------------------------------------------------------

    def test_mg_ha_gauges_created_on_init(
        self,
        mg_collector: MGCollector,
    ) -> None:
        """New #328 gauges must be created alongside the existing MG gauges."""
        assert mg_collector._mg_ha_enabled is not None
        assert mg_collector._mg_ha_role is not None

    async def test_collect_ha_status_basic(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A basic MG HA row emits enabled + role metrics."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "uplinks": [{"interface": "cellular", "status": "active"}],
                    "highAvailability": {"enabled": True, "role": "primary"},
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert len(enabled_calls) == 1
        _, enabled_labels, enabled_value, *_ = enabled_calls[0][0]
        assert enabled_value == 1.0
        assert enabled_labels["serial"] == "Q2XX-1"
        assert enabled_labels["network_id"] == "N_1"

        role_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_ha_role
        ]
        assert len(role_calls) == 1
        _, role_labels, role_value, *_ = role_calls[0][0]
        assert role_value == 1
        assert role_labels["role"] == "primary"

    async def test_collect_ha_status_spare_role(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A 'spare' role is a valid bounded value and must be emitted."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "highAvailability": {"enabled": True, "role": "spare"},
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        role_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_ha_role
        ]
        assert len(role_calls) == 1
        assert role_calls[0][0][1]["role"] == "spare"

    async def test_collect_ha_status_unknown_role_dropped(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An unbounded/unexpected role value must never be emitted as a label."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "highAvailability": {"enabled": True, "role": "some-unbounded-value"},
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        role_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_ha_role
        ]
        assert role_calls == []
        # enabled is independent of role validity - it must still be emitted.
        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert len(enabled_calls) == 1

    async def test_collect_ha_status_ignores_mx_rows(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """MX rows in the same org-wide response must not be touched."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q-MX-1",
                    "model": "MX67",
                    "highAvailability": {"enabled": True, "role": "primary"},
                },
                {
                    "networkId": "N_2",
                    "serial": "Q-MG-1",
                    "model": "MG21",
                    "highAvailability": {"enabled": False, "role": "primary"},
                },
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert len(enabled_calls) == 1
        assert enabled_calls[0][0][1]["serial"] == "Q-MG-1"

    async def test_collect_ha_status_identifies_mg_via_device_lookup_fallback(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When a row's own model is missing, fall back to the device lookup."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    # "model" intentionally omitted from the row
                    "highAvailability": {"enabled": True, "role": "primary"},
                }
            ]
        )
        device_lookup = {
            "Q2XX-1": {"model": "MG21", "network_id": "N_1", "device_type": "MG"},
        }

        await mg_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert len(enabled_calls) == 1

    async def test_collect_ha_status_no_ha_object_skips_emission(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A row with no highAvailability object emits neither metric."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        role_calls = [
            c for c in mock_parent._set_metric.call_args_list if c[0][0] is mg_collector._mg_ha_role
        ]
        assert enabled_calls == []
        assert role_calls == []

    async def test_collect_ha_status_respects_network_filter(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """MG rows on excluded networks must not emit HA metrics."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "serial": "Q-IN",
                    "model": "MG21",
                    "highAvailability": {"enabled": True, "role": "primary"},
                },
                {
                    "networkId": "N_EXCLUDED",
                    "serial": "Q-OUT",
                    "model": "MG21",
                    "highAvailability": {"enabled": True, "role": "primary"},
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert len(enabled_calls) == 1
        assert enabled_calls[0][0][1]["serial"] == "Q-IN"

    async def test_collect_ha_status_empty_response(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty response must not raise or emit metrics."""
        self._empty_esims(mock_api)
        self._empty_ha(mock_api)

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert enabled_calls == []

    async def test_collect_ha_status_api_error_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API error on the HA fetch must not raise."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert enabled_calls == []

    async def test_collect_ha_status_exhausted_retry_error_shape_handled_gracefully(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape must be absorbed, not raised."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert enabled_calls == []

    async def test_collect_ha_status_validates_rows_via_domain_model(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Each raw row must be validated via MGUplinkStatusRow.model_validate."""
        self._empty_esims(mock_api)
        row = {
            "networkId": "N_1",
            "serial": "Q2XX-1",
            "model": "MG21",
            "highAvailability": {"enabled": True, "role": "primary"},
        }
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(return_value=[row])

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mg.MGUplinkStatusRow.model_validate",
            wraps=MGUplinkStatusRow.model_validate,
        ) as spy:
            await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        spy.assert_called_once_with(row)

    async def test_collect_ha_status_tolerates_missing_and_extra_fields(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Missing optional fields and unexpected extra fields must not raise."""
        self._empty_esims(mock_api)
        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    # "networkId" intentionally omitted
                    "someBrandNewField": {"nested": True},
                    "highAvailability": {
                        "enabled": True,
                        "role": "primary",
                        "aFutureApiField": "unexpected",
                    },
                }
            ]
        )
        device_lookup = {"Q2XX-1": {"network_id": "N_1_FROM_LOOKUP"}}

        await mg_collector.collect_uplink_statuses("org1", "Test Org", device_lookup)

        enabled_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is mg_collector._mg_ha_enabled
        ]
        assert len(enabled_calls) == 1
        assert enabled_calls[0][0][1]["network_id"] == "N_1_FROM_LOOKUP"

    async def test_collect_ha_status_does_not_wipe_other_orgs(
        self,
        mg_collector: MGCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The shared gauges must not be cleared globally (multi-org safety)."""
        self._empty_esims(mock_api)
        role_gauge = mg_collector._mg_ha_role
        role_gauge.labels(org_id="org2", network_id="N_2", serial="Q2ZZ-OTHER", role="primary").set(
            1
        )
        assert len(role_gauge._metrics) == 1

        mock_api.organizations.getOrganizationUplinksStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "serial": "Q2XX-1",
                    "model": "MG21",
                    "highAvailability": {"enabled": True, "role": "spare"},
                }
            ]
        )

        await mg_collector.collect_uplink_statuses("org1", "Test Org", {})

        assert len(role_gauge._metrics) == 1
