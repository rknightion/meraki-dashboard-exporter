"""Tests for the /status endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.services.status import (
    ApiHealthStatus,
    CollectorStatus,
    DataFreshnessStatus,
    StatusSnapshot,
    SystemStatus,
)


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


def _make_snapshot() -> StatusSnapshot:
    """Build a minimal StatusSnapshot for testing."""
    return StatusSnapshot(
        timestamp="2026-04-14T12:00:00Z",
        system=SystemStatus(
            version="1.0.0",
            uptime="1h 30m",
            readiness={"ready": True, "collectors": {"fast": True, "medium": True, "slow": True}},
            org_health=[],
        ),
        collectors=[
            CollectorStatus(
                name="DeviceCollector",
                tier="FAST",
                total_runs=10,
                total_successes=9,
                total_failures=1,
                success_rate=90.0,
                failure_streak=0,
                last_success_time=1000.0,
                last_success_ago="30s ago",
                is_running=False,
                staleness="ok",
            ),
        ],
        api_health=ApiHealthStatus(total_calls=42, throttle_events=0, per_org_rate_limits=[]),
        data_freshness=DataFreshnessStatus(
            total_tracked_metrics=500, by_collector={}, ttl_multiplier=2.0
        ),
    )


class TestStatusEndpointHTML:
    """Tests for GET /status returning HTML."""

    def test_status_returns_html_by_default(self, app_client: TestClient) -> None:
        """GET /status returns an HTML page by default."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Exporter Status" in response.text
        assert "DeviceCollector" in response.text

    def test_status_html_contains_sections(self, app_client: TestClient) -> None:
        """The HTML page contains all expected sections."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status")

        body = response.text
        assert "Collectors" in body
        assert "API Health" in body
        assert "Data Freshness" in body


class TestStatusEndpointJSON:
    """Tests for GET /status?format=json returning JSON."""

    def test_status_returns_json_when_requested(self, app_client: TestClient) -> None:
        """GET /status?format=json returns a JSON response."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert data["timestamp"] == "2026-04-14T12:00:00Z"
        assert data["system"]["version"] == "1.0.0"
        assert len(data["collectors"]) == 1
        assert data["collectors"][0]["name"] == "DeviceCollector"

    def test_status_json_matches_snapshot_structure(self, app_client: TestClient) -> None:
        """The JSON output has the expected top-level keys."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status?format=json")

        data = response.json()
        assert set(data.keys()) == {
            "timestamp",
            "system",
            "collectors",
            "api_health",
            "data_freshness",
        }
