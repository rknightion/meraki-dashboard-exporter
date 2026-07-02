"""Tests for the APIUsageCollector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.api_usage import APIUsageCollector

if TYPE_CHECKING:
    pass


class TestAPIUsageCollector:
    """Test APIUsageCollector functionality."""

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
    def api_usage_collector(
        self, mock_api_builder, settings, isolated_registry
    ) -> APIUsageCollector:
        """Create APIUsageCollector instance with mocked dependencies."""

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
        return APIUsageCollector(parent=parent)  # type: ignore[arg-type]

    async def test_collect_api_usage_metrics(self, api_usage_collector, mock_api_builder):
        """Test collection of API usage metrics with various status codes."""
        # Set up test data
        org_id = "123"
        org_name = "Test Org"

        # Create API response with various status codes
        api_response = {
            "responseCodeCounts": {
                "200": 1500,
                "201": 250,
                "202": 50,
                "204": 100,
                "400": 25,
                "401": 5,
                "403": 3,
                "404": 75,
                "429": 10,
                "500": 2,
                "502": 1,
                "503": 0,  # Should be ignored (zero count)
                "504": 0,  # Should be ignored (zero count)
            }
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", api_response
        ).build()
        api_usage_collector.api = api

        # Run collection
        await api_usage_collector.collect(org_id, org_name)

        # Verify API was called
        assert api.organizations.getOrganizationApiRequestsOverview.called
        assert api.organizations.getOrganizationApiRequestsOverview.call_args[0][0] == org_id
        assert api.organizations.getOrganizationApiRequestsOverview.call_args[1]["timespan"] == 3600

        # Verify metrics were set correctly
        parent = api_usage_collector.parent

        # Check individual status code metrics, including zero-count codes
        # (F-096: zero counts must be emitted, not skipped, so the gauge
        # doesn't freeze at the last non-zero value).
        expected_status_metrics = [
            ("200", 1500),
            ("201", 250),
            ("202", 50),
            ("204", 100),
            ("400", 25),
            ("401", 5),
            ("403", 3),
            ("404", 75),
            ("429", 10),
            ("500", 2),
            ("502", 1),
            ("503", 0),
            ("504", 0),
        ]

        for status_code, count in expected_status_metrics:
            key = (
                "_api_requests_by_status",
                (("org_id", org_id), ("status_code", status_code)),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == count

        # Check total requests metric (zero-count codes contribute nothing)
        expected_total = sum(count for _, count in expected_status_metrics)
        total_key = ("_api_requests_total", (("org_id", org_id),))
        assert total_key in parent._metrics
        assert parent._metrics[total_key] == expected_total

        # Verify API call was tracked exactly once (by the @log_api_call decorator);
        # the redundant manual _track_api_call was removed (F-014, no double count).
        assert parent._api_calls.get("getOrganizationApiRequestsOverview") == 1

    async def test_collect_api_usage_with_all_zeros(self, api_usage_collector, mock_api_builder):
        """Test API usage metrics when all status codes have zero count."""
        # Set up test data
        org_id = "456"
        org_name = "Zero Usage Org"

        # Create API response with all zeros
        api_response = {
            "responseCodeCounts": {
                "200": 0,
                "201": 0,
                "400": 0,
                "401": 0,
                "404": 0,
                "429": 0,
                "500": 0,
            }
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", api_response
        ).build()
        api_usage_collector.api = api

        # Run collection
        await api_usage_collector.collect(org_id, org_name)

        # Verify total is set to 0
        parent = api_usage_collector.parent
        total_key = ("_api_requests_total", (("org_id", org_id),))
        assert total_key in parent._metrics
        assert parent._metrics[total_key] == 0

        # F-096: zero-count status codes present in the response must still
        # be emitted (as 0), not skipped.
        for status_code in api_response["responseCodeCounts"]:
            key = (
                "_api_requests_by_status",
                (("org_id", org_id), ("status_code", status_code)),
            )
            assert key in parent._metrics
            assert parent._metrics[key] == 0

    async def test_collect_api_usage_with_missing_response_codes(
        self, api_usage_collector, mock_api_builder
    ):
        """Test API usage metrics when responseCodeCounts is missing."""
        # Set up test data
        org_id = "789"
        org_name = "Malformed Org"

        # Create API response without responseCodeCounts
        api_response = {"someOtherField": "value"}

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", api_response
        ).build()
        api_usage_collector.api = api

        # Run collection - should not raise exception
        await api_usage_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = api_usage_collector.parent
        assert not hasattr(parent, "_metrics") or len(parent._metrics) == 0

    async def test_collect_api_usage_with_none_response(
        self, api_usage_collector, mock_api_builder
    ):
        """Test API usage metrics when API returns None."""
        # Set up test data
        org_id = "999"
        org_name = "None Response Org"

        # Configure mock API to return None
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", None
        ).build()
        api_usage_collector.api = api

        # Run collection - should not raise exception
        await api_usage_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = api_usage_collector.parent
        assert not hasattr(parent, "_metrics") or len(parent._metrics) == 0

    async def test_collect_api_usage_with_api_error(self, api_usage_collector, mock_api_builder):
        """Test API usage metrics handle API errors gracefully."""
        # Set up test data
        org_id = "111"
        org_name = "Error Org"

        # Configure mock API with error
        api = mock_api_builder.with_error(
            "getOrganizationApiRequestsOverview", Exception("API Error")
        ).build()
        api_usage_collector.api = api

        # Run collection - should not raise exception
        await api_usage_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = api_usage_collector.parent
        assert not hasattr(parent, "_metrics") or len(parent._metrics) == 0

    async def test_collect_api_usage_with_non_dict_response(
        self, api_usage_collector, mock_api_builder
    ):
        """Test API usage metrics when API returns non-dict response."""
        # Set up test data
        org_id = "222"
        org_name = "List Response Org"

        # Configure mock API to return a list instead of dict
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", ["not", "a", "dict"]
        ).build()
        api_usage_collector.api = api

        # Run collection - should not raise exception
        await api_usage_collector.collect(org_id, org_name)

        # Verify no metrics were set
        parent = api_usage_collector.parent
        assert not hasattr(parent, "_metrics") or len(parent._metrics) == 0

    async def test_collect_api_usage_with_empty_response_codes(
        self, api_usage_collector, mock_api_builder
    ):
        """Test API usage metrics when responseCodeCounts is empty dict."""
        # Set up test data
        org_id = "333"
        org_name = "Empty Codes Org"

        # Create API response with empty responseCodeCounts
        api_response = {"responseCodeCounts": {}}

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", api_response
        ).build()
        api_usage_collector.api = api

        # Run collection
        await api_usage_collector.collect(org_id, org_name)

        # Verify total is set to 0
        parent = api_usage_collector.parent
        total_key = ("_api_requests_total", (("org_id", org_id),))
        assert total_key in parent._metrics
        assert parent._metrics[total_key] == 0

    async def test_collect_api_usage_status_code_zeroed_when_no_longer_present(
        self, api_usage_collector, mock_api_builder
    ):
        """F-096: a status code that drops out of the response must be zeroed.

        Once a status code has been observed for an org, it must keep being
        emitted (as 0) on subsequent cycles where it's absent or zero, so the
        gauge doesn't freeze at its last non-zero value.
        """
        org_id = "555"
        org_name = "Flapping Status Org"

        first_response = {"responseCodeCounts": {"200": 100, "429": 50}}
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", first_response
        ).build()
        api_usage_collector.api = api

        await api_usage_collector.collect(org_id, org_name)

        parent = api_usage_collector.parent
        status_429_key = (
            "_api_requests_by_status",
            (("org_id", org_id), ("status_code", "429")),
        )
        assert parent._metrics[status_429_key] == 50

        # Second cycle: 429 has completely disappeared from the response.
        second_response = {"responseCodeCounts": {"200": 120}}
        api2 = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", second_response
        ).build()
        api_usage_collector.api = api2

        await api_usage_collector.collect(org_id, org_name)

        # 429 must now read 0, not the stale 50 from the first cycle.
        assert parent._metrics[status_429_key] == 0
        status_200_key = (
            "_api_requests_by_status",
            (("org_id", org_id), ("status_code", "200")),
        )
        assert parent._metrics[status_200_key] == 120

    async def test_collect_api_usage_with_non_numeric_counts(
        self, api_usage_collector, mock_api_builder
    ):
        """F-099: a single non-numeric count must not abort collection.

        The valid entries must still be processed and the total-requests
        gauge must still be written (summing only the valid counts).
        """
        # Set up test data
        org_id = "444"
        org_name = "Bad Count Org"

        # Create API response with non-numeric counts
        api_response = {
            "responseCodeCounts": {
                "200": "not a number",
                "201": None,
                "400": 100,  # One valid count
            }
        }

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", api_response
        ).build()
        api_usage_collector.api = api

        # Run collection - should handle gracefully, not raise, and not
        # abort before writing the total.
        await api_usage_collector.collect(org_id, org_name)

        parent = api_usage_collector.parent

        # The valid numeric count must be set.
        status_key = (
            "_api_requests_by_status",
            (("org_id", org_id), ("status_code", "400")),
        )
        assert status_key in parent._metrics
        assert parent._metrics[status_key] == 100

        # The non-numeric entries must be skipped, not emitted.
        for bad_code in ("200", "201"):
            bad_key = (
                "_api_requests_by_status",
                (("org_id", org_id), ("status_code", bad_code)),
            )
            assert bad_key not in parent._metrics

        # The total-requests gauge must still be written, summing only the
        # valid numeric counts (the loop must not abort mid-way).
        total_key = ("_api_requests_total", (("org_id", org_id),))
        assert total_key in parent._metrics
        assert parent._metrics[total_key] == 100

    async def test_fetch_api_requests_overview_parameters(
        self, api_usage_collector, mock_api_builder
    ):
        """Test that _fetch_api_requests_overview passes correct parameters."""
        # Set up test data
        org_id = "test-org-123"

        # Configure mock API
        api = mock_api_builder.with_custom_response(
            "getOrganizationApiRequestsOverview", {"responseCodeCounts": {}}
        ).build()
        api_usage_collector.api = api

        # Call the method directly
        result = await api_usage_collector._fetch_api_requests_overview(org_id)

        # Verify API was called with correct parameters
        assert api.organizations.getOrganizationApiRequestsOverview.called
        call_args = api.organizations.getOrganizationApiRequestsOverview.call_args
        assert call_args[0][0] == org_id
        assert call_args[1]["timespan"] == 3600
        assert result == {"responseCodeCounts": {}}
