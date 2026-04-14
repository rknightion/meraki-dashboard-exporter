"""Tests for core.config_logger to increase coverage."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.core import config_logger as config_logger_mod
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_logger import (
    get_env_vars,
    log_configuration,
    log_startup_summary,
    mask_sensitive_value,
)
from meraki_dashboard_exporter.core.config_models import MerakiSettings


@pytest.fixture
def test_settings() -> Settings:
    """Create minimal settings for config logger testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


class TestMaskSensitiveValue:
    """Tests for mask_sensitive_value."""

    def test_masks_api_key(self) -> None:
        """Test that api_key values are redacted."""
        assert mask_sensitive_value("api_key", "secret123") == "***REDACTED***"

    def test_masks_password(self) -> None:
        """Test that password values are redacted."""
        assert mask_sensitive_value("db_password", "p@ss") == "***REDACTED***"

    def test_masks_token(self) -> None:
        """Test that token values are redacted."""
        assert mask_sensitive_value("auth_token", "tok") == "***REDACTED***"

    def test_masks_secret(self) -> None:
        """Test that secret values are redacted."""
        assert mask_sensitive_value("webhook_secret", "s") == "***REDACTED***"

    def test_masks_credential(self) -> None:
        """Test that credential values are redacted."""
        assert mask_sensitive_value("my_credential", "c") == "***REDACTED***"

    def test_does_not_mask_normal_key(self) -> None:
        """Test that non-sensitive keys are not masked."""
        assert mask_sensitive_value("host", "localhost") == "localhost"

    def test_case_insensitive(self) -> None:
        """Test that masking is case-insensitive."""
        assert mask_sensitive_value("API_KEY", "val") == "***REDACTED***"


class TestGetEnvVars:
    """Tests for get_env_vars."""

    def test_returns_dict(self) -> None:
        """Test that get_env_vars returns a dictionary."""
        result = get_env_vars()
        assert isinstance(result, dict)

    @patch.dict(os.environ, {"MERAKI_EXPORTER_FOO": "bar"}, clear=False)
    def test_captures_meraki_exporter_vars(self) -> None:
        """Test that MERAKI_EXPORTER_ prefixed vars are captured."""
        result = get_env_vars()
        assert "MERAKI_EXPORTER_FOO" in result
        assert result["MERAKI_EXPORTER_FOO"] == "bar"

    def test_masks_api_key_env(self) -> None:
        """Test that MERAKI_API_KEY env var is masked."""
        fake_key = "my-fake-test-value"  # pragma: allowlist secret
        with patch.dict(os.environ, {"MERAKI_API_KEY": fake_key}, clear=False):
            result = get_env_vars()
        assert "MERAKI_API_KEY" in result
        assert result["MERAKI_API_KEY"] == "***REDACTED***"

    @patch.dict(os.environ, {"UNRELATED_VAR": "val"}, clear=False)
    def test_ignores_unrelated_vars(self) -> None:
        """Test that non-MERAKI vars are not included."""
        result = get_env_vars()
        assert "UNRELATED_VAR" not in result


class TestTruncateList:
    """Tests for the _truncate_list helper."""

    def test_short_list_not_truncated(self) -> None:
        """Test that a short list is returned as-is."""
        truncate = config_logger_mod._truncate_list  # noqa: SLF001
        values, truncated = truncate(["a", "b", "c"], max_items=5)
        assert values == ["a", "b", "c"]
        assert truncated is False

    def test_exact_length_not_truncated(self) -> None:
        """Test that a list at exactly max_items is not truncated."""
        truncate = config_logger_mod._truncate_list  # noqa: SLF001
        values, truncated = truncate(["a", "b", "c"], max_items=3)
        assert values == ["a", "b", "c"]
        assert truncated is False

    def test_long_list_truncated(self) -> None:
        """Test that a list over max_items is truncated."""
        truncate = config_logger_mod._truncate_list  # noqa: SLF001
        values, truncated = truncate(["a", "b", "c", "d", "e"], max_items=3)
        assert values == ["a", "b", "c"]
        assert truncated is True


class TestLogConfiguration:
    """Tests for log_configuration."""

    def test_does_not_raise(self, test_settings: Settings) -> None:
        """Test that log_configuration runs without error."""
        log_configuration(test_settings)


class TestLogStartupSummary:
    """Tests for log_startup_summary."""

    def test_basic_summary(self, test_settings: Settings) -> None:
        """Test startup summary with minimal args."""
        log_startup_summary(test_settings)

    def test_with_discovery_summary(self, test_settings: Settings) -> None:
        """Test startup summary with discovery data."""
        discovery = {
            "organizations": [
                {"name": "Test Org", "id": "123456"},
            ],
            "networks": {
                "123456": {
                    "count": 5,
                    "org_name": "Test Org",
                    "product_types": {"wireless": 3, "switch": 2},
                },
            },
            "errors": [],
        }
        log_startup_summary(test_settings, discovery_summary=discovery)

    def test_with_scheduling(self, test_settings: Settings) -> None:
        """Test startup summary with scheduling diagnostics."""
        scheduling = {
            "tiers": {
                "fast": {"interval": 60, "jitter_window": 6.0},
                "medium": {"interval": 300, "jitter_window": 10.0},
                "slow": {"interval": 900, "jitter_window": 10.0},
            },
            "collector_offsets": [
                {"collector": "DeviceCollector", "tier": "medium", "offset_seconds": 0.0},
            ],
            "endpoint_intervals": {
                "ms_port_usage_interval": 300,
                "ms_packet_stats_interval": 300,
            },
        }
        log_startup_summary(test_settings, scheduling=scheduling)

    def test_with_discovery_errors(self, test_settings: Settings) -> None:
        """Test startup summary with discovery errors."""
        discovery = {
            "organizations": [],
            "errors": ["discovery_failed"],
        }
        log_startup_summary(test_settings, discovery_summary=discovery)

    def test_without_org_id(self, test_settings: Settings) -> None:
        """Test startup summary with no org_id set."""
        test_settings.meraki.org_id = ""
        log_startup_summary(test_settings)

    def test_with_otel_enabled(self, test_settings: Settings) -> None:
        """Test startup summary with OTEL enabled."""
        test_settings.otel.enabled = True
        test_settings.otel.endpoint = "http://localhost:4317"
        test_settings.otel.service_name = "meraki-exporter"
        log_startup_summary(test_settings)
