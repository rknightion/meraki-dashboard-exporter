"""Tests for the /ready readiness probe endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings


@pytest.fixture
def test_settings() -> Settings:
    """Create minimal settings for endpoint testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


@pytest.fixture
def app_client(test_settings: Settings) -> TestClient:
    """Create a TestClient for the FastAPI app."""
    exporter = ExporterApp(test_settings)
    fastapi_app = exporter.create_app()
    return TestClient(fastapi_app, raise_server_exceptions=True)


@pytest.fixture
def app_and_manager(test_settings: Settings) -> tuple[TestClient, MagicMock]:
    """Create a TestClient with a mock CollectorManager for controlling readiness state."""
    exporter = ExporterApp(test_settings)
    fastapi_app = exporter.create_app()

    # Replace the real manager with a mock so we can control readiness state
    mock_manager = MagicMock()
    exporter.collector_manager = mock_manager

    client = TestClient(fastapi_app, raise_server_exceptions=True)
    return client, mock_manager


class TestReadinessEndpointNotReady:
    """Tests for /ready returning 503 before collection completes."""

    def test_ready_returns_503_before_any_collection(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 503 before any collection cycle completes."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"DeviceCollector": False, "NetworkHealthCollector": False},
        }

        response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False

    def test_ready_returns_503_when_some_collectors_incomplete(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 503 when only some gating collectors have succeeded."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"DeviceCollector": True, "NetworkHealthCollector": False},
        }

        response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert body["collectors"]["DeviceCollector"] is True
        assert body["collectors"]["NetworkHealthCollector"] is False


class TestReadinessEndpointReady:
    """Tests for /ready returning 200 after required collection completes."""

    def test_ready_returns_200_when_all_gating_collectors_complete(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 200 once every gating collector has succeeded."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"DeviceCollector": True, "NetworkHealthCollector": True},
        }

        response = client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["collectors"]["DeviceCollector"] is True
        assert body["collectors"]["NetworkHealthCollector"] is True


class TestReadinessStatusFormat:
    """Tests for the readiness status dictionary format."""

    def test_readiness_status_has_required_keys(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that the readiness status response includes all required keys."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"DeviceCollector": False},
        }

        response = client.get("/ready")
        body = response.json()

        assert "ready" in body
        assert "collectors" in body
        assert "DeviceCollector" in body["collectors"]

    def test_readiness_status_booleans(self, app_and_manager: tuple[TestClient, MagicMock]) -> None:
        """Test that readiness status values are booleans."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"DeviceCollector": True, "NetworkHealthCollector": False},
        }

        response = client.get("/ready")
        body = response.json()

        assert isinstance(body["ready"], bool)
        assert isinstance(body["collectors"]["DeviceCollector"], bool)
        assert isinstance(body["collectors"]["NetworkHealthCollector"], bool)


def _gating_collector(name: str):  # type: ignore[no-untyped-def]
    """Build a minimal collector owning one enabled, gated priority-1 group."""
    group = SimpleNamespace(priority=1, gated=True, name="grp")
    cls = type(name, (), {"get_endpoint_groups": lambda self: (group,)})
    return cls()


class TestCollectorManagerReadiness:
    """Unit tests for CollectorManager readiness tracking logic (#631)."""

    def _make_manager(self, test_settings: Settings, *, api_requests: int) -> MagicMock:
        from unittest.mock import patch

        from meraki_dashboard_exporter.collectors.manager import CollectorManager

        mock_client = MagicMock()
        mock_client.api = MagicMock()
        mock_client.get_successful_api_requests.return_value = api_requests

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    manager = CollectorManager(client=mock_client, settings=test_settings)
        # Every gated group reports enabled so the readiness set is driven purely
        # by first-success bookkeeping in these unit tests.
        manager.scheduler.is_enabled = lambda name: True  # type: ignore[assignment]
        return manager

    def test_initial_state_not_ready(self, test_settings: Settings) -> None:
        """Test that a fresh CollectorManager is not ready and nothing has succeeded."""
        manager = self._make_manager(test_settings, api_requests=0)

        assert manager.is_ready is False
        assert manager._collector_succeeded == set()

    def test_get_readiness_status_initial(self, test_settings: Settings) -> None:
        """Test that get_readiness_status returns correct initial state (no collectors)."""
        manager = self._make_manager(test_settings, api_requests=0)

        status = manager.get_readiness_status()
        assert status == {
            "ready": False,
            "api_success": False,
            "collectors": {},
        }

    def test_not_ready_until_every_gating_collector_succeeds(self, test_settings: Settings) -> None:
        """is_ready requires every priority-<=3 gating collector to have succeeded."""
        manager = self._make_manager(test_settings, api_requests=5)
        manager.collectors = [
            _gating_collector("DeviceCollector"),
            _gating_collector("AlertsCollector"),
        ]

        # Nothing has succeeded yet.
        assert manager.is_ready is False

        # Only one of the two gating collectors succeeded: still not ready.
        manager._collector_succeeded.add("DeviceCollector")
        assert manager.is_ready is False

        # Both gating collectors have now succeeded: ready.
        manager._collector_succeeded.add("AlertsCollector")
        assert manager.is_ready is True

    def test_is_ready_requires_api_success(self, test_settings: Settings) -> None:
        """Test that is_ready is gated on >=1 HTTP-200 API request (#509)."""
        manager = self._make_manager(test_settings, api_requests=0)
        manager.collectors = [_gating_collector("DeviceCollector")]
        manager._collector_succeeded.add("DeviceCollector")

        manager.client.get_successful_api_requests.return_value = 0
        assert manager.is_ready is False

        manager.client.get_successful_api_requests.return_value = 5
        assert manager.is_ready is True

    def test_get_readiness_status_when_ready(self, test_settings: Settings) -> None:
        """Test get_readiness_status maps each gating collector to its success state."""
        manager = self._make_manager(test_settings, api_requests=5)
        manager.collectors = [_gating_collector("DeviceCollector")]
        manager._collector_succeeded.add("DeviceCollector")

        status = manager.get_readiness_status()
        assert status == {
            "ready": True,
            "api_success": True,
            "collectors": {"DeviceCollector": True},
        }
