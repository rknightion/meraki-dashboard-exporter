"""Tests for AsyncMerakiClient.get_sensor_gateway_connections_latest (#269)."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock()

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
    api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(return_value=[])
    return api


class TestSensorGatewayConnectionsEndpoint:
    """Test the sensor-to-gateway connectivity API wrapper."""

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_sensor_gateway_connections_latest(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Fetches org-wide sensor-to-gateway connections with total_pages='all'."""
        mock_connections = [
            {
                "lastReportedAt": "2024-01-01T00:00:00Z",
                "lastConnectedAt": "2024-01-01T00:00:00Z",
                "rssi": -55,
                "network": {"id": "N_1", "name": "Net 1"},
                "sensor": {"serial": "Q2MT-XXXX", "name": "Sensor1", "mac": "00:00:00:00:00:01"},
                "gateway": {"serial": "Q2GW-YYYY", "name": "Gateway1", "mac": "00:00:00:00:00:02"},
            }
        ]
        mock_to_thread.return_value = mock_connections

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_sensor_gateway_connections_latest("org123")

        assert result == mock_connections
        mock_to_thread.assert_called_once_with(
            mock_dashboard_api.sensor.getOrganizationSensorGatewaysConnectionsLatest,
            "org123",
            total_pages="all",
        )

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.api.client.asyncio.to_thread")
    async def test_get_sensor_gateway_connections_latest_empty(
        self,
        mock_to_thread: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Empty response is handled without error."""
        mock_to_thread.return_value = []

        client = AsyncMerakiClient(mock_settings)
        with patch.object(client, "_api", mock_dashboard_api):
            result = await client.get_sensor_gateway_connections_latest("org123")

        assert result == []
