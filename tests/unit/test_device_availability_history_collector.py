"""Tests for the DeviceAvailabilityHistoryCollector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.device_availability_history import (
    DeviceAvailabilityHistoryCollector,
)

if TYPE_CHECKING:
    pass


class TestDeviceAvailabilityHistoryCollector:
    """Test DeviceAvailabilityHistoryCollector functionality."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        from pydantic import SecretStr

        from meraki_dashboard_exporter.core.config import Settings
        from meraki_dashboard_exporter.core.config_models import MerakiSettings

        return Settings(
            meraki=MerakiSettings(
                api_key=SecretStr("6bec40cf957de430a6f1f2baa056b367d6172e1e"), org_id="test-org-id"
            )
        )

    @pytest.fixture
    def isolated_registry(self, monkeypatch):
        """Create an isolated Prometheus registry."""
        from prometheus_client import CollectorRegistry

        registry = CollectorRegistry()
        return registry

    @pytest.fixture
    def availability_history_collector(
        self, mock_api_builder, settings, isolated_registry
    ) -> DeviceAvailabilityHistoryCollector:
        """Create DeviceAvailabilityHistoryCollector instance with mocked dependencies."""

        class MockParentCollector:
            def __init__(self) -> None:
                self.api = mock_api_builder.build()
                self.settings = settings
                self._api_calls: dict[str, int] = {}
                self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

            def _track_api_call(self, method_name: str) -> None:
                self._api_calls[method_name] = self._api_calls.get(method_name, 0) + 1

            def _set_metric_value(
                self, metric_name: str, labels: dict[str, str], value: float | None
            ) -> None:
                if value is not None:
                    key = (metric_name, tuple(sorted(labels.items())))
                    self._metrics[key] = value

        parent = MockParentCollector()
        return DeviceAvailabilityHistoryCollector(parent=parent)  # type: ignore[arg-type]

    async def test_collect_availability_changes_by_product_and_status(
        self, availability_history_collector, mock_api_builder
    ):
        """Test aggregation of availability change events by (productType, new_status)."""
        org_id = "123"
        org_name = "Test Org"

        events_response = [
            {
                "ts": "2026-07-01T00:00:00Z",
                "device": {
                    "serial": "Q2XX-0001",
                    "name": "AP1",
                    "productType": "wireless",
                    "model": "MR46",
                },
                "details": {
                    "old": [{"name": "status", "value": "online"}],
                    "new": [{"name": "status", "value": "offline"}],
                },
                "network": {"id": "n1", "name": "Network 1"},
            },
            {
                "ts": "2026-07-01T00:01:00Z",
                "device": {
                    "serial": "Q2XX-0002",
                    "name": "AP2",
                    "productType": "wireless",
                    "model": "MR46",
                },
                "details": {
                    "old": [{"name": "status", "value": "online"}],
                    "new": [{"name": "status", "value": "offline"}],
                },
                "network": {"id": "n2", "name": "Network 2"},
            },
            {
                "ts": "2026-07-01T00:02:00Z",
                "device": {
                    "serial": "Q2XX-0003",
                    "name": "SW1",
                    "productType": "switch",
                    "model": "MS120",
                },
                "details": {
                    "old": [{"name": "status", "value": "offline"}],
                    "new": [{"name": "status", "value": "online"}],
                },
                "network": {"id": "n3", "name": "Network 3"},
            },
            {
                "ts": "2026-07-01T00:03:00Z",
                "device": {
                    "serial": "Q2XX-0004",
                    "name": "SW2",
                    "productType": "switch",
                    "model": "MS120",
                },
                "details": {
                    "old": [{"name": "status", "value": "online"}],
                    "new": [{"name": "status", "value": "dormant"}],
                },
                "network": {"id": "n4", "name": "Network 4"},
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesAvailabilitiesChangeHistory", events_response
        ).build()
        availability_history_collector.api = api

        await availability_history_collector.collect(org_id, org_name)

        assert api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory.called
        call_args = api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory.call_args
        assert call_args[0][0] == org_id
        assert call_args[1]["timespan"] == 300
        assert call_args[1]["total_pages"] == "all"

        parent = availability_history_collector.parent

        expected_totals = [
            ("wireless", "offline", 2),
            ("switch", "online", 1),
            ("switch", "dormant", 1),
        ]
        for product_type, status, count in expected_totals:
            key = (
                "_org_devices_availability_changes_total",
                (
                    ("org_id", org_id),
                    ("org_name", org_name),
                    ("product_type", product_type),
                    ("status", status),
                ),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

    async def test_collect_with_empty_response(
        self, availability_history_collector, mock_api_builder
    ):
        """Test handling of empty availability change event list."""
        org_id = "456"
        org_name = "Empty Org"

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesAvailabilitiesChangeHistory", []
        ).build()
        availability_history_collector.api = api

        await availability_history_collector.collect(org_id, org_name)

        parent = availability_history_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_missing_status_defaults_to_unknown(
        self, availability_history_collector, mock_api_builder
    ):
        """Test that a missing 'status' detail defaults new_status to 'unknown'."""
        org_id = "789"
        org_name = "Missing Status Org"

        events_response = [
            {
                "ts": "2026-07-01T00:00:00Z",
                "device": {"serial": "Q2XX-0005", "name": "Dev1", "productType": "appliance"},
                "details": {
                    "old": [{"name": "status", "value": "online"}],
                    "new": [{"name": "somethingElse", "value": "foo"}],
                },
                "network": {"id": "n1", "name": "Network 1"},
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesAvailabilitiesChangeHistory", events_response
        ).build()
        availability_history_collector.api = api

        await availability_history_collector.collect(org_id, org_name)

        parent = availability_history_collector.parent
        key = (
            "_org_devices_availability_changes_total",
            (
                ("org_id", org_id),
                ("org_name", org_name),
                ("product_type", "appliance"),
                ("status", "unknown"),
            ),
        )
        assert key in parent._metrics
        assert parent._metrics[key] == 1

    async def test_collect_with_missing_product_type_defaults_to_unknown(
        self, availability_history_collector, mock_api_builder
    ):
        """Test that a missing device.productType defaults to 'unknown'."""
        org_id = "111"
        org_name = "Missing Product Type Org"

        events_response = [
            {
                "ts": "2026-07-01T00:00:00Z",
                "device": {"serial": "Q2XX-0006", "name": "Dev2"},
                "details": {
                    "old": [{"name": "status", "value": "online"}],
                    "new": [{"name": "status", "value": "offline"}],
                },
                "network": {"id": "n1", "name": "Network 1"},
            },
        ]

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesAvailabilitiesChangeHistory", events_response
        ).build()
        availability_history_collector.api = api

        await availability_history_collector.collect(org_id, org_name)

        parent = availability_history_collector.parent
        key = (
            "_org_devices_availability_changes_total",
            (
                ("org_id", org_id),
                ("org_name", org_name),
                ("product_type", "unknown"),
                ("status", "offline"),
            ),
        )
        assert key in parent._metrics
        assert parent._metrics[key] == 1

    async def test_collect_with_404_error(self, availability_history_collector, mock_api_builder):
        """Test handling of 404 error (no availability history info)."""
        org_id = "222"
        org_name = "No History API Org"

        api = mock_api_builder.with_error(
            "getOrganizationDevicesAvailabilitiesChangeHistory", Exception("404 Not Found")
        ).build()
        availability_history_collector.api = api

        await availability_history_collector.collect(org_id, org_name)

        parent = availability_history_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_api_error(self, availability_history_collector, mock_api_builder):
        """Test handling of general API errors."""
        org_id = "333"
        org_name = "API Error Org"

        api = mock_api_builder.with_error(
            "getOrganizationDevicesAvailabilitiesChangeHistory", Exception("Connection timeout")
        ).build()
        availability_history_collector.api = api

        await availability_history_collector.collect(org_id, org_name)

        parent = availability_history_collector.parent
        assert len(parent._metrics) == 0

    async def test_fetch_availability_change_history_parameters(
        self, availability_history_collector, mock_api_builder
    ):
        """Test that _fetch_availability_change_history passes correct parameters."""
        org_id = "test-org-123"

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesAvailabilitiesChangeHistory", []
        ).build()
        availability_history_collector.api = api

        result = await availability_history_collector._fetch_availability_change_history(org_id)

        assert api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory.called
        call_args = api.organizations.getOrganizationDevicesAvailabilitiesChangeHistory.call_args
        assert call_args[0][0] == org_id
        assert call_args[1]["timespan"] == 300
        assert call_args[1]["total_pages"] == "all"
        assert result == []
