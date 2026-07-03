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
            readiness={"ready": True, "collectors": {"DeviceCollector": True}},
            org_health=[],
        ),
        collectors=[
            CollectorStatus(
                name="DeviceCollector",
                cadence_seconds=60.0,
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
            "network_filter",
            "webhook",
            "scheduler",
        }


class TestStatusEndpointScheduler:
    """The scheduler diagnostics section (#617) rides the /status snapshot."""

    def _scheduler_diagnostics(self) -> dict:
        return {
            "mode": "adaptive",
            "org_shape": {
                "org_id": "123456",
                "network_count": 500,
                "wireless_network_count": 500,
                "switch_network_count": 400,
                "appliance_network_count": 500,
                "sensor_network_count": 50,
                "camera_network_count": 30,
                "cellular_network_count": 10,
                "device_count": 5000,
                "ap_count": 2000,
                "switch_count": 1500,
                "appliance_count": 500,
                "physical_mx_count": 480,
                "camera_count": 300,
                "sensor_count": 200,
                "cellular_count": 20,
            },
            "budget_rps": 8.0,
            "effective_budget_rps": 8.0,
            "target_utilization": 0.7,
            "over_budget": False,
            "total_demand_rps": 4.2,
            "last_resolve_ts": 1000.0,
            "groups": [
                {
                    "name": "nh_connection_stats",
                    "priority": 3,
                    "tier": "medium",
                    "floor_seconds": 1800.0,
                    "interval_seconds": 1800.0,
                    "stretch_factor": 1.0,
                    "pinned": False,
                    "cost_per_cycle": 500.0,
                    "demand_rps": 0.28,
                    "last_ran_ago_seconds": 42.0,
                },
            ],
        }

    def test_status_json_carries_scheduler_section(self, app_client: TestClient) -> None:
        """/status?format=json exposes the scheduler diagnostics dict verbatim."""
        snapshot = _make_snapshot()
        snapshot.scheduler = self._scheduler_diagnostics()
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=snapshot,
        ):
            response = app_client.get("/status?format=json")

        assert response.status_code == 200
        sched = response.json()["scheduler"]
        assert sched["mode"] == "adaptive"
        assert sched["budget_rps"] == 8.0
        assert sched["effective_budget_rps"] == 8.0
        assert sched["org_shape"]["device_count"] == 5000
        assert sched["groups"][0]["name"] == "nh_connection_stats"
        assert sched["groups"][0]["interval_seconds"] == 1800.0

    def test_status_json_scheduler_absent_is_null(self, app_client: TestClient) -> None:
        """When the scheduler has not resolved, the section serializes as null."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status?format=json")

        assert response.status_code == 200
        assert response.json()["scheduler"] is None

    def test_status_html_renders_scheduler_section(self, app_client: TestClient) -> None:
        """The HTML page renders the Scheduler card with the org shape + groups."""
        snapshot = _make_snapshot()
        snapshot.scheduler = self._scheduler_diagnostics()
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=snapshot,
        ):
            response = app_client.get("/status")

        body = response.text
        assert "Scheduler" in body
        assert "nh_connection_stats" in body
        assert "Org Shape" in body
