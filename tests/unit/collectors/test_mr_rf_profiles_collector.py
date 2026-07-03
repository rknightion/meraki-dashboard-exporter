"""Tests for MR RF profile assignment drift collector (#291)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr.rf_profiles import MRRfProfilesCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    pass


def _make_gauge(name: str, description: str, labelnames: list[str]) -> Gauge:
    """Create a real Prometheus Gauge using the enum value as the metric name."""
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


class TestMRRfProfilesCollector:
    """Test MR RF profile assignment drift collector."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock Meraki DashboardAPI client."""
        api = MagicMock()
        api.wireless = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent collector (DeviceCollector) instance."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collector emits all rows.
        parent.inventory = None
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        parent._should_run_group = MagicMock(return_value=True)
        parent._group_ttl_seconds = MagicMock(return_value=None)
        parent._mark_group_ran = MagicMock()
        return parent

    @pytest.fixture
    def rf_profiles_collector(self, mock_parent: MagicMock) -> MRRfProfilesCollector:
        """Create an MRRfProfilesCollector instance backed by mock parent."""
        return MRRfProfilesCollector(mock_parent)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation_creates_info_metric(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_parent: MagicMock,
    ) -> None:
        """The RF profile info gauge must be created with the expected labels."""
        mock_parent._create_gauge.assert_called_once()
        args, kwargs = mock_parent._create_gauge.call_args
        assert args[0] == MRMetricName.MR_RF_PROFILE_INFO
        assert set(kwargs["labelnames"]) == {
            "org_id",
            "network_id",
            "serial",
            "rf_profile_id",
            "rf_profile_name",
            "is_default",
        }

    def test_initialisation_stores_parent_api_settings(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_parent: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Collector should hold references to parent, api, and settings."""
        assert rf_profiles_collector.parent is mock_parent
        assert rf_profiles_collector.api is mock_api
        assert rf_profiles_collector.settings is mock_parent.settings

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    async def test_emits_one_series_per_ap(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """One info series per AP, with rf_profile_id/name/is_default populated."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q123",
                    "name": "AP1",
                    "network": {"id": "net1", "name": "Network 1"},
                    "rfProfile": {"id": 1234, "name": "Custom Profile"},
                },
                {
                    "serial": "Q456",
                    "name": "AP2",
                    "network": {"id": "net1", "name": "Network 1"},
                    "rfProfile": {
                        "id": "default-indoor",
                        "name": "Indoor default",
                        "isIndoorDefault": True,
                    },
                },
            ]
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice.assert_called_once_with(
            "org1", total_pages="all", perPage=1000
        )

        calls = {
            c[0][1]["serial"]: c[0][1]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is rf_profiles_collector._rf_profile_info
        }
        assert set(calls) == {"Q123", "Q456"}

        assert calls["Q123"]["rf_profile_id"] == "1234"
        assert calls["Q123"]["rf_profile_name"] == "Custom Profile"
        assert calls["Q123"]["is_default"] == "false"
        assert calls["Q123"]["network_id"] == "net1"
        assert calls["Q123"]["org_id"] == "org1"

        assert calls["Q456"]["rf_profile_id"] == "default-indoor"
        assert calls["Q456"]["is_default"] == "true"

        # Value is always the constant 1 (join/info-carrier series).
        for c in mock_parent._set_metric.call_args_list:
            if c[0][0] is rf_profiles_collector._rf_profile_info:
                assert c[0][2] == 1.0

    async def test_is_default_true_from_outdoor_flag(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """isOutdoorDefault alone must also set is_default=true."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q789",
                    "network": {"id": "net1"},
                    "rfProfile": {
                        "id": "default-outdoor",
                        "name": "Outdoor default",
                        "isOutdoorDefault": True,
                    },
                },
            ]
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is rf_profiles_collector._rf_profile_info
        ]
        assert len(calls) == 1
        assert calls[0][0][1]["is_default"] == "true"

    async def test_missing_rf_profile_skips_row(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An AP row with no rfProfile assignment data has nothing to join on."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[
                {"serial": "Q999", "network": {"id": "net1"}},
            ]
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_missing_serial_skips_row(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A row without a serial has nothing to key the series on and must be skipped."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[
                {"network": {"id": "net1"}, "rfProfile": {"id": 1, "name": "X"}},
            ]
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    # ------------------------------------------------------------------
    # NetworkFilter enforcement
    # ------------------------------------------------------------------

    async def test_respects_network_filter(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """RF profile assignment rows for excluded networks must be skipped."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q-IN",
                    "network": {"id": "N_INCLUDED"},
                    "rfProfile": {"id": 1, "name": "Profile A"},
                },
                {
                    "serial": "Q-OUT",
                    "network": {"id": "N_EXCLUDED"},
                    "rfProfile": {"id": 2, "name": "Profile B"},
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is rf_profiles_collector._rf_profile_info
        ]
        assert len(calls) == 1
        assert calls[0][0][1]["serial"] == "Q-IN"

    # ------------------------------------------------------------------
    # Scheduler gating (#617)
    # ------------------------------------------------------------------

    async def test_gate_closed_skips_fetch(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A closed mr_rf_profiles gate must skip the API call and not mark ran."""
        mock_parent._should_run_group = MagicMock(return_value=False)

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_gate_open_marks_ran_after_success(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A successful fetch marks the mr_rf_profiles group ran exactly once."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[]
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MR_RF_PROFILES)

    async def test_ttl_threaded_to_every_emission(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The solved per-series TTL must be forwarded to every _set_metric call."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=900.0)
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value=[
                {
                    "serial": "Q1",
                    "network": {"id": "net1"},
                    "rfProfile": {"id": 1, "name": "X"},
                },
            ]
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs["ttl_seconds"] == 900.0

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def test_error_shape_response_handled_gracefully(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape must be absorbed, not raised."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_api_exception_handled_gracefully(
        self,
        rf_profiles_collector: MRRfProfilesCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API exception must not propagate — @with_error_handling absorbs it."""
        mock_api.wireless.getOrganizationWirelessRfProfilesAssignmentsByDevice = MagicMock(
            side_effect=Exception("connection reset")
        )

        await rf_profiles_collector.collect_rf_profile_assignments("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    # ------------------------------------------------------------------
    # Domain-model validation
    # ------------------------------------------------------------------

    def test_assignment_validates_via_domain_model(self) -> None:
        """The RF profile assignment row parses via a typed Pydantic domain model."""
        from meraki_dashboard_exporter.core.domain_models import WirelessRfProfileAssignment

        parsed = WirelessRfProfileAssignment.model_validate({
            "serial": "Q1",
            "network": {"id": "net1", "name": "Network 1"},
            "rfProfile": {"id": 5, "name": "Profile", "isIndoorDefault": True},
        })
        assert parsed.serial == "Q1"
        assert parsed.network is not None
        assert parsed.network.id == "net1"
        assert parsed.rfProfile is not None
        assert parsed.rfProfile.name == "Profile"
        assert parsed.rfProfile.isIndoorDefault is True
