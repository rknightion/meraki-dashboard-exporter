"""Tests for API helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.core.api_helpers import APIHelper, create_api_helper
from meraki_dashboard_exporter.core.collector import MetricCollector


@pytest.fixture
def mock_collector():
    """Create a mock collector with necessary attributes."""
    collector = MagicMock(spec=MetricCollector)
    collector.api = MagicMock()

    # Create nested mock settings structure
    collector.settings = MagicMock()
    collector.settings.meraki = MagicMock()
    collector.settings.meraki.org_id = None
    collector.settings.api = MagicMock()
    collector.settings.api.batch_size = 10

    collector._track_api_call = MagicMock()
    return collector


@pytest.fixture
def api_helper(mock_collector):
    """Create APIHelper instance."""
    return APIHelper(mock_collector)


class TestAPIHelper:
    """Test APIHelper functionality."""

    def test_init(self, api_helper, mock_collector):
        """Test APIHelper initialization."""
        assert api_helper.collector == mock_collector
        assert api_helper.api == mock_collector.api
        assert api_helper.settings == mock_collector.settings

    async def test_get_organizations_all(self, api_helper, mock_collector):
        """Test fetching all organizations."""
        mock_orgs = [
            {"id": "123", "name": "Org 1"},
            {"id": "456", "name": "Org 2"},
        ]
        mock_collector.api.organizations.getOrganizations.return_value = mock_orgs

        result = await api_helper.get_organizations()

        assert result == mock_orgs
        mock_collector._track_api_call.assert_called_once_with("getOrganizations")
        mock_collector.api.organizations.getOrganizations.assert_called_once()

    async def test_get_organizations_configured_org(self, api_helper, mock_collector):
        """Test fetching single configured organization."""
        mock_collector.settings.meraki.org_id = "123"
        mock_org = {"id": "123", "name": "Configured Org"}
        mock_collector.api.organizations.getOrganization.return_value = mock_org

        result = await api_helper.get_organizations()

        assert result == [mock_org]
        mock_collector._track_api_call.assert_called_once_with("getOrganization")
        mock_collector.api.organizations.getOrganization.assert_called_once_with("123")

    async def test_get_organizations_error_handling(self, api_helper, mock_collector):
        """Test error handling in get_organizations."""
        mock_collector.api.organizations.getOrganizations.side_effect = Exception("API Error")

        # Should not raise due to error handling decorator
        result = await api_helper.get_organizations()

        # Result should be None or empty due to error
        assert result is None or result == []

    async def test_get_organization_networks_basic(self, api_helper, mock_collector):
        """Test fetching networks for an organization."""
        mock_networks = [
            {"id": "N_123", "name": "Network 1", "productTypes": ["wireless", "switch"]},
            {"id": "N_456", "name": "Network 2", "productTypes": ["appliance"]},
        ]
        mock_collector.api.organizations.getOrganizationNetworks.return_value = mock_networks

        result = await api_helper.get_organization_networks("123")

        assert result == mock_networks
        mock_collector._track_api_call.assert_called_once_with("getOrganizationNetworks")
        mock_collector.api.organizations.getOrganizationNetworks.assert_called_once_with(
            "123", total_pages="all"
        )

    async def test_get_organization_networks_with_filter(self, api_helper, mock_collector):
        """Test fetching networks with product type filtering."""
        mock_networks = [
            {"id": "N_123", "name": "Network 1", "productTypes": ["wireless", "switch"]},
            {"id": "N_456", "name": "Network 2", "productTypes": ["appliance"]},
            {"id": "N_789", "name": "Network 3", "productTypes": ["wireless"]},
        ]
        mock_collector.api.organizations.getOrganizationNetworks.return_value = mock_networks

        # Filter for wireless networks
        result = await api_helper.get_organization_networks("123", product_types=["wireless"])

        assert len(result) == 2
        assert all("wireless" in n["productTypes"] for n in result)
        assert result[0]["id"] == "N_123"
        assert result[1]["id"] == "N_789"

    async def test_get_organization_networks_empty_result(self, api_helper, mock_collector):
        """Test handling empty network list."""
        mock_collector.api.organizations.getOrganizationNetworks.return_value = []

        result = await api_helper.get_organization_networks("123")

        assert result == []

    async def test_get_organization_devices_basic(self, api_helper, mock_collector):
        """Test fetching devices for an organization."""
        mock_devices = [
            {"serial": "Q2XX-XXXX-XXXX", "model": "MR36", "productType": "wireless"},
            {"serial": "Q2YY-YYYY-YYYY", "model": "MS225", "productType": "switch"},
        ]
        mock_collector.api.organizations.getOrganizationDevices.return_value = mock_devices

        result = await api_helper.get_organization_devices("123")

        assert result == mock_devices
        mock_collector._track_api_call.assert_called_once_with("getOrganizationDevices")
        mock_collector.api.organizations.getOrganizationDevices.assert_called_once_with(
            "123", total_pages="all"
        )

    async def test_get_organization_devices_with_product_filter(self, api_helper, mock_collector):
        """Test fetching devices with product type filtering."""
        mock_devices = [
            {"serial": "Q2XX-XXXX-XXXX", "model": "MR36", "productType": "wireless"},
            {"serial": "Q2YY-YYYY-YYYY", "model": "MS225", "productType": "switch"},
        ]
        mock_collector.api.organizations.getOrganizationDevices.return_value = mock_devices

        await api_helper.get_organization_devices("123", product_types=["wireless"])

        mock_collector.api.organizations.getOrganizationDevices.assert_called_once_with(
            "123", total_pages="all", productTypes=["wireless"]
        )

    async def test_get_organization_devices_with_model_filter(self, api_helper, mock_collector):
        """Test fetching devices with model filtering."""
        mock_devices = [
            {"serial": "Q2XX-XXXX-XXXX", "model": "MR36", "productType": "wireless"},
            {"serial": "Q2YY-YYYY-YYYY", "model": "MS225", "productType": "switch"},
            {"serial": "Q2ZZ-ZZZZ-ZZZZ", "model": "MR46", "productType": "wireless"},
        ]
        mock_collector.api.organizations.getOrganizationDevices.return_value = mock_devices

        result = await api_helper.get_organization_devices("123", models=["MR"])

        assert len(result) == 2
        assert all(d["model"].startswith("MR") for d in result)

    async def test_get_organization_devices_combined_filters(self, api_helper, mock_collector):
        """Test fetching devices with both product type and model filtering."""
        mock_devices = [
            {"serial": "Q2XX-XXXX-XXXX", "model": "MR36", "productType": "wireless"},
            {"serial": "Q2YY-YYYY-YYYY", "model": "MS225", "productType": "switch"},
            {"serial": "Q2ZZ-ZZZZ-ZZZZ", "model": "MX64", "productType": "appliance"},
        ]
        # API returns only wireless devices due to product type filter
        mock_collector.api.organizations.getOrganizationDevices.return_value = [mock_devices[0]]

        result = await api_helper.get_organization_devices(
            "123", product_types=["wireless"], models=["MR"]
        )

        assert len(result) == 1
        assert result[0]["model"] == "MR36"

    async def test_process_in_batches_basic(self, api_helper):
        """Test basic batch processing."""
        items = list(range(25))  # 25 items with batch size 10 = 3 batches

        async def process_item(item: int) -> int:
            await asyncio.sleep(0.01)  # Simulate processing
            return item * 2

        results = await api_helper.process_in_batches(
            items, process_item, batch_size=10, description="numbers"
        )

        assert len(results) == 25
        assert results == [i * 2 for i in range(25)]

    async def test_process_in_batches_with_errors(self, api_helper):
        """Test batch processing with some items failing."""
        items = list(range(10))

        async def process_item(item: int) -> int:
            if item % 3 == 0:  # Fail for multiples of 3
                raise ValueError(f"Failed on {item}")
            return item * 2

        results = await api_helper.process_in_batches(
            items, process_item, batch_size=5, description="numbers"
        )

        # Should have 6 successful results (1,2,4,5,7,8)
        assert len(results) == 6
        assert 0 not in results  # 0 failed
        assert 2 in results  # 1 * 2
        assert 6 not in results  # 3 failed
        assert 8 in results  # 4 * 2

    async def test_process_in_batches_empty_list(self, api_helper):
        """Test batch processing with empty list."""
        results = await api_helper.process_in_batches(
            [],
            lambda x: x,
            description="empty",  # type: ignore[arg-type, return-value]
        )

        assert results == []

    async def test_process_in_batches_uses_default_batch_size(self, api_helper, mock_collector):
        """Test that default batch size from settings is used."""
        items = list(range(25))
        mock_collector.settings.api.batch_size = 7  # Non-standard batch size

        processed_count = 0

        async def count_items(item: int) -> int:
            nonlocal processed_count
            processed_count += 1
            return item

        results = await api_helper.process_in_batches(items, count_items, description="test")

        assert len(results) == 25
        assert processed_count == 25

    async def test_get_time_based_data_basic(self, api_helper, mock_collector):
        """Test fetching time-based data."""
        mock_data = [
            {"ts": "2024-01-15T10:00:00Z", "value": 50},
            {"ts": "2024-01-15T10:05:00Z", "value": 60},
        ]
        mock_api_method = MagicMock(return_value=mock_data)

        result = await api_helper.get_time_based_data(
            mock_api_method, "getTimeSeries", timespan=300
        )

        assert result == mock_data
        mock_collector._track_api_call.assert_called_once_with("getTimeSeries")
        mock_api_method.assert_called_once_with(timespan=300)

    async def test_get_time_based_data_with_interval(self, api_helper, mock_collector):
        """Test fetching time-based data with interval."""
        mock_data = {"average": 75.5}
        mock_api_method = MagicMock(return_value=mock_data)

        result = await api_helper.get_time_based_data(
            mock_api_method, "getAggregatedData", timespan=3600, interval=300
        )

        assert result == mock_data
        mock_api_method.assert_called_once_with(timespan=3600, interval=300)

    async def test_get_time_based_data_wrapped_response(self, api_helper, mock_collector):
        """Test handling wrapped response format."""
        wrapped_data = {
            "items": [
                {"ts": "2024-01-15T10:00:00Z", "value": 50},
                {"ts": "2024-01-15T10:05:00Z", "value": 60},
            ],
            "meta": {"page": 1},
        }
        mock_api_method = MagicMock(return_value=wrapped_data)

        result = await api_helper.get_time_based_data(
            mock_api_method, "getWrappedData", timespan=300
        )

        # Should unwrap and return just the items
        assert result == wrapped_data["items"]

    async def test_get_time_based_data_with_kwargs(self, api_helper, mock_collector):
        """Test passing additional kwargs to API method."""
        mock_data: list[Any] = []
        mock_api_method = MagicMock(return_value=mock_data)

        result = await api_helper.get_time_based_data(
            mock_api_method,
            "getFilteredData",
            timespan=300,
            network_id="N_123",
            device_serial="Q2XX-XXXX-XXXX",
        )

        assert result == mock_data
        mock_api_method.assert_called_once_with(
            timespan=300, network_id="N_123", device_serial="Q2XX-XXXX-XXXX"
        )

    async def test_get_time_based_data_error_handling(self, api_helper, mock_collector):
        """Test error handling in time-based data fetching."""
        mock_api_method = MagicMock(side_effect=Exception("API Error"))

        # Should not raise due to error handling decorator
        result = await api_helper.get_time_based_data(
            mock_api_method, "getFailingData", timespan=300
        )

        assert result is None or result == []

    def test_create_api_helper(self, mock_collector):
        """Test create_api_helper factory function."""
        helper = create_api_helper(mock_collector)

        assert isinstance(helper, APIHelper)
        assert helper.collector == mock_collector
        assert helper.api == mock_collector.api
        assert helper.settings == mock_collector.settings

    async def test_concurrent_api_calls(self, api_helper, mock_collector):
        """Test that multiple API calls can be made concurrently."""
        # Setup different mock responses
        mock_collector.api.organizations.getOrganizations.return_value = [{"id": "123"}]
        mock_collector.api.organizations.getOrganizationNetworks.return_value = [{"id": "N_123"}]
        mock_collector.api.organizations.getOrganizationDevices.return_value = [{"serial": "Q2XX"}]

        # Make concurrent calls
        results = await asyncio.gather(
            api_helper.get_organizations(),
            api_helper.get_organization_networks("123"),
            api_helper.get_organization_devices("123"),
        )

        assert len(results) == 3
        assert results[0] == [{"id": "123"}]
        assert results[1] == [{"id": "N_123"}]
        assert results[2] == [{"serial": "Q2XX"}]

    async def test_process_in_batches_respects_order(self, api_helper):
        """Test that batch processing maintains order of results."""
        items = list(range(20))

        async def process_with_delay(item: int) -> int:
            # Add varying delays to test order preservation
            await asyncio.sleep(0.01 * (20 - item))
            return item * 2

        results = await api_helper.process_in_batches(
            items, process_with_delay, batch_size=5, description="ordered"
        )

        # Results should maintain original order
        assert results == [i * 2 for i in range(20)]
