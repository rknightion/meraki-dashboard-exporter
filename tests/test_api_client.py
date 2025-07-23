"""Tests for the AsyncMerakiClient wrapper."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from meraki.exceptions import APIError
from pydantic import SecretStr

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock()

    # Create nested mock objects
    settings.meraki = MagicMock()
    settings.meraki.api_key = SecretStr("test-api-key")
    settings.meraki.api_base_url = "https://api.meraki.com/api/v1"

    settings.api = MagicMock()
    settings.api.concurrency_limit = 5
    settings.api.timeout = 30
    settings.api.max_retries = 3

    return settings


@pytest.fixture
def mock_dashboard_api() -> Mock:
    """Create mock DashboardAPI instance."""
    api = MagicMock()

    # Mock organization endpoints
    api.organizations.getOrganizations = MagicMock(return_value=[])
    api.organizations.getOrganization = MagicMock(return_value={})
    api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
    api.organizations.getOrganizationDevices = MagicMock(return_value=[])
    api.organizations.getOrganizationDevicesAvailabilities = MagicMock(return_value=[])
    api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
    api.organizations.getOrganizationApiRequests = MagicMock(return_value=[])

    # Mock device endpoints
    api.switch.getDeviceSwitchPortsStatuses = MagicMock(return_value=[])
    api.wireless.getDeviceWirelessStatus = MagicMock(return_value={})

    # Mock sensor endpoints
    api.sensor.getOrganizationSensorReadingsLatest = MagicMock(return_value=[])

    return api


class TestAsyncMerakiClientInitialization:
    """Test client initialization and configuration."""

    def test_init_with_settings(self, mock_settings: Settings) -> None:
        """Test client initialization with settings."""
        client = AsyncMerakiClient(mock_settings)

        assert client.settings == mock_settings
        assert client._api is None
        assert isinstance(client._semaphore, asyncio.Semaphore)
        assert isinstance(client._api_lock, asyncio.Lock)
        assert client._api_call_count == 0

    @patch("meraki_dashboard_exporter.api.client.meraki.DashboardAPI")
    def test_api_property_lazy_initialization(
        self,
        mock_dashboard_class: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test API client is created lazily on first access."""
        mock_dashboard_class.return_value = mock_dashboard_api

        client = AsyncMerakiClient(mock_settings)
        assert client._api is None

        # First access creates the API
        api = client.api
        assert api == mock_dashboard_api
        assert client._api == mock_dashboard_api

        # Verify initialization parameters
        mock_dashboard_class.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://api.meraki.com/api/v1",
            output_log=False,
            suppress_logging=False,
            inherit_logging_config=True,
            single_request_timeout=30,
            maximum_retries=3,
            action_batch_retry_wait_time=10,
            nginx_429_retry_wait_time=5,
            wait_on_rate_limit=True,
            retry_4xx_error=False,
            caller="merakidashboardexporter rknightion",
        )

    @patch("meraki_dashboard_exporter.api.client.meraki.DashboardAPI")
    def test_api_property_reuses_instance(
        self,
        mock_dashboard_class: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test API property reuses existing instance."""
        mock_dashboard_class.return_value = mock_dashboard_api

        client = AsyncMerakiClient(mock_settings)

        # Multiple accesses should return same instance
        api1 = client.api
        api2 = client.api

        assert api1 == api2
        assert mock_dashboard_class.call_count == 1


class TestOrganizationEndpoints:
    """Test organization-related API endpoints."""

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_organizations(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching organizations."""
        mock_orgs = [
            {"id": "123", "name": "Org 1"},
            {"id": "456", "name": "Org 2"},
        ]
        mock_to_thread.return_value = mock_orgs

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_organizations()

        assert result == mock_orgs
        mock_to_thread.assert_called_once_with(mock_dashboard_api.organizations.getOrganizations)

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_organization(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching a specific organization."""
        mock_org = {"id": "123", "name": "Test Org"}
        mock_to_thread.return_value = mock_org

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_organization("123")

        assert result == mock_org
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.organizations.getOrganization, "123"
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_networks(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching networks for an organization."""
        mock_networks = [
            {"id": "N_123", "name": "Network 1"},
            {"id": "N_456", "name": "Network 2"},
        ]
        mock_to_thread.return_value = mock_networks

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_networks("org123")

        assert result == mock_networks
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.organizations.getOrganizationNetworks,
            "org123",
            total_pages="all",
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_licenses(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching licenses for an organization."""
        mock_licenses = [
            {"licenseType": "ENT", "state": "active"},
            {"licenseType": "MX", "state": "expired"},
        ]
        mock_to_thread.return_value = mock_licenses

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_licenses("org123")

        assert result == mock_licenses
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.organizations.getOrganizationLicenses,
            "org123",
            total_pages="all",
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_api_requests(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching API request statistics."""
        mock_requests = [
            {"adminId": "admin1", "method": "GET", "host": "api.meraki.com"},
            {"adminId": "admin2", "method": "POST", "host": "api.meraki.com"},
        ]
        mock_to_thread.return_value = mock_requests

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_api_requests("org123")

        assert result == mock_requests
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.organizations.getOrganizationApiRequests,
            "org123",
            total_pages="all",
        )


class TestDeviceEndpoints:
    """Test device-related API endpoints."""

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_devices(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching devices for an organization."""
        mock_devices = [
            {"serial": "Q2XX-XXXX-XXXX", "model": "MR46", "name": "AP1"},
            {"serial": "Q2YY-YYYY-YYYY", "model": "MS120", "name": "Switch1"},
        ]
        mock_to_thread.return_value = mock_devices

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_devices("org123")

        assert result == mock_devices
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.organizations.getOrganizationDevices,
            "org123",
            total_pages="all",
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_device_availabilities(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching device availabilities."""
        mock_availabilities = [
            {"serial": "Q2XX-XXXX-XXXX", "availability": 99.9},
            {"serial": "Q2YY-YYYY-YYYY", "availability": 98.5},
        ]
        mock_to_thread.return_value = mock_availabilities

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_device_availabilities("org123")

        assert result == mock_availabilities
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.organizations.getOrganizationDevicesAvailabilities,
            "org123",
            total_pages="all",
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_switch_port_statuses(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching switch port statuses."""
        mock_ports = [
            {"portId": "1", "enabled": True, "status": "Connected"},
            {"portId": "2", "enabled": False, "status": "Disconnected"},
        ]
        mock_to_thread.return_value = mock_ports

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_switch_port_statuses("Q2XX-XXXX-XXXX")

        assert result == mock_ports
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.switch.getDeviceSwitchPortsStatuses, "Q2XX-XXXX-XXXX"
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_wireless_status(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching wireless device status."""
        mock_status = {
            "basicServiceSets": [
                {"ssidName": "Guest", "radioIndex": 0},
                {"ssidName": "Corporate", "radioIndex": 1},
            ]
        }
        mock_to_thread.return_value = mock_status

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_wireless_status("Q2XX-XXXX-XXXX")

        assert result == mock_status
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.wireless.getDeviceWirelessStatus, "Q2XX-XXXX-XXXX"
        )


class TestSensorEndpoints:
    """Test sensor-related API endpoints."""

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_sensor_readings_latest(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching latest sensor readings."""
        mock_readings = [
            {
                "serial": "Q2MT-XXXX-XXXX",
                "readings": [
                    {"metric": "temperature", "value": 22.5},
                    {"metric": "humidity", "value": 45.0},
                ],
            }
        ]
        mock_to_thread.return_value = mock_readings

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_sensor_readings_latest("org123")

        assert result == mock_readings
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.sensor.getOrganizationSensorReadingsLatest,
            "org123",
            total_pages="all",
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_sensor_readings_with_serials(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test fetching sensor readings filtered by serials."""
        mock_readings = [
            {
                "serial": "Q2MT-XXXX-XXXX",
                "readings": [{"metric": "temperature", "value": 22.5}],
            }
        ]
        mock_to_thread.return_value = mock_readings

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_sensor_readings_latest(
                "org123", serials=["Q2MT-XXXX-XXXX", "Q2MT-YYYY-YYYY"]
            )

        assert result == mock_readings
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.sensor.getOrganizationSensorReadingsLatest,
            "org123",
            total_pages="all",
            serials=["Q2MT-XXXX-XXXX", "Q2MT-YYYY-YYYY"],
        )


class TestConcurrencyControl:
    """Test concurrency limiting functionality."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_requests(
        self,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test that semaphore properly limits concurrent requests."""
        mock_settings.api.concurrency_limit = 2
        client = AsyncMerakiClient(mock_settings)

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0

        async def slow_operation(*args: Any, **kwargs: Any) -> str:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.1)
            concurrent_count -= 1
            return "done"

        with patch.object(client, "_api", mock_dashboard_api):
            with patch(
                "meraki_dashboard_exporter.api.client.asyncio.to_thread", side_effect=slow_operation
            ):
                # Launch multiple concurrent requests
                tasks = [
                    client.get_organizations(),
                    client.get_organizations(),
                    client.get_organizations(),
                    client.get_organizations(),
                ]

                await asyncio.gather(*tasks)

        # Should respect concurrency limit
        assert max_concurrent <= 2


class TestErrorHandling:
    """Test error handling with api_call_context."""

    @pytest.mark.asyncio
    async def test_api_call_context_success(
        self,
        mock_settings: Settings,
    ) -> None:
        """Test api_call_context with successful operation."""
        client = AsyncMerakiClient(mock_settings)

        async with client.api_call_context():
            # Should not raise
            result = "success"

        assert result == "success"

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.logger")
    async def test_api_call_context_rate_limit_error(
        self,
        mock_logger: Mock,
        mock_settings: Settings,
    ) -> None:
        """Test handling of rate limit errors."""
        client = AsyncMerakiClient(mock_settings)

        # Create a real APIError instance by creating mock response and metadata
        mock_response = Mock()
        mock_response.status = 429
        mock_response.reason = "Too Many Requests"

        mock_metadata = {"tags": ["rate-limit"], "operation": "test"}
        error = APIError(mock_metadata, mock_response)
        error.status = 429  # Set status directly
        error.reason = "Too Many Requests"

        with pytest.raises(APIError):
            async with client.api_call_context():
                raise error

        # Verify warning was logged
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.logger")
    async def test_api_call_context_client_error(
        self,
        mock_logger: Mock,
        mock_settings: Settings,
    ) -> None:
        """Test handling of client errors (4xx)."""
        client = AsyncMerakiClient(mock_settings)

        # Create a real APIError instance by creating mock response and metadata
        mock_response = Mock()
        mock_response.status = 404
        mock_response.reason = "Not Found"

        mock_metadata = {"tags": ["organizations"], "operation": "getOrganization"}
        error = APIError(mock_metadata, mock_response)
        error.status = 404  # Set status directly
        error.reason = "Not Found"

        with pytest.raises(APIError):
            async with client.api_call_context():
                raise error

        # Verify error was logged
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.logger")
    async def test_api_call_context_server_error(
        self,
        mock_logger: Mock,
        mock_settings: Settings,
    ) -> None:
        """Test handling of server errors (5xx)."""
        client = AsyncMerakiClient(mock_settings)

        # Create a real APIError instance by creating mock response and metadata
        mock_response = Mock()
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"

        mock_metadata = {"tags": ["server-error"], "operation": "test"}
        error = APIError(mock_metadata, mock_response)
        error.status = 500  # Set status directly
        error.reason = "Internal Server Error"

        with pytest.raises(APIError):
            async with client.api_call_context():
                raise error

        # Verify error was logged
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_call_context_unexpected_error(
        self,
        mock_settings: Settings,
    ) -> None:
        """Test handling of unexpected errors."""
        client = AsyncMerakiClient(mock_settings)

        with pytest.raises(RuntimeError):
            async with client.api_call_context():
                raise RuntimeError("Unexpected error")


class TestClientLifecycle:
    """Test client lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_client(
        self,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test closing the client."""
        client = AsyncMerakiClient(mock_settings)

        # Force API creation
        with patch(
            "meraki_dashboard_exporter.api.client.meraki.DashboardAPI",
            return_value=mock_dashboard_api,
        ):
            _ = client.api
            assert client._api is not None

        # Close should clear the API instance
        await client.close()
        assert client._api is None


class TestLoggingAndTracing:
    """Test logging and tracing integration."""

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.tracer")
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_tracing_spans(
        self,
        mock_to_thread: Mock,
        mock_tracer: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test that operations create proper tracing spans."""
        mock_to_thread.return_value = [{"id": "123", "name": "Org"}]
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            await client.get_organizations()

        # Should create span for operation
        mock_tracer.start_as_current_span.assert_called_once_with("get_organizations")
        mock_span.set_attribute.assert_any_call("api.endpoint", "getOrganizations")
        mock_span.set_attribute.assert_any_call("org.count", 1)
