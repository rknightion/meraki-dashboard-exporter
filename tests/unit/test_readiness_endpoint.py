"""Tests for the /ready readiness probe endpoint."""

from __future__ import annotations

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
            "collectors": {"fast": False, "medium": False, "slow": False},
        }

        response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False

    def test_ready_returns_503_when_only_fast_complete(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 503 when only FAST tier has completed."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"fast": True, "medium": False, "slow": False},
        }

        response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert body["collectors"]["fast"] is True
        assert body["collectors"]["medium"] is False

    def test_ready_returns_503_when_only_medium_complete(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 503 when only MEDIUM tier has completed."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"fast": False, "medium": True, "slow": False},
        }

        response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert body["collectors"]["fast"] is False
        assert body["collectors"]["medium"] is True


class TestReadinessEndpointReady:
    """Tests for /ready returning 200 after required collection completes."""

    def test_ready_returns_200_after_fast_and_medium_complete(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 200 after both FAST and MEDIUM tiers complete."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": False},
        }

        response = client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["collectors"]["fast"] is True
        assert body["collectors"]["medium"] is True

    def test_ready_returns_200_when_all_tiers_complete(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that /ready returns 200 when all tiers have completed."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": True},
        }

        response = client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["collectors"]["slow"] is True


class TestReadinessStatusFormat:
    """Tests for the readiness status dictionary format."""

    def test_readiness_status_has_required_keys(
        self, app_and_manager: tuple[TestClient, MagicMock]
    ) -> None:
        """Test that the readiness status response includes all required keys."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"fast": False, "medium": False, "slow": False},
        }

        response = client.get("/ready")
        body = response.json()

        assert "ready" in body
        assert "collectors" in body
        assert "fast" in body["collectors"]
        assert "medium" in body["collectors"]
        assert "slow" in body["collectors"]

    def test_readiness_status_booleans(self, app_and_manager: tuple[TestClient, MagicMock]) -> None:
        """Test that readiness status values are booleans."""
        client, mock_manager = app_and_manager
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": False},
        }

        response = client.get("/ready")
        body = response.json()

        assert isinstance(body["ready"], bool)
        assert isinstance(body["collectors"]["fast"], bool)
        assert isinstance(body["collectors"]["medium"], bool)
        assert isinstance(body["collectors"]["slow"], bool)


class TestCollectorManagerReadiness:
    """Unit tests for CollectorManager readiness tracking logic."""

    def test_initial_state_not_ready(self, test_settings: Settings) -> None:
        """Test that a fresh CollectorManager is not ready."""
        from unittest.mock import patch

        from meraki_dashboard_exporter.collectors.manager import CollectorManager

        mock_client = MagicMock()
        mock_client.api = MagicMock()

        # Patch out all the metric registrations to avoid Prometheus duplicate errors
        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    manager = CollectorManager(client=mock_client, settings=test_settings)

        assert manager.is_ready is False
        assert manager._tier_initial_complete == {
            "fast": False,
            "medium": False,
            "slow": False,
        }

    def test_get_readiness_status_initial(self, test_settings: Settings) -> None:
        """Test that get_readiness_status returns correct initial state."""
        from unittest.mock import patch

        from meraki_dashboard_exporter.collectors.manager import CollectorManager

        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    manager = CollectorManager(client=mock_client, settings=test_settings)

        status = manager.get_readiness_status()
        assert status == {
            "ready": False,
            "collectors": {"fast": False, "medium": False, "slow": False},
        }

    def test_is_ready_requires_both_fast_and_medium(self, test_settings: Settings) -> None:
        """Test that is_ready requires both fast and medium tiers, not just one."""
        from unittest.mock import patch

        from meraki_dashboard_exporter.collectors.manager import CollectorManager

        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    manager = CollectorManager(client=mock_client, settings=test_settings)

        # Only fast complete: not ready
        manager._tier_initial_complete["fast"] = True
        assert manager.is_ready is False

        # Both fast and medium complete: ready
        manager._tier_initial_complete["medium"] = True
        assert manager.is_ready is True

    def test_is_ready_does_not_require_slow(self, test_settings: Settings) -> None:
        """Test that is_ready does not require SLOW tier to complete."""
        from unittest.mock import patch

        from meraki_dashboard_exporter.collectors.manager import CollectorManager

        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    manager = CollectorManager(client=mock_client, settings=test_settings)

        manager._tier_initial_complete["fast"] = True
        manager._tier_initial_complete["medium"] = True
        # slow is still False

        assert manager.is_ready is True

    def test_get_readiness_status_when_ready(self, test_settings: Settings) -> None:
        """Test get_readiness_status when both required tiers are complete."""
        from unittest.mock import patch

        from meraki_dashboard_exporter.collectors.manager import CollectorManager

        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    manager = CollectorManager(client=mock_client, settings=test_settings)

        manager._tier_initial_complete["fast"] = True
        manager._tier_initial_complete["medium"] = True

        status = manager.get_readiness_status()
        assert status == {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": False},
        }
