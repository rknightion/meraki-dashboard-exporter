"""Tests for the StatusService and StatusSnapshot."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.org_health import OrgHealth
from meraki_dashboard_exporter.services.status import (
    ApiHealthStatus,
    CollectorStatus,
    DataFreshnessStatus,
    StatusService,
    StatusSnapshot,
    SystemStatus,
    _compute_staleness,  # noqa: PLC2701
    _format_time_ago,  # noqa: PLC2701
)


class TestStatusSnapshot:
    """Tests for StatusSnapshot dataclass construction."""

    def test_snapshot_round_trips_to_dict(self) -> None:
        """A snapshot can be converted to a dict for JSON serialization."""
        snapshot = StatusSnapshot(
            timestamp="2026-04-14T12:00:00Z",
            system=SystemStatus(
                version="1.0.0",
                uptime="3h 42m",
                readiness={
                    "ready": True,
                    "collectors": {"fast": True, "medium": True, "slow": True},
                },
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
                    last_success_time=1744632000.0,
                    last_success_ago="30s ago",
                    is_running=False,
                    staleness="ok",
                ),
            ],
            api_health=ApiHealthStatus(
                total_calls=100,
                throttle_events=2,
                per_org_rate_limits=[{"org_id": "123", "tokens_remaining": 5.0}],
            ),
            data_freshness=DataFreshnessStatus(
                total_tracked_metrics=500,
                by_collector={"DeviceCollector": 200},
                ttl_multiplier=2.0,
            ),
        )

        result = snapshot.to_dict()

        assert result["timestamp"] == "2026-04-14T12:00:00Z"
        assert result["system"]["version"] == "1.0.0"
        assert result["collectors"][0]["name"] == "DeviceCollector"
        assert result["collectors"][0]["success_rate"] == 90.0
        assert result["api_health"]["total_calls"] == 100
        assert result["data_freshness"]["total_tracked_metrics"] == 500


class TestStalenessComputation:
    """Tests for staleness threshold logic."""

    def test_ok_when_within_one_interval(self) -> None:
        """Return 'ok' when age is less than one tier interval."""
        now = 1000.0
        last_success = 950.0
        assert _compute_staleness(last_success, 60, now) == "ok"

    def test_warning_when_between_one_and_two_intervals(self) -> None:
        """Return 'warning' when age is between one and two tier intervals."""
        now = 1000.0
        last_success = 920.0
        assert _compute_staleness(last_success, 60, now) == "warning"

    def test_stale_when_beyond_two_intervals(self) -> None:
        """Return 'stale' when age exceeds two tier intervals."""
        now = 1000.0
        last_success = 800.0
        assert _compute_staleness(last_success, 60, now) == "stale"

    def test_stale_when_never_succeeded(self) -> None:
        """Return 'stale' when last_success_time is None."""
        assert _compute_staleness(None, 60, 1000.0) == "stale"

    def test_ok_at_exact_boundary(self) -> None:
        """Return 'ok' when age equals exactly one tier interval."""
        now = 1000.0
        last_success = 940.0
        assert _compute_staleness(last_success, 60, now) == "ok"

    def test_warning_at_exact_two_x_boundary(self) -> None:
        """Return 'warning' when age equals exactly two tier intervals."""
        now = 1000.0
        last_success = 880.0
        assert _compute_staleness(last_success, 60, now) == "warning"


class TestFormatTimeAgo:
    """Tests for human-readable relative time formatting."""

    def test_seconds_ago(self) -> None:
        """Format timestamps less than 60s old as seconds."""
        assert _format_time_ago(950.0, 1000.0) == "50s ago"

    def test_minutes_ago(self) -> None:
        """Format timestamps between 60s and 3600s old as minutes."""
        assert _format_time_ago(700.0, 1000.0) == "5m ago"

    def test_hours_ago(self) -> None:
        """Format timestamps over 3600s old as hours."""
        assert _format_time_ago(0.0, 7200.0) == "2h ago"

    def test_none_returns_never(self) -> None:
        """Return 'Never' when timestamp is None."""
        assert _format_time_ago(None, 1000.0) == "Never"


class TestStatusService:
    """Tests for StatusService.get_snapshot()."""

    def _make_service(self) -> tuple[StatusService, MagicMock, MagicMock, MagicMock, MagicMock]:
        mock_manager = MagicMock()
        mock_expiration = MagicMock()
        mock_client = MagicMock()
        mock_settings = MagicMock()

        mock_settings.update_intervals.fast = 60
        mock_settings.update_intervals.medium = 300
        mock_settings.update_intervals.slow = 900

        service = StatusService(
            collector_manager=mock_manager,
            expiration_manager=mock_expiration,
            client=mock_client,
            settings=mock_settings,
            start_time=0.0,
        )
        return service, mock_manager, mock_expiration, mock_client, mock_settings

    def test_get_snapshot_returns_snapshot(self) -> None:
        """Snapshot includes collector status, API health, and data freshness."""
        service, mock_manager, mock_expiration, mock_client, _ = self._make_service()

        mock_collector = MagicMock()
        mock_collector.__class__ = type("DeviceCollector", (), {})
        mock_collector.is_active = True

        mock_manager.collectors = {
            UpdateTier.FAST: [mock_collector],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {
            "DeviceCollector": {
                "total_runs": 10,
                "total_successes": 9,
                "total_failures": 1,
                "failure_streak": 0,
                "last_success_time": 950.0,
            },
        }
        mock_manager.is_collector_running.return_value = False
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": True},
        }
        mock_manager.org_health_tracker._orgs = {}
        mock_manager.rate_limiter._tokens = {"123": 5.0}
        mock_manager.rate_limiter.enabled = True
        mock_client._api_call_count = 42
        mock_expiration.get_stats.return_value = {
            "total_tracked": 500,
            "by_collector": {"DeviceCollector": 200},
            "ttl_multiplier": 2.0,
        }

        with patch("meraki_dashboard_exporter.services.status.time") as mock_time:
            mock_time.time.return_value = 1000.0
            snapshot = service.get_snapshot()

        assert snapshot.timestamp is not None
        assert len(snapshot.collectors) == 1
        assert snapshot.collectors[0].name == "DeviceCollector"
        assert snapshot.collectors[0].tier == "FAST"
        assert snapshot.collectors[0].success_rate == 90.0
        assert snapshot.collectors[0].staleness == "ok"
        assert snapshot.collectors[0].last_success_ago == "50s ago"
        assert snapshot.api_health.total_calls == 42
        assert snapshot.api_health.per_org_rate_limits == [
            {"org_id": "123", "tokens_remaining": 5.0}
        ]
        assert snapshot.data_freshness.total_tracked_metrics == 500

    def test_get_snapshot_handles_zero_runs(self) -> None:
        """Collectors with zero runs get 0% success rate and stale staleness."""
        service, mock_manager, mock_expiration, mock_client, _ = self._make_service()

        mock_collector = MagicMock()
        mock_collector.__class__ = type("AlertCollector", (), {})
        mock_collector.is_active = True

        mock_manager.collectors = {
            UpdateTier.FAST: [mock_collector],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {
            "AlertCollector": {
                "total_runs": 0,
                "total_successes": 0,
                "total_failures": 0,
                "failure_streak": 0,
                "last_success_time": None,
            },
        }
        mock_manager.is_collector_running.return_value = False
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"fast": False, "medium": False, "slow": False},
        }
        mock_manager.org_health_tracker._orgs = {}
        mock_manager.rate_limiter._tokens = {}
        mock_manager.rate_limiter.enabled = True
        mock_client._api_call_count = 0
        mock_expiration.get_stats.return_value = {
            "total_tracked": 0,
            "by_collector": {},
            "ttl_multiplier": 2.0,
        }

        with patch("meraki_dashboard_exporter.services.status.time") as mock_time:
            mock_time.time.return_value = 1000.0
            snapshot = service.get_snapshot()

        assert snapshot.collectors[0].success_rate == 0.0
        assert snapshot.collectors[0].staleness == "stale"

    def test_get_snapshot_includes_org_health_in_backoff(self) -> None:
        """Orgs in backoff appear with correct remaining seconds."""
        service, mock_manager, mock_expiration, mock_client, _ = self._make_service()

        mock_manager.collectors = {UpdateTier.FAST: [], UpdateTier.MEDIUM: [], UpdateTier.SLOW: []}
        mock_manager.collector_health = {}
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": True},
        }
        mock_manager.org_health_tracker._orgs = {
            "org1": OrgHealth(
                org_id="org1",
                org_name="Acme Corp",
                consecutive_failures=5,
                last_failure=980.0,
                backoff_until=1060.0,
            ),
        }
        mock_manager.rate_limiter._tokens = {}
        mock_manager.rate_limiter.enabled = True
        mock_client._api_call_count = 0
        mock_expiration.get_stats.return_value = {
            "total_tracked": 0,
            "by_collector": {},
            "ttl_multiplier": 2.0,
        }

        with patch("meraki_dashboard_exporter.services.status.time") as mock_time:
            mock_time.time.return_value = 1000.0
            snapshot = service.get_snapshot()

        assert len(snapshot.system.org_health) == 1
        org = snapshot.system.org_health[0]
        assert org.org_id == "org1"
        assert org.org_name == "Acme Corp"
        assert org.in_backoff is True
        assert org.backoff_remaining_seconds == 60.0
