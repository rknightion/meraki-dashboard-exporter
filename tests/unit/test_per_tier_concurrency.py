"""Tests for per-tier concurrency limit settings."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import APISettings, MerakiSettings
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
                return CollectorManager(client=mock_client, settings=test_settings)


class TestAPISettingsPerTierDefaults:
    """Tests for per-tier concurrency default values in APISettings."""

    def test_fast_tier_default_concurrency(self) -> None:
        """FAST tier default concurrency is 5 (sensor readings are lightweight)."""
        api_settings = APISettings()
        assert api_settings.concurrency_limit_fast == 5

    def test_medium_tier_default_concurrency(self) -> None:
        """MEDIUM tier default concurrency is 3 (standard collection)."""
        api_settings = APISettings()
        assert api_settings.concurrency_limit_medium == 3

    def test_slow_tier_default_concurrency(self) -> None:
        """SLOW tier default concurrency is 2 (config endpoints are heavier)."""
        api_settings = APISettings()
        assert api_settings.concurrency_limit_slow == 2

    def test_global_fallback_concurrency_unchanged(self) -> None:
        """Global concurrency_limit default is still 5 (backwards compat)."""
        api_settings = APISettings()
        assert api_settings.concurrency_limit == 5

    def test_per_tier_values_are_configurable(self) -> None:
        """Per-tier concurrency limits can be overridden."""
        api_settings = APISettings(
            concurrency_limit_fast=10,
            concurrency_limit_medium=7,
            concurrency_limit_slow=4,
        )
        assert api_settings.concurrency_limit_fast == 10
        assert api_settings.concurrency_limit_medium == 7
        assert api_settings.concurrency_limit_slow == 4


class TestGetTierConcurrency:
    """Tests for CollectorManager._get_tier_concurrency()."""

    def test_fast_tier_returns_fast_limit(self, manager: CollectorManager) -> None:
        """_get_tier_concurrency returns FAST tier limit for UpdateTier.FAST."""
        result = manager._get_tier_concurrency(UpdateTier.FAST)
        assert result == manager.settings.api.concurrency_limit_fast

    def test_medium_tier_returns_medium_limit(self, manager: CollectorManager) -> None:
        """_get_tier_concurrency returns MEDIUM tier limit for UpdateTier.MEDIUM."""
        result = manager._get_tier_concurrency(UpdateTier.MEDIUM)
        assert result == manager.settings.api.concurrency_limit_medium

    def test_slow_tier_returns_slow_limit(self, manager: CollectorManager) -> None:
        """_get_tier_concurrency returns SLOW tier limit for UpdateTier.SLOW."""
        result = manager._get_tier_concurrency(UpdateTier.SLOW)
        assert result == manager.settings.api.concurrency_limit_slow

    def test_fast_tier_returns_default_5(self, manager: CollectorManager) -> None:
        """_get_tier_concurrency returns 5 for FAST tier by default."""
        result = manager._get_tier_concurrency(UpdateTier.FAST)
        assert result == 5

    def test_medium_tier_returns_default_3(self, manager: CollectorManager) -> None:
        """_get_tier_concurrency returns 3 for MEDIUM tier by default."""
        result = manager._get_tier_concurrency(UpdateTier.MEDIUM)
        assert result == 3

    def test_slow_tier_returns_default_2(self, manager: CollectorManager) -> None:
        """_get_tier_concurrency returns 2 for SLOW tier by default."""
        result = manager._get_tier_concurrency(UpdateTier.SLOW)
        assert result == 2

    def test_custom_fast_concurrency_reflected(self, test_settings: Settings) -> None:
        """Custom FAST concurrency setting is reflected in _get_tier_concurrency."""
        test_settings.api.concurrency_limit_fast = 8
        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    mgr = CollectorManager(client=mock_client, settings=test_settings)

        assert mgr._get_tier_concurrency(UpdateTier.FAST) == 8

    def test_custom_medium_concurrency_reflected(self, test_settings: Settings) -> None:
        """Custom MEDIUM concurrency setting is reflected in _get_tier_concurrency."""
        test_settings.api.concurrency_limit_medium = 6
        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    mgr = CollectorManager(client=mock_client, settings=test_settings)

        assert mgr._get_tier_concurrency(UpdateTier.MEDIUM) == 6

    def test_custom_slow_concurrency_reflected(self, test_settings: Settings) -> None:
        """Custom SLOW concurrency setting is reflected in _get_tier_concurrency."""
        test_settings.api.concurrency_limit_slow = 4
        mock_client = MagicMock()
        mock_client.api = MagicMock()

        with patch.object(CollectorManager, "_initialize_metrics"):
            with patch.object(CollectorManager, "_initialize_collectors"):
                with patch.object(CollectorManager, "_validate_collector_configuration"):
                    mgr = CollectorManager(client=mock_client, settings=test_settings)

        assert mgr._get_tier_concurrency(UpdateTier.SLOW) == 4

    def test_tiers_have_distinct_defaults(self, manager: CollectorManager) -> None:
        """FAST, MEDIUM, and SLOW tiers use different default concurrency limits."""
        fast = manager._get_tier_concurrency(UpdateTier.FAST)
        medium = manager._get_tier_concurrency(UpdateTier.MEDIUM)
        slow = manager._get_tier_concurrency(UpdateTier.SLOW)

        # Each tier has a unique value by default: FAST > MEDIUM > SLOW
        assert fast > medium > slow
