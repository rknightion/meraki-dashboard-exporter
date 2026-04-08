"""Tests for collection utilization ratio metric in CollectorManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.constants import UpdateTier


@pytest.fixture
def test_settings() -> Settings:
    """Create minimal settings for testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


@pytest.fixture
def manager(test_settings: Settings) -> CollectorManager:
    """Create a CollectorManager with mocked initialization."""
    mock_client = MagicMock()
    mock_client.api = MagicMock()

    with patch.object(CollectorManager, "_initialize_metrics"):
        with patch.object(CollectorManager, "_initialize_collectors"):
            with patch.object(CollectorManager, "_validate_collector_configuration"):
                mgr = CollectorManager(client=mock_client, settings=test_settings)

    # Manually wire up the gauges that the real _initialize_metrics creates
    mgr._parallel_collections_active = MagicMock()
    mgr._parallel_collections_active.labels.return_value = MagicMock()
    mgr._collection_errors = MagicMock()
    mgr._collection_errors.labels.return_value = MagicMock()
    mgr._collector_last_success_age = MagicMock()
    mgr._collector_last_success_age.labels.return_value = MagicMock()
    mgr._collector_failure_streak = MagicMock()
    mgr._collector_failure_streak.labels.return_value = MagicMock()
    mgr._collection_utilization = MagicMock()
    mgr._collection_utilization.labels.return_value = MagicMock()

    return mgr


def _make_collector(name: str = "TestCollector") -> MagicMock:
    """Create a minimal mock MetricCollector."""
    collector = MagicMock()
    collector.__class__.__name__ = name
    collector.collect = AsyncMock()
    return collector


class TestCollectionUtilizationCalculation:
    """Tests for the utilization ratio calculation (duration / interval)."""

    @pytest.mark.asyncio
    async def test_utilization_set_after_collection(self, manager: CollectorManager) -> None:
        """Utilization gauge is set after a collector completes."""
        collector = _make_collector()
        tier = UpdateTier.FAST  # 60s interval

        await manager._run_collector_with_timeout(collector, tier, timeout=120)

        manager._collection_utilization.labels.assert_called_with(
            collector="TestCollector",
            tier="fast",
        )
        gauge_mock = manager._collection_utilization.labels.return_value
        gauge_mock.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_utilization_ratio_uses_tier_interval(self, manager: CollectorManager) -> None:
        """Utilization is calculated as duration / tier interval (not timeout)."""
        collector = _make_collector()

        # Patch time to control the measured duration
        fake_start = 1000.0
        fake_end = 1006.0  # 6 seconds elapsed

        with patch("meraki_dashboard_exporter.collectors.manager.time") as mock_time:
            mock_time.time.side_effect = [fake_start, fake_end, fake_end]
            await manager._run_collector_with_timeout(collector, UpdateTier.FAST, timeout=120)

        gauge_mock = manager._collection_utilization.labels.return_value
        gauge_mock.set.assert_called_once()
        set_value = gauge_mock.set.call_args[0][0]

        fast_interval = manager.settings.update_intervals.fast  # 60s
        expected = 6.0 / fast_interval
        assert abs(set_value - expected) < 0.01

    @pytest.mark.asyncio
    async def test_utilization_uses_medium_tier_interval(self, manager: CollectorManager) -> None:
        """Utilization denominator changes with the tier interval."""
        collector = _make_collector()

        fake_start = 2000.0
        fake_end = 2030.0  # 30 seconds elapsed

        with patch("meraki_dashboard_exporter.collectors.manager.time") as mock_time:
            mock_time.time.side_effect = [fake_start, fake_end, fake_end]
            await manager._run_collector_with_timeout(collector, UpdateTier.MEDIUM, timeout=120)

        gauge_mock = manager._collection_utilization.labels.return_value
        set_value = gauge_mock.set.call_args[0][0]

        medium_interval = manager.settings.update_intervals.medium  # 300s
        expected = 30.0 / medium_interval
        assert abs(set_value - expected) < 0.01

    @pytest.mark.asyncio
    async def test_utilization_set_even_on_collection_error(
        self, manager: CollectorManager
    ) -> None:
        """Utilization is recorded even when the collector raises an exception."""
        collector = _make_collector()
        collector.collect = AsyncMock(side_effect=RuntimeError("boom"))

        await manager._run_collector_with_timeout(collector, UpdateTier.FAST, timeout=120)

        gauge_mock = manager._collection_utilization.labels.return_value
        gauge_mock.set.assert_called_once()


class TestCollectionUtilizationWarning:
    """Tests for the high-utilization warning log."""

    @pytest.mark.asyncio
    async def test_warning_logged_when_utilization_above_threshold(
        self, manager: CollectorManager
    ) -> None:
        """A warning is logged when utilization exceeds 0.8."""
        collector = _make_collector()

        fast_interval = manager.settings.update_intervals.fast  # 60s
        # Duration = 85% of interval -> utilization 0.85 > 0.8
        elapsed = fast_interval * 0.85

        fake_start = 3000.0
        fake_end = fake_start + elapsed

        with patch("meraki_dashboard_exporter.collectors.manager.time") as mock_time:
            mock_time.time.side_effect = [fake_start, fake_end, fake_end]
            with patch("meraki_dashboard_exporter.collectors.manager.logger") as mock_logger:
                await manager._run_collector_with_timeout(collector, UpdateTier.FAST, timeout=120)

        mock_logger.warning.assert_called_once()
        warning_kwargs = mock_logger.warning.call_args
        assert "utilization" in str(warning_kwargs).lower() or "high" in str(warning_kwargs).lower()

    @pytest.mark.asyncio
    async def test_no_warning_when_utilization_below_threshold(
        self, manager: CollectorManager
    ) -> None:
        """No warning is logged when utilization is below 0.8."""
        collector = _make_collector()

        fast_interval = manager.settings.update_intervals.fast  # 60s
        # Duration = 50% of interval -> utilization 0.5 < 0.8
        elapsed = fast_interval * 0.50

        fake_start = 4000.0
        fake_end = fake_start + elapsed

        with patch("meraki_dashboard_exporter.collectors.manager.time") as mock_time:
            mock_time.time.side_effect = [fake_start, fake_end, fake_end]
            with patch("meraki_dashboard_exporter.collectors.manager.logger") as mock_logger:
                await manager._run_collector_with_timeout(collector, UpdateTier.FAST, timeout=120)

        # logger.warning should not have been called for utilization
        for call in mock_logger.warning.call_args_list:
            # Allow other warnings but not the utilization warning
            assert "utilization" not in str(call).lower() and "may not keep up" not in str(call)

    @pytest.mark.asyncio
    async def test_warning_includes_collector_name_and_tier(
        self, manager: CollectorManager
    ) -> None:
        """The high-utilization warning includes collector, tier, and utilization fields."""
        collector = _make_collector("SlowCollector")

        fast_interval = manager.settings.update_intervals.fast  # 60s
        elapsed = fast_interval * 0.90  # 90% utilization

        fake_start = 5000.0
        fake_end = fake_start + elapsed

        with patch("meraki_dashboard_exporter.collectors.manager.time") as mock_time:
            mock_time.time.side_effect = [fake_start, fake_end, fake_end]
            with patch("meraki_dashboard_exporter.collectors.manager.logger") as mock_logger:
                await manager._run_collector_with_timeout(collector, UpdateTier.FAST, timeout=120)

        mock_logger.warning.assert_called_once()
        _, kwargs = mock_logger.warning.call_args
        assert kwargs.get("collector") == "SlowCollector"
        assert kwargs.get("tier") == "fast"
        assert "utilization" in kwargs

    @pytest.mark.asyncio
    async def test_warning_at_exactly_threshold_boundary(self, manager: CollectorManager) -> None:
        """Utilization exactly at 0.8 does NOT trigger a warning (strictly > 0.8)."""
        collector = _make_collector()

        fast_interval = manager.settings.update_intervals.fast  # 60s
        elapsed = fast_interval * 0.80  # exactly 0.8

        fake_start = 6000.0
        fake_end = fake_start + elapsed

        with patch("meraki_dashboard_exporter.collectors.manager.time") as mock_time:
            mock_time.time.side_effect = [fake_start, fake_end, fake_end]
            with patch("meraki_dashboard_exporter.collectors.manager.logger") as mock_logger:
                await manager._run_collector_with_timeout(collector, UpdateTier.FAST, timeout=120)

        for call in mock_logger.warning.call_args_list:
            assert "may not keep up" not in str(call)
