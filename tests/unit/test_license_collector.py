"""Tests for the LicenseCollector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.license import LicenseCollector

if TYPE_CHECKING:
    pass


class TestLicenseCollector:
    """Test LicenseCollector functionality."""

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
    def license_collector(self, mock_api_builder, settings, isolated_registry) -> LicenseCollector:
        """Create LicenseCollector instance with mocked dependencies."""

        # Create a mock parent collector with required attributes
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
                # Store metrics for verification
                if value is not None:
                    key = (metric_name, tuple(sorted(labels.items())))
                    self._metrics[key] = value

        parent = MockParentCollector()
        return LicenseCollector(parent=parent)  # type: ignore[arg-type]

    async def test_collect_co_termination_licenses(self, license_collector, mock_api_builder):
        """Test collection of co-termination licensing model metrics."""
        org_id = "123"
        org_name = "Co-Term Org"

        # Create co-termination licensing overview response
        overview_response = {
            "status": "OK",
            "expirationDate": "Mar 13, 2027 UTC",
            "licensedDeviceCounts": {"MS": 50, "MR": 100, "MX": 10, "MV": 5, "MT": 20},
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationLicensesOverview", overview_response
        ).build()
        license_collector.api = api

        # Run collection
        await license_collector.collect(org_id, org_name)

        # Verify API was called
        assert api.organizations.getOrganizationLicensesOverview.called
        assert api.organizations.getOrganizationLicensesOverview.call_args[0][0] == org_id

        # Verify metrics were set correctly
        parent = license_collector.parent

        # Check license total metrics for each device type
        expected_counts = [("MS", 50), ("MR", 100), ("MX", 10), ("MV", 5), ("MT", 20)]
        for device_type, count in expected_counts:
            key = (
                "_licenses_total",
                (
                    ("license_type", device_type),
                    ("org_id", org_id),
                    ("org_name", org_name),
                    ("status", "OK"),
                ),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

        # Since expiration is in 2027, no licenses should be expiring
        for device_type, _ in expected_counts:
            key = (
                "_licenses_expiring",
                (("license_type", device_type), ("org_id", org_id), ("org_name", org_name)),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == 0

    async def test_collect_co_termination_licenses_expiring_soon(
        self, license_collector, mock_api_builder
    ):
        """Test co-termination licenses expiring within 30 days."""
        org_id = "456"
        org_name = "Expiring Co-Term Org"

        # Create expiration date 20 days from now
        expiring_date = datetime.now(UTC) + timedelta(days=20)
        date_str = expiring_date.strftime("%b %d, %Y UTC")

        overview_response = {
            "status": "OK",
            "expirationDate": date_str,
            "licensedDeviceCounts": {"MS": 30, "MR": 60},
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationLicensesOverview", overview_response
        ).build()
        license_collector.api = api

        # Run collection
        await license_collector.collect(org_id, org_name)

        parent = license_collector.parent

        # All licenses should be marked as expiring
        for device_type, count in [("MS", 30), ("MR", 60)]:
            key = (
                "_licenses_expiring",
                (("license_type", device_type), ("org_id", org_id), ("org_name", org_name)),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

    async def test_collect_per_device_licenses(self, license_collector, mock_api_builder):
        """Test collection of per-device licensing model metrics."""
        org_id = "789"
        org_name = "Per-Device Org"

        # Overview response without licensedDeviceCounts indicates per-device model
        overview_response = {
            "status": "OK"
            # No licensedDeviceCounts field
        }

        # Create per-device licenses response
        licenses_response = [
            {"licenseType": "ENT", "state": "active", "expirationDate": "2027-03-13T00:00:00Z"},
            {"licenseType": "ENT", "state": "active", "expirationDate": "2027-03-13T00:00:00Z"},
            {"licenseType": "ENT", "state": "inactive", "expirationDate": "2024-01-01T00:00:00Z"},
            {"licenseType": "ADV-SEC", "state": "active", "expirationDate": "2027-06-01T00:00:00Z"},
            {
                "licenseType": "ADV-SEC",
                "state": "active",
                "expirationDate": (datetime.now(UTC) + timedelta(days=15)).isoformat(),
            },
            {
                "licenseType": "LIC-MR-ADV",
                "state": "active",
                "expirationDate": "2028-01-01T00:00:00Z",
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_custom_response(
                "getOrganizationLicensesOverview", overview_response
            )
            .with_custom_response("getOrganizationLicenses", licenses_response)
            .build()
        )
        license_collector.api = api

        # Run collection
        await license_collector.collect(org_id, org_name)

        # Verify both APIs were called
        assert api.organizations.getOrganizationLicensesOverview.called
        assert api.organizations.getOrganizationLicenses.called
        assert api.organizations.getOrganizationLicenses.call_args[1]["total_pages"] == "all"

        parent = license_collector.parent

        # Check license total metrics
        expected_totals = [
            ("ENT", "active", 2),
            ("ENT", "inactive", 1),
            ("ADV-SEC", "active", 2),
            ("LIC-MR-ADV", "active", 1),
        ]
        for license_type, status, count in expected_totals:
            key = (
                "_licenses_total",
                (
                    ("license_type", license_type),
                    ("org_id", org_id),
                    ("org_name", org_name),
                    ("status", status),
                ),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

        # Check expiring licenses (only ADV-SEC has one expiring within 30 days)
        expiring_checks = [
            ("ENT", 0),
            ("ADV-SEC", 1),  # One expiring in 15 days
            ("LIC-MR-ADV", 0),
        ]
        for license_type, expected_expiring in expiring_checks:
            key = (
                "_licenses_expiring",
                (("license_type", license_type), ("org_id", org_id), ("org_name", org_name)),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == expected_expiring

    async def test_collect_with_empty_licenses(self, license_collector, mock_api_builder):
        """Test handling of empty license list."""
        org_id = "111"
        org_name = "No Licenses Org"

        overview_response = {"status": "OK"}
        licenses_response = []

        # Configure mock API
        api = (
            mock_api_builder.with_custom_response(
                "getOrganizationLicensesOverview", overview_response
            )
            .with_custom_response("getOrganizationLicenses", licenses_response)
            .build()
        )
        license_collector.api = api

        # Run collection - should handle gracefully
        await license_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = license_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_404_error(self, license_collector, mock_api_builder):
        """Test handling of 404 error (no licensing info)."""
        org_id = "222"
        org_name = "No License API Org"

        # Configure mock API with 404 error
        api = mock_api_builder.with_error(
            "getOrganizationLicensesOverview", Exception("404 Not Found")
        ).build()
        license_collector.api = api

        # Run collection - should handle 404 gracefully
        await license_collector.collect(org_id, org_name)

        # Verify no metrics were set and no exception raised
        parent = license_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_api_error(self, license_collector, mock_api_builder):
        """Test handling of general API errors."""
        org_id = "333"
        org_name = "API Error Org"

        # Configure mock API with error
        api = mock_api_builder.with_error(
            "getOrganizationLicensesOverview", Exception("Connection timeout")
        ).build()
        license_collector.api = api

        # Run collection - should handle error gracefully
        await license_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = license_collector.parent
        assert len(parent._metrics) == 0

    async def test_parse_meraki_date_formats(self, license_collector):
        """Test parsing of various Meraki date formats."""
        # Test ISO format
        iso_date = "2027-03-13T00:00:00Z"
        parsed = license_collector._parse_meraki_date(iso_date)
        assert parsed is not None
        assert parsed.year == 2027
        assert parsed.month == 3
        assert parsed.day == 13

        # Test human-readable format (short month)
        human_date = "Mar 13, 2027 UTC"
        parsed = license_collector._parse_meraki_date(human_date)
        assert parsed is not None
        assert parsed.year == 2027
        assert parsed.month == 3
        assert parsed.day == 13

        # Test human-readable format (long month)
        human_date_long = "March 13, 2027 UTC"
        parsed = license_collector._parse_meraki_date(human_date_long)
        assert parsed is not None
        assert parsed.year == 2027
        assert parsed.month == 3
        assert parsed.day == 13

        # Test GMT suffix
        gmt_date = "Mar 13, 2027 GMT"
        parsed = license_collector._parse_meraki_date(gmt_date)
        assert parsed is not None
        assert parsed.year == 2027

        # Test invalid format
        invalid_date = "not a date"
        parsed = license_collector._parse_meraki_date(invalid_date)
        assert parsed is None

        # Test empty string
        parsed = license_collector._parse_meraki_date("")
        assert parsed is None

    async def test_collect_co_termination_with_missing_fields(
        self, license_collector, mock_api_builder
    ):
        """Test co-termination model with missing fields."""
        org_id = "444"
        org_name = "Incomplete Co-Term Org"

        # Response missing licensedDeviceCounts
        overview_response = {
            "status": "OK",
            "expirationDate": "Mar 13, 2027 UTC",
            # Missing licensedDeviceCounts
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationLicensesOverview", overview_response
        ).build()
        license_collector.api = api

        # Run collection
        await license_collector.collect(org_id, org_name)

        # Should fall back to per-device model since no licensedDeviceCounts
        assert api.organizations.getOrganizationLicenses.called

    async def test_collect_per_device_with_unknown_fields(
        self, license_collector, mock_api_builder
    ):
        """Test per-device licenses with unknown/missing fields."""
        org_id = "555"
        org_name = "Unknown Fields Org"

        overview_response = {"status": "OK"}

        # Licenses with missing or unknown fields
        licenses_response = [
            {
                # Missing licenseType
                "state": "active",
                "expirationDate": "2027-03-13T00:00:00Z",
            },
            {
                "licenseType": "ENT",
                # Missing state
                "expirationDate": "2027-03-13T00:00:00Z",
            },
            {
                "licenseType": "ADV-SEC",
                "state": "active",
                # Missing expirationDate
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_custom_response(
                "getOrganizationLicensesOverview", overview_response
            )
            .with_custom_response("getOrganizationLicenses", licenses_response)
            .build()
        )
        license_collector.api = api

        # Run collection
        await license_collector.collect(org_id, org_name)

        parent = license_collector.parent

        # Check that missing fields default to "Unknown"
        key1 = (
            "_licenses_total",
            (
                ("license_type", "Unknown"),
                ("org_id", org_id),
                ("org_name", org_name),
                ("status", "active"),
            ),
        )
        assert key1 in parent._metrics
        assert parent._metrics[key1] == 1

        key2 = (
            "_licenses_total",
            (
                ("license_type", "ENT"),
                ("org_id", org_id),
                ("org_name", org_name),
                ("status", "Unknown"),
            ),
        )
        assert key2 in parent._metrics
        assert parent._metrics[key2] == 1

        # License without expiration date should not contribute to expiring count
        key3 = (
            "_licenses_expiring",
            (("license_type", "ADV-SEC"), ("org_id", org_id), ("org_name", org_name)),
        )
        assert key3 in parent._metrics
        assert parent._metrics[key3] == 0

    async def test_collect_co_termination_with_invalid_status(
        self, license_collector, mock_api_builder
    ):
        """Test co-termination model with non-OK status."""
        org_id = "666"
        org_name = "Invalid Status Org"

        overview_response = {
            "status": "EXPIRED",  # Not "OK"
            "expirationDate": (datetime.now(UTC) + timedelta(days=10)).strftime("%b %d, %Y UTC"),
            "licensedDeviceCounts": {"MS": 20, "MR": 40},
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationLicensesOverview", overview_response
        ).build()
        license_collector.api = api

        # Run collection
        await license_collector.collect(org_id, org_name)

        parent = license_collector.parent

        # Licenses should be recorded with EXPIRED status
        for device_type, count in [("MS", 20), ("MR", 40)]:
            key = (
                "_licenses_total",
                (
                    ("license_type", device_type),
                    ("org_id", org_id),
                    ("org_name", org_name),
                    ("status", "EXPIRED"),
                ),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

        # No licenses should be marked as expiring since status is not OK
        for device_type in ["MS", "MR"]:
            key = (
                "_licenses_expiring",
                (("license_type", device_type), ("org_id", org_id), ("org_name", org_name)),
            )
            assert key not in parent._metrics

    async def test_fetch_methods_parameters(self, license_collector, mock_api_builder):
        """Test that fetch methods pass correct parameters."""
        org_id = "test-org-777"

        # Configure mock API
        api = (
            mock_api_builder.with_custom_response(
                "getOrganizationLicensesOverview", {"status": "OK"}
            )
            .with_custom_response("getOrganizationLicenses", [])
            .build()
        )
        license_collector.api = api

        # Test _fetch_licenses_overview
        result1 = await license_collector._fetch_licenses_overview(org_id)
        assert api.organizations.getOrganizationLicensesOverview.called
        assert api.organizations.getOrganizationLicensesOverview.call_args[0][0] == org_id
        assert result1 == {"status": "OK"}

        # Test _fetch_licenses
        result2 = await license_collector._fetch_licenses(org_id)
        assert api.organizations.getOrganizationLicenses.called
        call_args = api.organizations.getOrganizationLicenses.call_args
        assert call_args[0][0] == org_id
        assert call_args[1]["total_pages"] == "all"
        assert result2 == []
