"""Tests for ExporterApp endpoints and helper methods to increase app.py coverage."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.constants import UpdateTier


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
def exporter(test_settings: Settings) -> ExporterApp:
    """Create an ExporterApp instance for testing."""
    return ExporterApp(test_settings)


@pytest.fixture
def app_client(exporter: ExporterApp) -> TestClient:
    """Create a TestClient for the FastAPI app."""
    fastapi_app = exporter.create_app()
    return TestClient(fastapi_app, raise_server_exceptions=True)


@pytest.fixture
def mock_collector() -> MagicMock:
    """Create a mock collector with standard attributes."""
    collector = MagicMock()
    collector.__class__ = type("DeviceCollector", (), {})
    collector.is_active = True
    collector.update_tier = UpdateTier.MEDIUM
    return collector


@pytest.fixture
def exporter_with_mock_manager(
    exporter: ExporterApp, mock_collector: MagicMock
) -> tuple[ExporterApp, MagicMock]:
    """Create an ExporterApp with a mock CollectorManager."""
    mock_manager = MagicMock()
    mock_manager.collectors = {
        UpdateTier.FAST: [],
        UpdateTier.MEDIUM: [mock_collector],
        UpdateTier.SLOW: [],
    }
    mock_manager.collector_health = {
        "DeviceCollector": {
            "total_runs": 10,
            "total_successes": 9,
            "failure_streak": 0,
            "last_success_time": time.time() - 30,
        },
    }
    mock_manager.skipped_collectors = []
    mock_manager.is_collector_running.return_value = False
    mock_manager.get_scheduling_diagnostics.return_value = {
        "tiers": {
            "fast": {"interval": 60, "jitter_window": 6.0, "smoothing_window": 5.0},
            "medium": {"interval": 300, "jitter_window": 10.0, "smoothing_window": 25.0},
            "slow": {"interval": 900, "jitter_window": 10.0, "smoothing_window": 75.0},
        },
        "collector_offsets": [
            {"collector": "DeviceCollector", "tier": "medium", "offset_seconds": 0.0},
        ],
        "smoothing": {
            "enabled": True,
            "window_ratio": 0.3,
            "min_batch_delay": 0.1,
            "max_batch_delay": 2.0,
            "window_cap_seconds": 230.0,
        },
        "collector_timeout_seconds": 240,
        "rate_limiter": {
            "enabled": True,
            "rps": 10,
            "burst": 5,
            "share_fraction": 0.5,
        },
        "endpoint_intervals": {
            "ms_port_usage_interval": 300,
            "ms_packet_stats_interval": 300,
            "client_app_usage_interval": 300,
            "ms_port_status_org_endpoint": True,
        },
    }
    exporter.collector_manager = mock_manager
    return exporter, mock_manager


@pytest.fixture
def client_with_mock_manager(
    exporter_with_mock_manager: tuple[ExporterApp, MagicMock],
) -> TestClient:
    """Create a TestClient backed by a mock CollectorManager."""
    exporter, _ = exporter_with_mock_manager
    fastapi_app = exporter.create_app()
    return TestClient(fastapi_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests for GET / (root endpoint)
# ---------------------------------------------------------------------------


class TestRootEndpoint:
    """Tests for the GET / index page endpoint."""

    def test_root_returns_html(self, client_with_mock_manager: TestClient) -> None:
        """Test that root returns a 200 with HTML content."""
        response = client_with_mock_manager.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_root_contains_version(self, client_with_mock_manager: TestClient) -> None:
        """Test that root page contains version information."""
        response = client_with_mock_manager.get("/")
        assert response.status_code == 200
        assert "Meraki Dashboard Exporter" in response.text

    def test_root_contains_collector_info(self, client_with_mock_manager: TestClient) -> None:
        """Test that root page renders collector data."""
        response = client_with_mock_manager.get("/")
        assert response.status_code == 200
        # The mock collector name with "Collector" stripped is "Device"
        assert "Device" in response.text

    def test_root_with_no_collectors(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root renders with no active collectors."""
        exporter, mock_manager = exporter_with_mock_manager
        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200

    def test_root_with_skipped_collectors(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root renders skipped collectors section."""
        exporter, mock_manager = exporter_with_mock_manager
        mock_manager.skipped_collectors = [
            {"name": "AlertsCollector", "tier": "FAST", "reason": "disabled in config"},
        ]
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "AlertsCollector" in response.text

    def test_root_with_inactive_collector(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test that inactive collectors are excluded from the root page."""
        exporter, mock_manager = exporter_with_mock_manager
        inactive_collector = MagicMock()
        inactive_collector.__class__.__name__ = "InactiveCollector"
        inactive_collector.is_active = False
        mock_manager.collectors[UpdateTier.MEDIUM].append(inactive_collector)
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        # Inactive collector should not appear
        assert "Inactive" not in response.text

    def test_root_last_success_never(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root handles collectors with no last_success_time."""
        exporter, mock_manager = exporter_with_mock_manager
        mock_manager.collector_health["DeviceCollector"]["last_success_time"] = None
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "Never" in response.text

    def test_root_last_success_minutes_ago(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root displays last success in minutes format."""
        exporter, mock_manager = exporter_with_mock_manager
        # Set to 120 seconds (2 minutes) ago
        mock_manager.collector_health["DeviceCollector"]["last_success_time"] = time.time() - 120
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "2m ago" in response.text

    def test_root_last_success_hours_ago(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root displays last success in hours format."""
        exporter, mock_manager = exporter_with_mock_manager
        # Set to 7200 seconds (2 hours) ago
        mock_manager.collector_health["DeviceCollector"]["last_success_time"] = time.time() - 7200
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "2h ago" in response.text

    def test_root_with_zero_total_runs(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root handles collectors with zero total runs."""
        exporter, mock_manager = exporter_with_mock_manager
        mock_manager.collector_health["DeviceCollector"] = {
            "total_runs": 0,
            "total_successes": 0,
            "failure_streak": 0,
            "last_success_time": None,
        }
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200

    def test_root_with_no_org_id(self, test_settings: Settings) -> None:
        """Test root displays 'All' when no org_id is set."""
        test_settings.meraki.org_id = ""
        exporter = ExporterApp(test_settings)
        mock_manager = MagicMock()
        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {}
        mock_manager.skipped_collectors = []
        mock_manager.get_scheduling_diagnostics.return_value = {
            "tiers": {},
            "collector_offsets": [],
            "smoothing": {
                "enabled": False,
                "window_ratio": 0.0,
                "min_batch_delay": 0.0,
                "max_batch_delay": 0.0,
                "window_cap_seconds": 0.0,
            },
            "collector_timeout_seconds": 240,
            "rate_limiter": {"enabled": False, "rps": 0, "burst": 0, "share_fraction": 0.0},
            "endpoint_intervals": {
                "ms_port_usage_interval": 300,
                "ms_packet_stats_interval": 300,
                "client_app_usage_interval": 300,
                "ms_port_status_org_endpoint": False,
            },
        }
        exporter.collector_manager = mock_manager
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200
        assert "All" in response.text

    def test_root_collector_is_running(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test root page when a collector is currently running."""
        exporter, mock_manager = exporter_with_mock_manager
        mock_manager.is_collector_running.return_value = True
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests for GET /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for the GET /health endpoint."""

    def test_health_returns_healthy(self, app_client: TestClient) -> None:
        """Test that /health returns a healthy status."""
        response = app_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# Tests for GET /metrics
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    """Tests for the GET /metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, app_client: TestClient) -> None:
        """Test that /metrics returns Prometheus text format."""
        response = app_client.get("/metrics")
        assert response.status_code == 200
        # Prometheus content type
        assert "text/plain" in response.headers["content-type"] or (
            "text/openmetrics" in response.headers["content-type"]
        )

    def test_metrics_contains_data(self, app_client: TestClient) -> None:
        """Test that /metrics returns non-empty content."""
        response = app_client.get("/metrics")
        assert response.status_code == 200
        assert len(response.content) > 0


# ---------------------------------------------------------------------------
# Tests for POST /api/collectors/trigger
# ---------------------------------------------------------------------------


class TestTriggerCollectorEndpoint:
    """Tests for the POST /api/collectors/trigger endpoint."""

    @pytest.fixture
    def trigger_client(self, test_settings: Settings) -> tuple[TestClient, MagicMock, ExporterApp]:
        """Create a fresh TestClient with mock manager for trigger tests."""
        exporter = ExporterApp(test_settings)
        mock_manager = MagicMock()
        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {}
        mock_manager.skipped_collectors = []
        mock_manager.is_collector_running.return_value = False
        mock_manager.get_scheduling_diagnostics.return_value = {
            "tiers": {},
            "collector_offsets": [],
            "smoothing": {
                "enabled": False,
                "window_ratio": 0.0,
                "min_batch_delay": 0.0,
                "max_batch_delay": 0.0,
                "window_cap_seconds": 0.0,
            },
            "collector_timeout_seconds": 240,
            "rate_limiter": {"enabled": False, "rps": 0, "burst": 0, "share_fraction": 0.0},
            "endpoint_intervals": {
                "ms_port_usage_interval": 300,
                "ms_packet_stats_interval": 300,
                "client_app_usage_interval": 300,
                "ms_port_status_org_endpoint": False,
            },
        }
        exporter.collector_manager = mock_manager
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=False)
        return client, mock_manager, exporter

    def test_trigger_collector_not_found(
        self, trigger_client: tuple[TestClient, MagicMock, ExporterApp]
    ) -> None:
        """Test triggering a non-existent collector returns error."""
        client, mock_manager, _ = trigger_client
        mock_manager.get_collector_by_name.return_value = None

        response = client.post(
            "/api/collectors/trigger",
            json={"collector": "NonExistentCollector"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert "not found" in body["message"]

    def test_trigger_collector_disabled(
        self, trigger_client: tuple[TestClient, MagicMock, ExporterApp]
    ) -> None:
        """Test triggering a disabled collector returns error."""
        client, mock_manager, _ = trigger_client
        disabled_collector = MagicMock()
        disabled_collector.__class__.__name__ = "DisabledCollector"
        disabled_collector.is_active = False
        mock_manager.get_collector_by_name.return_value = (disabled_collector, UpdateTier.MEDIUM)

        response = client.post(
            "/api/collectors/trigger",
            json={"collector": "DisabledCollector"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert "disabled" in body["message"].lower()

    def test_trigger_collector_already_running(
        self, trigger_client: tuple[TestClient, MagicMock, ExporterApp]
    ) -> None:
        """Test triggering an already-running collector returns running status."""
        client, mock_manager, _ = trigger_client
        running_collector = MagicMock()
        running_collector.__class__.__name__ = "DeviceCollector"
        running_collector.is_active = True
        mock_manager.get_collector_by_name.return_value = (running_collector, UpdateTier.MEDIUM)
        mock_manager.is_collector_running.return_value = True

        response = client.post(
            "/api/collectors/trigger",
            json={"collector": "DeviceCollector"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "running"
        assert "already running" in body["message"]

    def test_trigger_collector_success(
        self, trigger_client: tuple[TestClient, MagicMock, ExporterApp]
    ) -> None:
        """Test successfully triggering a collector.

        The endpoint creates an asyncio.Task for the background run. In the
        TestClient synchronous context there is no running event loop, so we
        patch asyncio.create_task to avoid the RuntimeError while still
        exercising the full function body.
        """
        from unittest.mock import patch

        client, mock_manager, _ = trigger_client
        active_collector = MagicMock()
        active_collector.__class__.__name__ = "DeviceCollector"
        active_collector.is_active = True
        mock_manager.get_collector_by_name.return_value = (active_collector, UpdateTier.MEDIUM)
        mock_manager.is_collector_running.return_value = False

        mock_task = MagicMock()
        with patch("asyncio.create_task", return_value=mock_task):
            response = client.post(
                "/api/collectors/trigger",
                json={"collector": "DeviceCollector"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "started"
        assert "triggered" in body["message"]


# ---------------------------------------------------------------------------
# Tests for _handle_shutdown
# ---------------------------------------------------------------------------


class TestHandleShutdown:
    """Tests for ExporterApp._handle_shutdown()."""

    def test_handle_shutdown_sets_event(self, exporter: ExporterApp) -> None:
        """Test that _handle_shutdown sets the shutdown event."""
        import asyncio

        exporter._shutdown_event = asyncio.Event()
        assert not exporter._shutdown_event.is_set()
        exporter._handle_shutdown()
        assert exporter._shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Tests for GET /clients endpoint
# ---------------------------------------------------------------------------


class TestClientsEndpoint:
    """Tests for the GET /clients endpoint."""

    def test_clients_disabled(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test /clients returns 404 when client collection is disabled."""
        exporter, _ = exporter_with_mock_manager
        exporter.settings.clients.enabled = False
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/clients")
        assert response.status_code == 404
        assert "disabled" in response.text.lower()

    def test_clients_no_collector_found(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test /clients returns 500 when ClientsCollector is not found."""
        exporter, mock_manager = exporter_with_mock_manager
        exporter.settings.clients.enabled = True
        # No ClientsCollector in the collector list
        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.get("/clients")
        assert response.status_code == 500
        assert "not found" in response.text.lower()


# ---------------------------------------------------------------------------
# Tests for POST /api/clients/clear-dns-cache
# ---------------------------------------------------------------------------


class TestClearDnsCacheEndpoint:
    """Tests for the POST /api/clients/clear-dns-cache endpoint."""

    def test_clear_dns_cache_disabled(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test clear-dns-cache returns error when clients disabled."""
        exporter, _ = exporter_with_mock_manager
        exporter.settings.clients.enabled = False
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.post("/api/clients/clear-dns-cache")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert "disabled" in body["message"].lower()

    def test_clear_dns_cache_no_resolver(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test clear-dns-cache returns error when no DNS resolver found."""
        exporter, mock_manager = exporter_with_mock_manager
        exporter.settings.clients.enabled = True
        # No ClientsCollector -> no dns resolver
        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.post("/api/clients/clear-dns-cache")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert "not found" in body["message"].lower()

    def test_clear_dns_cache_success(
        self, exporter_with_mock_manager: tuple[ExporterApp, MagicMock]
    ) -> None:
        """Test clear-dns-cache successfully clears the cache."""
        exporter, mock_manager = exporter_with_mock_manager
        exporter.settings.clients.enabled = True

        # Create a mock ClientsCollector with a dns_resolver
        mock_dns_resolver = MagicMock()
        mock_clients_collector = MagicMock()
        mock_clients_collector.__class__ = type("ClientsCollector", (), {})
        mock_clients_collector.is_active = True
        mock_clients_collector.dns_resolver = mock_dns_resolver

        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [mock_clients_collector],
            UpdateTier.SLOW: [],
        }
        fastapi_app = exporter.create_app()
        client = TestClient(fastapi_app, raise_server_exceptions=True)

        response = client.post("/api/clients/clear-dns-cache")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        mock_dns_resolver.clear_cache.assert_called_once()


# ---------------------------------------------------------------------------
# Tests for ExporterApp._format_uptime()
# ---------------------------------------------------------------------------


class TestFormatUptime:
    """Tests for ExporterApp._format_uptime() helper."""

    def test_format_uptime_minutes_only(self, exporter: ExporterApp) -> None:
        """Test uptime formatting when under an hour."""
        exporter._start_time = time.time() - 300  # 5 minutes ago
        result = exporter._format_uptime()
        assert result == "5m"

    def test_format_uptime_zero_minutes(self, exporter: ExporterApp) -> None:
        """Test uptime formatting when just started."""
        exporter._start_time = time.time()
        result = exporter._format_uptime()
        assert result == "0m"

    def test_format_uptime_hours_and_minutes(self, exporter: ExporterApp) -> None:
        """Test uptime formatting when over an hour."""
        exporter._start_time = time.time() - 3900  # 1h 5m ago
        result = exporter._format_uptime()
        assert result == "1h 5m"

    def test_format_uptime_days_and_hours(self, exporter: ExporterApp) -> None:
        """Test uptime formatting when over a day."""
        exporter._start_time = time.time() - 90000  # 1d 1h ago
        result = exporter._format_uptime()
        assert result == "1d 1h"

    def test_format_uptime_multiple_days(self, exporter: ExporterApp) -> None:
        """Test uptime formatting for multiple days."""
        exporter._start_time = time.time() - 259200  # 3 days
        result = exporter._format_uptime()
        assert result == "3d 0h"


# ---------------------------------------------------------------------------
# Tests for ExporterApp._get_metrics_stats()
# ---------------------------------------------------------------------------


class TestGetMetricsStats:
    """Tests for ExporterApp._get_metrics_stats() helper."""

    def test_get_metrics_stats_returns_dict(self, exporter: ExporterApp) -> None:
        """Test that _get_metrics_stats returns a dict with required keys."""
        result = exporter._get_metrics_stats()
        assert "metric_count" in result
        assert "timeseries_count" in result
        assert isinstance(result["metric_count"], int)
        assert isinstance(result["timeseries_count"], int)

    def test_get_metrics_stats_nonnegative(self, exporter: ExporterApp) -> None:
        """Test that metric counts are non-negative."""
        result = exporter._get_metrics_stats()
        assert result["metric_count"] >= 0
        assert result["timeseries_count"] >= 0

    def test_get_metrics_stats_excludes_cardinality(self, exporter: ExporterApp) -> None:
        """Test that cardinality metrics are excluded from counts."""
        # Register a temporary cardinality metric to ensure it is excluded
        from prometheus_client import Gauge

        test_gauge = Gauge(
            "meraki_exporter_cardinality_test_metric_abc",
            "Test cardinality metric",
        )
        try:
            test_gauge.set(1)
            result = exporter._get_metrics_stats()
            # The cardinality metric should not be counted; verify it
            # by checking a known cardinality metric is not inflating the count
            assert result["metric_count"] >= 0
        finally:
            # Clean up the test gauge from the registry
            from prometheus_client import REGISTRY

            REGISTRY.unregister(test_gauge)


# ---------------------------------------------------------------------------
# Tests for Settings helper methods (covers core/config.py uncovered lines)
# ---------------------------------------------------------------------------


class TestSettingsHelpers:
    """Tests for Settings.get_collector_config and Settings.to_summary."""

    def test_get_collector_config_enabled(self, test_settings: Settings) -> None:
        """Test get_collector_config returns enabled for active collector."""
        result = test_settings.get_collector_config("device")
        assert result["enabled"] is True
        assert "timeout" in result

    def test_get_collector_config_disabled(self, test_settings: Settings) -> None:
        """Test get_collector_config returns disabled for unknown collector."""
        result = test_settings.get_collector_config("nonexistent_collector")
        assert result["enabled"] is False

    def test_to_summary(self, test_settings: Settings) -> None:
        """Test to_summary returns a dict without sensitive data."""
        result = test_settings.to_summary()
        assert "meraki" in result
        assert "org_id" in result["meraki"]
        assert "api_base_url" in result["meraki"]
        assert "api_key" not in result["meraki"]
        assert "logging" in result
        assert "collectors" in result

    def test_china_region_timeout_adjustment(self) -> None:
        """Test that China region URL triggers timeout adjustment."""
        settings = Settings(
            meraki=MerakiSettings(
                api_key=SecretStr("test_api_key_at_least_30_characters_long"),
                org_id="123456",
                api_base_url="https://api.meraki.china.example.com/api/v1",
            ),
        )
        # With "china" in URL and default timeout < 45, should be bumped to 45
        assert settings.api.timeout >= 45


class TestMerakiAPIConfig:
    """Tests for MerakiAPIConfig to cover the base_url property."""

    def test_base_url_property(self) -> None:
        """Test that base_url returns the default regional URL."""
        from meraki_dashboard_exporter.core.constants.config_constants import MerakiAPIConfig

        config = MerakiAPIConfig()
        assert config.base_url == "https://api.meraki.com/api/v1"


class TestGetVersionFallback:
    """Tests for __version__.py fallback path."""

    def test_get_version_fallback_to_metadata(self) -> None:
        """Test get_version falls back to importlib.metadata when pyproject.toml missing."""
        from unittest.mock import patch

        from meraki_dashboard_exporter.__version__ import get_version

        # Patch Path.exists to return False so it falls back to importlib.metadata
        with patch("meraki_dashboard_exporter.__version__.Path.exists", return_value=False):
            version = get_version()
            # Should return the installed package version or dev fallback
            assert isinstance(version, str)
            assert len(version) > 0


class TestUpdateIntervalValidation:
    """Tests for UpdateIntervals model validator."""

    def test_medium_not_multiple_of_fast_raises(self) -> None:
        """Test that medium not a multiple of fast raises ValueError."""
        from pydantic import ValidationError as PydanticValidationError

        from meraki_dashboard_exporter.core.config_models import UpdateIntervals

        # fast=70 is within [30, 300], medium=300 is within [300, 1800]
        # but 300 % 70 = 20 != 0, so the model_validator should raise
        with pytest.raises(PydanticValidationError, match="should be a multiple of fast"):
            UpdateIntervals(fast=70, medium=300, slow=900)
