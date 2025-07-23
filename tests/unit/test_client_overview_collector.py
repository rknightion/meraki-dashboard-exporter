"""Tests for the ClientOverviewCollector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.client_overview import (
    ClientOverviewCollector,
)

if TYPE_CHECKING:
    pass


class TestClientOverviewCollector:
    """Test ClientOverviewCollector functionality."""

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
    def client_overview_collector(
        self, mock_api_builder, settings, isolated_registry
    ) -> ClientOverviewCollector:
        """Create ClientOverviewCollector instance with mocked dependencies."""

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
        return ClientOverviewCollector(parent=parent)  # type: ignore[arg-type]

    async def test_collect_client_overview_metrics(
        self, client_overview_collector, mock_api_builder
    ):
        """Test collection of client overview metrics with typical data."""
        # Set up test data
        org_id = "123"
        org_name = "Test Org"

        # Create API response with client and usage data
        api_response = {
            "counts": {"total": 150, "wireless": 120, "wired": 30},
            "usage": {
                "overall": {
                    "total": 1048576,  # 1GB in KB
                    "downstream": 786432,  # 768MB in KB
                    "upstream": 262144,  # 256MB in KB
                }
            },
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", api_response
        ).build()
        client_overview_collector.api = api

        # Run collection
        await client_overview_collector.collect(org_id, org_name)

        # Verify API was called with correct parameters
        assert api.organizations.getOrganizationClientsOverview.called
        assert api.organizations.getOrganizationClientsOverview.call_args[0][0] == org_id
        assert api.organizations.getOrganizationClientsOverview.call_args[1]["timespan"] == 3600

        # Verify metrics were set correctly
        parent = client_overview_collector.parent

        # Check client count metric
        client_key = ("_clients_total", (("org_id", org_id), ("org_name", org_name)))
        assert client_key in parent._metrics
        assert parent._metrics[client_key] == 150

        # Check usage metrics
        total_usage_key = ("_usage_total_kb", (("org_id", org_id), ("org_name", org_name)))
        assert total_usage_key in parent._metrics
        assert parent._metrics[total_usage_key] == 1048576

        downstream_key = ("_usage_downstream_kb", (("org_id", org_id), ("org_name", org_name)))
        assert downstream_key in parent._metrics
        assert parent._metrics[downstream_key] == 786432

        upstream_key = ("_usage_upstream_kb", (("org_id", org_id), ("org_name", org_name)))
        assert upstream_key in parent._metrics
        assert parent._metrics[upstream_key] == 262144

        # Verify API call was tracked
        assert parent._api_calls.get("getOrganizationClientsOverview") == 2

    async def test_collect_with_zero_values_and_caching(
        self, client_overview_collector, mock_api_builder
    ):
        """Test that collector caches non-zero values and uses them when API returns all zeros."""
        org_id = "456"
        org_name = "Cache Test Org"

        # First collection with non-zero values
        good_response = {
            "counts": {"total": 100},
            "usage": {"overall": {"total": 500000, "downstream": 300000, "upstream": 200000}},
        }

        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", good_response
        ).build()
        client_overview_collector.api = api

        # First collection - should cache values
        await client_overview_collector.collect(org_id, org_name)

        # Verify cached values
        assert org_id in client_overview_collector._last_non_zero_values
        cached = client_overview_collector._last_non_zero_values[org_id]
        assert cached["total_clients"] == 100
        assert cached["total_kb"] == 500000
        assert cached["downstream_kb"] == 300000
        assert cached["upstream_kb"] == 200000

        # Second collection with all zeros
        zero_response = {
            "counts": {"total": 0},
            "usage": {"overall": {"total": 0, "downstream": 0, "upstream": 0}},
        }

        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", zero_response
        ).build()
        client_overview_collector.api = api

        # Clear previous metrics for clean test
        parent = client_overview_collector.parent
        parent._metrics.clear()

        # Second collection - should use cached values
        await client_overview_collector.collect(org_id, org_name)

        # Verify cached values were used
        client_key = ("_clients_total", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[client_key] == 100  # Cached value

        total_usage_key = ("_usage_total_kb", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[total_usage_key] == 500000  # Cached value

        downstream_key = ("_usage_downstream_kb", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[downstream_key] == 300000  # Cached value

        upstream_key = ("_usage_upstream_kb", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[upstream_key] == 200000  # Cached value

    async def test_collect_with_missing_fields(self, client_overview_collector, mock_api_builder):
        """Test handling of response with missing fields."""
        org_id = "789"
        org_name = "Partial Data Org"

        # Response with missing usage data
        api_response = {
            "counts": {"total": 50}
            # Missing usage field entirely
        }

        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", api_response
        ).build()
        client_overview_collector.api = api

        # Run collection - should handle gracefully
        await client_overview_collector.collect(org_id, org_name)

        parent = client_overview_collector.parent

        # Client count should be set
        client_key = ("_clients_total", (("org_id", org_id), ("org_name", org_name)))
        assert client_key in parent._metrics
        assert parent._metrics[client_key] == 50

        # Usage metrics should be set to 0
        total_usage_key = ("_usage_total_kb", (("org_id", org_id), ("org_name", org_name)))
        assert total_usage_key in parent._metrics
        assert parent._metrics[total_usage_key] == 0

    async def test_collect_with_empty_response(self, client_overview_collector, mock_api_builder):
        """Test handling of empty API response."""
        org_id = "111"
        org_name = "Empty Response Org"

        # Configure mock API to return empty dict
        api = mock_api_builder.with_custom_response("getOrganizationClientsOverview", {}).build()
        client_overview_collector.api = api

        # Run collection - should handle gracefully
        await client_overview_collector.collect(org_id, org_name)

        parent = client_overview_collector.parent

        # When response is empty (no client overview data), no metrics should be set
        # This is the actual behavior as shown in the code: it logs a warning but doesn't set metrics
        assert len(parent._metrics) == 0

    async def test_collect_with_none_response(self, client_overview_collector, mock_api_builder):
        """Test handling when API returns None."""
        org_id = "222"
        org_name = "None Response Org"

        # Configure mock API to return None
        api = mock_api_builder.with_custom_response("getOrganizationClientsOverview", None).build()
        client_overview_collector.api = api

        # Run collection - should handle gracefully
        await client_overview_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = client_overview_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_404_error(self, client_overview_collector, mock_api_builder):
        """Test handling of 404 error (endpoint not available)."""
        org_id = "333"
        org_name = "404 Error Org"

        # Configure mock API with 404 error
        api = mock_api_builder.with_error(
            "getOrganizationClientsOverview", Exception("404 Not Found")
        ).build()
        client_overview_collector.api = api

        # Run collection - should handle 404 gracefully
        await client_overview_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = client_overview_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_general_api_error(
        self, client_overview_collector, mock_api_builder
    ):
        """Test handling of general API errors."""
        org_id = "444"
        org_name = "API Error Org"

        # Configure mock API with general error
        api = mock_api_builder.with_error(
            "getOrganizationClientsOverview", Exception("Connection timeout")
        ).build()
        client_overview_collector.api = api

        # Run collection - should handle error gracefully
        await client_overview_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = client_overview_collector.parent
        assert len(parent._metrics) == 0

    async def test_collect_with_partial_usage_data(
        self, client_overview_collector, mock_api_builder
    ):
        """Test handling of response with partial usage data."""
        org_id = "555"
        org_name = "Partial Usage Org"

        # Response with incomplete usage data
        api_response = {
            "counts": {"total": 75},
            "usage": {
                "overall": {
                    "total": 100000
                    # Missing downstream and upstream
                }
            },
        }

        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", api_response
        ).build()
        client_overview_collector.api = api

        # Run collection
        await client_overview_collector.collect(org_id, org_name)

        parent = client_overview_collector.parent

        # Client count should be set
        client_key = ("_clients_total", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[client_key] == 75

        # Total usage should be set
        total_usage_key = ("_usage_total_kb", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[total_usage_key] == 100000

        # Downstream and upstream should default to 0
        downstream_key = ("_usage_downstream_kb", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[downstream_key] == 0

        upstream_key = ("_usage_upstream_kb", (("org_id", org_id), ("org_name", org_name)))
        assert parent._metrics[upstream_key] == 0

    async def test_caching_across_multiple_organizations(
        self, client_overview_collector, mock_api_builder
    ):
        """Test that caching works correctly for multiple organizations."""
        org1_id, org1_name = "org1", "Org 1"
        org2_id, org2_name = "org2", "Org 2"

        # First collection for both orgs with different values
        response1 = {
            "counts": {"total": 100},
            "usage": {"overall": {"total": 1000, "downstream": 600, "upstream": 400}},
        }
        response2 = {
            "counts": {"total": 200},
            "usage": {"overall": {"total": 2000, "downstream": 1200, "upstream": 800}},
        }

        # Collect for org1
        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", response1
        ).build()
        client_overview_collector.api = api
        await client_overview_collector.collect(org1_id, org1_name)

        # Collect for org2
        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", response2
        ).build()
        client_overview_collector.api = api
        await client_overview_collector.collect(org2_id, org2_name)

        # Verify both orgs have cached values
        assert org1_id in client_overview_collector._last_non_zero_values
        assert org2_id in client_overview_collector._last_non_zero_values

        # Verify cached values are correct for each org
        cached1 = client_overview_collector._last_non_zero_values[org1_id]
        assert cached1["total_clients"] == 100
        assert cached1["total_kb"] == 1000

        cached2 = client_overview_collector._last_non_zero_values[org2_id]
        assert cached2["total_clients"] == 200
        assert cached2["total_kb"] == 2000

    async def test_fetch_client_overview_parameters(
        self, client_overview_collector, mock_api_builder
    ):
        """Test that _fetch_client_overview passes correct parameters."""
        org_id = "test-org-666"

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationClientsOverview", {"counts": {"total": 10}}
        ).build()
        client_overview_collector.api = api

        # Call the method directly
        result = await client_overview_collector._fetch_client_overview(org_id)

        # Verify API was called with correct parameters
        assert api.organizations.getOrganizationClientsOverview.called
        call_args = api.organizations.getOrganizationClientsOverview.call_args
        assert call_args[0][0] == org_id
        assert call_args[1]["timespan"] == 3600
        assert result == {"counts": {"total": 10}}
