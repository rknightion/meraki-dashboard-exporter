"""Tests for the AsyncMerakiClient wrapper."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, Mock, patch

import pytest
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
    settings.api.action_batch_retry_wait = 10
    settings.api.rate_limit_retry_wait = 5
    settings.api.validate_kwargs = False

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
            validate_kwargs=False,
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


class TestApiRequestTotalAccessor:
    """F-028/F-074: expose the real Meraki API request total for /status."""

    def test_get_total_api_requests_reflects_increments(self, mock_settings: Settings) -> None:
        """The accessor sums the shared request counter across all labels.

        The legacy ``_api_call_count`` attribute was never incremented, so
        /status always reported zero. ``get_total_api_requests`` reads the real
        ``_api_requests_total`` counter that inventory increments per call.
        """
        client = AsyncMerakiClient(mock_settings)

        before = client.get_total_api_requests()

        assert AsyncMerakiClient._api_requests_total is not None
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizations", method="GET", status_code="200"
        ).inc()
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizationDevices", method="GET", status_code="200"
        ).inc(2)

        assert client.get_total_api_requests() == before + 3


class TestAuthOutcomeLatch:
    """#509: auth-outcome latch used for /status `authenticated` and readiness."""

    def test_auth_outcome_latch(self) -> None:
        """get_auth_ok() tracks record_auth_outcome()/reset_auth_state()."""
        AsyncMerakiClient.reset_auth_state()
        assert AsyncMerakiClient.get_auth_ok() is None

        AsyncMerakiClient.record_auth_outcome(False)
        assert AsyncMerakiClient.get_auth_ok() is False

        AsyncMerakiClient.record_auth_outcome(True)
        assert AsyncMerakiClient.get_auth_ok() is True

        AsyncMerakiClient.reset_auth_state()
        assert AsyncMerakiClient.get_auth_ok() is None

    def test_get_successful_api_requests_counts_only_200(self, mock_settings: Settings) -> None:
        """get_successful_api_requests sums only status_code=200 samples."""
        client = AsyncMerakiClient(mock_settings)

        before = client.get_successful_api_requests()

        assert AsyncMerakiClient._api_requests_total is not None
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizations", method="GET", status_code="200"
        ).inc(2)
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizations", method="GET", status_code="401"
        ).inc(5)

        assert client.get_successful_api_requests() == before + 2
